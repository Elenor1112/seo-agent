"""
Ratings API Router for AI SEO Agent System
Endpoints for SEO scoring and ratings
"""

import logging
from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_async_session
from backend.db.models import Project, ProjectScore
from backend.services.rating_engine import RatingEngine
from backend.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/ratings", tags=["ratings"])


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post("/projects/{project_id}/calculate")
async def calculate_project_score(
    project_id: UUID,
    session: AsyncSession = Depends(get_async_session)
):
    """
    Calculate overall SEO score for a project
    
    Scoring weights:
    - Technical SEO: 25%
    - Speed/Core Web Vitals: 25%
    - Content Quality: 20%
    - Keyword Rankings: 15%
    - Backlink/Profile Signals: 10%
    - Structured Data: 5%
    """
    # Verify project exists
    from sqlalchemy import select
    stmt = select(Project).where(Project.id == project_id)
    result = await session.execute(stmt)
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        engine = RatingEngine()
        
        result = await engine.calculate_project_score(
            session=session,
            project_id=project_id
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Score calculation failed"))
        
        return result
        
    except Exception as e:
        logger.error(f"Score calculation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/score")
async def get_project_score(
    project_id: UUID,
    session: AsyncSession = Depends(get_async_session)
):
    """Get latest SEO score for a project"""
    
    from sqlalchemy import select
    
    # Get latest score
    stmt = (
        select(ProjectScore)
        .where(ProjectScore.project_id == project_id)
        .order_by(ProjectScore.created_at.desc())
        .limit(1)
    )
    
    result = await session.execute(stmt)
    score = result.scalar_one_or_none()
    
    if not score:
        return {
            "success": False,
            "message": "No score calculated yet. Run calculation first."
        }
    
    return {
        "success": True,
        "score": {
            "id": str(score.id),
            "overall_score": score.overall_score,
            "grade": score.grade,
            "category_scores": {
                "technical": score.technical_score,
                "speed": score.speed_score,
                "content": score.content_score,
                "keyword": score.keyword_score,
                "schema": score.schema_score,
                "backlink": score.backlink_score,
            },
            "recommendations": score.recommendations,
            "created_at": score.created_at.isoformat()
        }
    }


@router.get("/projects/{project_id}/score/history")
async def get_score_history(
    project_id: UUID,
    days: int = Query(default=90, ge=1, le=365),
    session: AsyncSession = Depends(get_async_session)
):
    """Get historical SEO scores for trend analysis"""
    
    from sqlalchemy import select, func
    from datetime import datetime, timedelta
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    # Get scores within date range
    stmt = (
        select(ProjectScore)
        .where(
            ProjectScore.project_id == project_id,
            ProjectScore.created_at >= cutoff_date
        )
        .order_by(ProjectScore.created_at.asc())
    )
    
    result = await session.execute(stmt)
    scores = result.scalars().all()
    
    history = [
        {
            "id": str(score.id),
            "overall_score": score.overall_score,
            "grade": score.grade,
            "technical_score": score.technical_score,
            "speed_score": score.speed_score,
            "content_score": score.content_score,
            "keyword_score": score.keyword_score,
            "schema_score": score.schema_score,
            "backlink_score": score.backlink_score,
            "created_at": score.created_at.isoformat()
        }
        for score in scores
    ]
    
    return {
        "success": True,
        "days": days,
        "count": len(history),
        "history": history
    }
