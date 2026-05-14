"""
Feedback Loop Agent
===================
Joins content edit-types with 30-day rank delta outcomes to identify
which changes correlate with improvements. Updates prompt weights.

Inputs:  project_id (or all)
Outputs: feedback_signals rows in ClickHouse, prompt config updates
Queue:   optimize (weekly schedule)
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Optional

try:
    import clickhouse_connect
except ImportError:
    clickhouse_connect = None

from sqlalchemy import select, and_

from core.config import settings
from core.logging import get_logger
from db.models import ContentVersion, Project
from db.worker_session import create_worker_session_factory
from services.storage import StorageService

logger = get_logger("feedback_agent")


class FeedbackLoopAgent:
    """
    Analyses which content edit-types correlate with rank improvements
    and surfaces these signals to tune future content generation prompts.
    """

    def __init__(self) -> None:
        self.ch = clickhouse_connect.get_client(
            host=settings.clickhouse_host,
            port=settings.clickhouse_port,
            username=settings.clickhouse_user,
            password=settings.clickhouse_password,
            database=settings.clickhouse_database,
        )
        self.storage = StorageService()

    # ── Main entry point ───────────────────────────────────────────────────

    async def run_for_project(self, project_id: str) -> dict:
        logger.info("feedback.start", project_id=project_id)

        # Get content versions with measured rank deltas
        SessionLocal = create_worker_session_factory()
        async with SessionLocal() as session:
            result = await session.execute(
                select(ContentVersion).where(
                    and_(
                        ContentVersion.project_id == project_id,
                        ContentVersion.rank_delta_30d.isnot(None),
                        ContentVersion.content_type == "optimize_diff",
                    )
                )
            )
            versions = result.scalars().all()

        if not versions:
            logger.info("feedback.no_data", project_id=project_id)
            return {"status": "no_data"}

        # Load edit metadata from S3 for each version
        signals = []
        for v in versions:
            if not v.s3_key or not v.rank_delta_30d:
                continue
            try:
                edit_data = await self.storage.get_json(v.s3_key)
                edit_types = [e["edit_type"] for e in edit_data.get("edit_set", {}).get("edits", [])]
                for edit_type in edit_types:
                    signals.append({
                        "recorded_at": datetime.now(timezone.utc),
                        "project_id": project_id,
                        "content_version_id": str(v.id),
                        "edit_type": edit_type,
                        "position_before": v.rank_at_publish or 0,
                        "position_after": v.rank_30d or 0,
                        "position_delta": v.rank_delta_30d,
                        "days_to_measure": 30,
                        "keyword": v.target_keyword or "",
                    })
            except Exception as exc:
                logger.warning("feedback.load_error", version=str(v.id), error=str(exc))

        if signals:
            self._write_signals_to_clickhouse(signals)

        # Compute aggregated insights
        insights = self._compute_insights(signals)

        # Persist insights as a prompt config update
        await self._update_prompt_config(project_id, insights)

        logger.info("feedback.complete", signals=len(signals), insights=insights)
        return {"signals_recorded": len(signals), "insights": insights}

    # ── Aggregation ────────────────────────────────────────────────────────

    def _compute_insights(self, signals: list[dict]) -> dict:
        """Aggregate rank-delta by edit_type to find what works."""
        by_type: dict[str, list[float]] = defaultdict(list)
        for s in signals:
            by_type[s["edit_type"]].append(s["position_delta"])

        ranked: list[dict] = []
        for edit_type, deltas in by_type.items():
            avg_delta = mean(deltas) if deltas else 0.0
            ranked.append({
                "edit_type": edit_type,
                "avg_rank_improvement": round(avg_delta, 2),
                "sample_size": len(deltas),
                "success_rate": round(sum(1 for d in deltas if d > 0) / len(deltas), 2),
            })

        ranked.sort(key=lambda x: x["avg_rank_improvement"], reverse=True)

        return {
            "best_edit_types": ranked[:5],
            "worst_edit_types": ranked[-3:] if len(ranked) >= 3 else [],
            "total_signals": len(signals),
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── Prompt config update ───────────────────────────────────────────────

    async def _update_prompt_config(self, project_id: str, insights: dict) -> None:
        """
        Persist insights as a JSON config that the ContentGenAgent and
        OptimizerAgent read at runtime to weight their prompt instructions.
        """
        config_key = f"projects/{project_id}/prompt_config.json"

        try:
            existing = await self.storage.get_json(config_key) or {}
        except Exception:
            existing = {}

        # Merge new insights with historical config
        history = existing.get("history", [])
        history.append(insights)
        history = history[-12:]  # Keep last 12 weeks

        # Compute rolling weights for edit type emphasis
        all_signals = [s for h in history for s in h.get("best_edit_types", [])]
        type_scores: dict[str, list[float]] = defaultdict(list)
        for s in all_signals:
            type_scores[s["edit_type"]].append(s["avg_rank_improvement"])

        weights = {
            et: round(mean(scores), 2)
            for et, scores in type_scores.items()
            if scores
        }

        updated_config = {
            "project_id": project_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "edit_type_weights": weights,
            "emphasise_in_prompts": [
                et for et, w in sorted(weights.items(), key=lambda x: x[1], reverse=True)[:3]
            ],
            "de_emphasise_in_prompts": [
                et for et, w in sorted(weights.items(), key=lambda x: x[1])[:2]
                if w < 0
            ],
            "history": history,
        }

        await self.storage.put_json(config_key, updated_config)
        logger.info("feedback.config_updated", project_id=project_id, weights=weights)

    # ── ClickHouse write ───────────────────────────────────────────────────

    def _write_signals_to_clickhouse(self, signals: list[dict]) -> None:
        column_names = [
            "recorded_at", "project_id", "content_version_id", "edit_type",
            "position_before", "position_after", "position_delta",
            "days_to_measure", "keyword",
        ]
        data = [[s[c] for c in column_names] for s in signals]
        self.ch.insert(
            "analytics.feedback_signals",
            data,
            column_names=column_names,
        )
