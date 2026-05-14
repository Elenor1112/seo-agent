"""Analytics router - ClickHouse query endpoints."""
import math
from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, Query
import clickhouse_connect
from core.config import settings

router = APIRouter()


def get_ch():
    return clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=8123,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
    )


def _safe_float(value, ndigits: int = 1) -> Optional[float]:
    """Return a rounded float, or None if value is nan/inf/None."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return round(f, ndigits)


def _safe_int(value) -> int:
    """Return an int, or 0 if value is nan/None."""
    if value is None:
        return 0
    try:
        f = float(value)
        return 0 if not math.isfinite(f) else int(f)
    except (TypeError, ValueError):
        return 0


@router.get("/project/{project_id}/rankings")
async def get_rankings_trend(
    project_id: UUID,
    days: int = Query(30, ge=7, le=365),
    keyword_id: Optional[str] = Query(None),
):
    """Time-series ranking data for dashboard charts."""
    ch = get_ch()
    where = f"project_id = '{project_id}'"
    if keyword_id:
        where += f" AND keyword_id = '{keyword_id}'"

    result = ch.query(f"""
        SELECT
            date,
            avg(position)    as avg_position,
            sum(impressions) as total_impressions,
            sum(clicks)      as total_clicks,
            avg(ctr)         as avg_ctr
        FROM analytics.rankings_daily
        WHERE {where}
          AND date >= today() - {days}
        GROUP BY date
        ORDER BY date ASC
    """)

    return [
        {
            "date": str(row[0]),
            "avg_position": _safe_float(row[1], 1),
            "impressions": _safe_int(row[2]),
            "clicks": _safe_int(row[3]),
            "ctr": _safe_float(row[4] * 100 if row[4] is not None else None, 2),
        }
        for row in result.result_rows
    ]


@router.get("/project/{project_id}/top-movers")
async def get_top_movers(project_id: UUID, days: int = Query(7, ge=1, le=90)):
    """Keywords with the biggest position improvements."""
    ch = get_ch()
    result = ch.query(f"""
        SELECT
            query,
            keyword_id,
            avg(position_delta) as avg_delta,
            avg(position)       as latest_position
        FROM analytics.rankings_daily
        WHERE project_id = '{project_id}'
          AND date >= today() - {days}
        GROUP BY query, keyword_id
        HAVING avg_delta > 0
        ORDER BY avg_delta DESC
        LIMIT 20
    """)
    return [
        {
            "query": row[0],
            "keyword_id": row[1],
            "avg_position_improvement": _safe_float(row[2], 1),
            "latest_position": _safe_float(row[3], 1),
        }
        for row in result.result_rows
    ]


@router.get("/project/{project_id}/summary")
async def get_project_summary(project_id: UUID):
    """High-level KPI summary for the project dashboard."""
    ch = get_ch()

    result = ch.query(f"""
        SELECT
            sum(clicks)      as clicks_30d,
            sum(impressions) as impressions_30d,
            avg(position)    as avg_position_30d
        FROM analytics.rankings_daily
        WHERE project_id = '{project_id}'
          AND date >= today() - 30
    """)

    if result.result_rows:
        row = result.result_rows[0]
        return {
            "clicks_30d": _safe_int(row[0]),
            "impressions_30d": _safe_int(row[1]),
            "avg_position_30d": _safe_float(row[2], 1) or 0.0,
        }
    return {"clicks_30d": 0, "impressions_30d": 0, "avg_position_30d": 0.0}


@router.get("/project/{project_id}/feedback-insights")
async def get_feedback_insights(project_id: UUID):
    """Aggregated edit-type performance from feedback signals."""
    ch = get_ch()
    result = ch.query(f"""
        SELECT
            edit_type,
            avg(position_delta)                          as avg_improvement,
            count(*)                                     as sample_size,
            countIf(position_delta > 0) / count(*)      as success_rate
        FROM analytics.feedback_signals
        WHERE project_id = '{project_id}'
        GROUP BY edit_type
        ORDER BY avg_improvement DESC
    """)
    return [
        {
            "edit_type": row[0],
            "avg_rank_improvement": _safe_float(row[1], 2),
            "sample_size": _safe_int(row[2]),
            "success_rate": _safe_float(row[3], 2),
        }
        for row in result.result_rows
    ]