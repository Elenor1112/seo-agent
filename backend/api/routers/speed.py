"""
Speed Audit API Router for AI SEO Agent System
Endpoints for running and retrieving speed audits
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_async_session
from backend.db.models import Project, SpeedAudit, Page
from backend.agents.speed_agent import SpeedAuditAgent
from backend.workers.tasks.speed_tasks import run_speed_audit_task, run_project_speed_audit_task
from backend.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/speed", tags=["speed"])


# ── Pydantic Schemas ───────────────────────────────────────────────────────────

from pydantic import BaseModel, Field


class SpeedAuditRequest(BaseModel):
    """Request schema for running a speed audit"""
    url: Optional[str] = None
    page_id: Optional[str] = None
    strategy: str = Field(default="desktop", description="'desktop' or 'mobile'")


class SpeedAuditResponse(BaseModel):
    """Response schema for speed audit results"""
    success: bool
    audit_id: Optional[str] = None
    error: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    recommendations: Optional[List[Dict[str, Any]]] = None


class SpeedMetricsSummary(BaseModel):
    """Summary of speed metrics"""
    performance_score: float
    seo_score: float
    accessibility_score: float
    best_practices_score: float
    lcp: float
    cls: float
    inp: float
    ttfb: float
    total_blocking_time: float


class SpeedHistoryItem(BaseModel):
    """Historical speed audit item"""
    id: str
    page_url: Optional[str]
    performance_score: float
    seo_score: float
    accessibility_score: float
    best_practices_score: float
    lcp: float
    cls: float
    inp: float
    created_at: str


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post("/projects/{project_id}/run", response_model=Dict[str, Any])
async def run_speed_audit(
    project_id: UUID,
    request: SpeedAuditRequest,
    session: AsyncSession = Depends(get_async_session)
):
    """
    Run a speed audit for a project or specific page
    
    - If URL is provided, audits that specific URL
    - If no URL, audits all pages in the project
    """
    # Verify project exists
    from sqlalchemy import select
    stmt = select(Project).where(Project.id == project_id)
    result = await session.execute(stmt)
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        # Specific URL audit
        if request.url:
            task = run_speed_audit_task.delay(
                project_id=str(project_id),
                page_url=request.url,
                page_id=request.page_id,
                strategy=request.strategy
            )
            
            return {
                "success": True,
                "message": "Speed audit queued",
                "task_id": task.id,
                "type": "single_url"
            }
        
        # Project-wide audit
        else:
            task = run_project_speed_audit_task.delay(
                project_id=str(project_id),
                strategy=request.strategy
            )
            
            return {
                "success": True,
                "message": "Project speed audit queued",
                "task_id": task.id,
                "type": "project_wide"
            }
            
    except Exception as e:
        logger.error(f"Failed to queue speed audit: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}", response_model=Dict[str, Any])
async def get_project_speed_audits(
    project_id: UUID,
    limit: int = Query(default=10, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session)
):
    """Get latest speed audits for a project"""
    
    from sqlalchemy import select
    
    # Get latest audits (one per page)
    stmt = (
        select(SpeedAudit)
        .where(SpeedAudit.project_id == project_id)
        .order_by(SpeedAudit.created_at.desc())
        .limit(limit)
    )
    
    result = await session.execute(stmt)
    audits = result.scalars().all()
    
    # Get page URLs for each audit
    audit_list = []
    for audit in audits:
        page_url = None
        if audit.page_id:
            page_stmt = select(Page.url).where(Page.id == audit.page_id)
            page_result = await session.execute(page_stmt)
            page = page_result.scalar_one_or_none()
            page_url = page.url if page else None
        
        audit_list.append({
            "id": str(audit.id),
            "page_id": str(audit.page_id) if audit.page_id else None,
            "page_url": page_url,
            "performance_score": audit.performance_score,
            "seo_score": audit.seo_score,
            "accessibility_score": audit.accessibility_score,
            "best_practices_score": audit.best_practices_score,
            "lcp": audit.lcp,
            "cls": audit.cls,
            "inp": audit.inp,
            "ttfb": audit.ttfb,
            "total_blocking_time": audit.total_blocking_time,
            "recommendations": audit.recommendations,
            "created_at": audit.created_at.isoformat()
        })
    
    # Calculate averages
    if audits:
        avg_metrics = {
            "performance_score": sum(a.performance_score for a in audits) / len(audits),
            "seo_score": sum(a.seo_score for a in audits) / len(audits),
            "accessibility_score": sum(a.accessibility_score for a in audits) / len(audits),
            "best_practices_score": sum(a.best_practices_score for a in audits) / len(audits),
            "lcp": sum(a.lcp for a in audits) / len(audits),
            "cls": sum(a.cls for a in audits) / len(audits),
            "inp": sum(a.inp for a in audits) / len(audits),
            "ttfb": sum(a.ttfb for a in audits) / len(audits),
            "total_blocking_time": sum(a.total_blocking_time for a in audits) / len(audits),
        }
    else:
        avg_metrics = {}
    
    return {
        "success": True,
        "count": len(audit_list),
        "average_metrics": avg_metrics,
        "audits": audit_list
    }


@router.get("/projects/{project_id}/history", response_model=Dict[str, Any])
async def get_speed_history(
    project_id: UUID,
    days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_async_session)
):
    """Get historical speed metrics for trend analysis"""
    
    from sqlalchemy import select, func
    from datetime import datetime, timedelta
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    # Group by date and calculate daily averages
    stmt = (
        select(
            func.date(SpeedAudit.created_at).label('audit_date'),
            func.avg(SpeedAudit.performance_score).label('avg_performance'),
            func.avg(SpeedAudit.lcp).label('avg_lcp'),
            func.avg(SpeedAudit.cls).label('avg_cls'),
            func.avg(SpeedAudit.inp).label('avg_inp'),
            func.count(SpeedAudit.id).label('audit_count')
        )
        .where(
            SpeedAudit.project_id == project_id,
            SpeedAudit.created_at >= cutoff_date
        )
        .group_by(func.date(SpeedAudit.created_at))
        .order_by(func.date(SpeedAudit.created_at))
    )
    
    result = await session.execute(stmt)
    rows = result.fetchall()
    
    history = [
        {
            "date": str(row.audit_date),
            "performance_score": float(row.avg_performance) if row.avg_performance else 0,
            "lcp": float(row.avg_lcp) if row.avg_lcp else 0,
            "cls": float(row.avg_cls) if row.avg_cls else 0,
            "inp": float(row.avg_inp) if row.avg_inp else 0,
            "audit_count": row.audit_count
        }
        for row in rows
    ]
    
    return {
        "success": True,
        "days": days,
        "history": history
    }


@router.get("/pages/{page_id}", response_model=Dict[str, Any])
async def get_page_speed_audit(
    page_id: UUID,
    session: AsyncSession = Depends(get_async_session)
):
    """Get latest speed audit for a specific page"""
    
    from sqlalchemy import select
    
    # Get latest audit for this page
    stmt = (
        select(SpeedAudit)
        .where(SpeedAudit.page_id == page_id)
        .order_by(SpeedAudit.created_at.desc())
        .limit(1)
    )
    
    result = await session.execute(stmt)
    audit = result.scalar_one_or_none()
    
    if not audit:
        return {
            "success": False,
            "message": "No speed audit found for this page"
        }
    
    # Get page URL
    page_stmt = select(Page.url).where(Page.id == page_id)
    page_result = await session.execute(page_stmt)
    page = page_result.scalar_one_or_none()
    
    return {
        "success": True,
        "audit": {
            "id": str(audit.id),
            "page_id": str(audit.page_id),
            "page_url": page.url if page else None,
            "performance_score": audit.performance_score,
            "seo_score": audit.seo_score,
            "accessibility_score": audit.accessibility_score,
            "best_practices_score": audit.best_practices_score,
            "lcp": audit.lcp,
            "cls": audit.cls,
            "inp": audit.inp,
            "ttfb": audit.ttfb,
            "total_blocking_time": audit.total_blocking_time,
            "recommendations": audit.recommendations,
            "created_at": audit.created_at.isoformat()
        }
    }
