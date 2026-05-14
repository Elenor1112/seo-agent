"""Keywords router."""
from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.session import get_db
from db.models import Keyword

router = APIRouter()


@router.get("/project/{project_id}")
async def list_keywords(
    project_id: UUID,
    gaps_only: bool = Query(False),
    min_score: float = Query(0.0),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    query = select(Keyword).where(Keyword.project_id == project_id)
    if gaps_only:
        query = query.where(Keyword.is_gap == True)
    if min_score > 0:
        query = query.where(Keyword.opportunity_score >= min_score)
    query = query.order_by(Keyword.opportunity_score.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    keywords = result.scalars().all()

    return [
        {
            "id": str(k.id),
            "query": k.query,
            "impressions": k.impressions,
            "clicks": k.clicks,
            "ctr": k.ctr,
            "avg_position": k.avg_position,
            "opportunity_score": k.opportunity_score,
            "search_intent": k.search_intent,
            "is_gap": k.is_gap,
            "cluster_label": k.cluster_label,
        }
        for k in keywords
    ]


@router.get("/project/{project_id}/clusters")
async def list_clusters(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """Return distinct keyword clusters with aggregate stats."""
    result = await db.execute(
        select(Keyword.cluster_id, Keyword.cluster_label)
        .where(Keyword.project_id == project_id, Keyword.cluster_id.isnot(None))
        .distinct()
        .limit(100)
    )
    return [{"cluster_id": r[0], "label": r[1]} for r in result.all()]
