"""
Performance Tracker Agent
=========================
Polls GSC daily for fresh ranking data, computes deltas vs previous
snapshots, and writes time-series rows to ClickHouse.

Inputs:  project_id (or all active projects)
Outputs: rankings_daily rows in ClickHouse, rank_delta on ContentVersion
Queue:   tracker (scheduled via Celery beat)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import clickhouse_connect
from sqlalchemy import select

from core.config import settings
from core.logging import get_logger
from db.models import ContentVersion, Keyword, Project
from db.worker_session import create_worker_session_factory
from integrations.gsc.client import GSCClient

logger = get_logger("tracker_agent")


class TrackerAgent:
    """
    Fetches daily performance data from GSC, computes rank deltas,
    and persists analytics rows to ClickHouse for dashboard queries.
    """

    def __init__(self) -> None:
        self.ch = clickhouse_connect.get_client(
            host=settings.clickhouse_host,
            port=8123,
            username=settings.clickhouse_user,
            password=settings.clickhouse_password,
            database=settings.clickhouse_database,
        )

    # ── Main entry point ───────────────────────────────────────────────────

    async def run_for_project(self, project_id: str) -> dict:
        logger.info("tracker.start", project_id=project_id)

        SessionLocal = create_worker_session_factory()
        async with SessionLocal() as session:
            project = await session.get(Project, project_id)
            if not project or not project.gsc_access_token:
                logger.warning("tracker.no_gsc_token", project_id=project_id)
                return {"status": "skipped", "reason": "no_gsc_token"}

            result = await session.execute(
                select(Keyword).where(Keyword.project_id == project_id)
            )
            keywords = result.scalars().all()

        if not keywords:
            return {"status": "skipped", "reason": "no_keywords"}

        # Fetch yesterday's GSC data (GSC lags ~2 days, so we take -3 days)
        target_date = (datetime.now(timezone.utc) - timedelta(days=3)).date()
        date_str = target_date.isoformat()

        gsc = GSCClient(project)
        rows = await gsc.fetch_queries(
            start_date=date_str,
            end_date=date_str,
            row_limit=25000,
        )

        # Build lookup map query -> gsc data
        gsc_map = {r["query"]: r for r in rows}

        # Build ClickHouse rows and compute deltas
        ch_rows = []
        for kw in keywords:
            gsc_data = gsc_map.get(kw.query)
            if not gsc_data:
                continue

            new_position = gsc_data.get("position", 0.0)
            prev_position = kw.avg_position or new_position

            ch_rows.append({
                "date": target_date,
                "project_id": str(project_id),
                "page_url": "",  # GSC page-level query needed for this; simplified
                "keyword_id": str(kw.id),
                "query": kw.query,
                "position": new_position,
                "impressions": gsc_data.get("impressions", 0),
                "clicks": gsc_data.get("clicks", 0),
                "ctr": gsc_data.get("ctr", 0.0),
                "position_delta": round(prev_position - new_position, 2),
                "impressions_delta": gsc_data.get("impressions", 0) - kw.impressions,
                "clicks_delta": gsc_data.get("clicks", 0) - kw.clicks,
            })

        if ch_rows:
            self._insert_to_clickhouse(ch_rows)

        # Update avg_position on Keyword rows in Postgres
        await self._update_keyword_positions(keywords, gsc_map)

        # Update rank_delta on recently published ContentVersions
        await self._update_content_version_deltas(project_id, gsc_map)

        logger.info("tracker.complete", project_id=project_id, rows=len(ch_rows))
        return {"rows_inserted": len(ch_rows), "date": date_str}

    async def run_all_projects(self) -> dict:
        """Run tracker for all active projects with GSC connected."""
        SessionLocal = create_worker_session_factory()
        async with SessionLocal() as session:
            result = await session.execute(
                select(Project).where(
                    Project.gsc_access_token.isnot(None),
                )
            )
            projects = result.scalars().all()

        results = {}
        for project in projects:
            try:
                results[str(project.id)] = await self.run_for_project(str(project.id))
            except Exception as exc:
                logger.error("tracker.project_error", project_id=str(project.id), error=str(exc))
                results[str(project.id)] = {"status": "error", "error": str(exc)}

        return results

    # ── ClickHouse write ───────────────────────────────────────────────────

    def _insert_to_clickhouse(self, rows: list[dict]) -> None:
        column_names = [
            "date", "project_id", "page_url", "keyword_id", "query",
            "position", "impressions", "clicks", "ctr",
            "position_delta", "impressions_delta", "clicks_delta",
        ]
        data = [[r[c] for c in column_names] for r in rows]
        self.ch.insert(
            "analytics.rankings_daily",
            data,
            column_names=column_names,
        )

    # ── Postgres updates ───────────────────────────────────────────────────

    async def _update_keyword_positions(
        self,
        keywords: list[Keyword],
        gsc_map: dict,
    ) -> None:
        SessionLocal = create_worker_session_factory()
        async with SessionLocal() as session:
            for kw in keywords:
                gsc_data = gsc_map.get(kw.query)
                if not gsc_data:
                    continue
                kw_obj = await session.get(Keyword, kw.id)
                if kw_obj:
                    kw_obj.avg_position = gsc_data.get("position")
                    kw_obj.impressions = gsc_data.get("impressions", 0)
                    kw_obj.clicks = gsc_data.get("clicks", 0)
                    kw_obj.ctr = gsc_data.get("ctr", 0.0)
                    session.add(kw_obj)
            await session.commit()

    async def _update_content_version_deltas(
        self,
        project_id: str,
        gsc_map: dict,
    ) -> None:
        """Update rank_delta_30d on content versions published ~30 days ago."""
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        window_start = thirty_days_ago - timedelta(days=3)
        window_end = thirty_days_ago + timedelta(days=3)

        SessionLocal = create_worker_session_factory()
        async with SessionLocal() as session:
            result = await session.execute(
                select(ContentVersion).where(
                    ContentVersion.project_id == project_id,
                    ContentVersion.published_at.between(window_start, window_end),
                    ContentVersion.rank_at_publish.isnot(None),
                )
            )
            versions = result.scalars().all()

            for v in versions:
                if not v.target_keyword:
                    continue
                gsc_data = gsc_map.get(v.target_keyword)
                if not gsc_data:
                    continue

                current_pos = gsc_data.get("position")
                if current_pos and v.rank_at_publish:
                    v.rank_30d = current_pos
                    v.rank_delta_30d = v.rank_at_publish - current_pos  # positive = improved
                    session.add(v)

            await session.commit()
