"""
Speed Audit Worker Tasks for AI SEO Agent System
Celery tasks for running website speed audits
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_async_session
from backend.agents.speed_agent import SpeedAuditAgent
from backend.db.models import Project, Task, TaskStatus, TaskType
from backend.core.logging import get_logger

logger = get_logger(__name__)


@shared_task(
    bind=True,
    name="tasks.speed.run_speed_audit",
    queue="speed",
    max_retries=3,
    default_retry_delay=60,
)
def run_speed_audit_task(
    self,
    project_id: str,
    page_url: str,
    page_id: Optional[str] = None,
    strategy: str = "desktop"
) -> Dict[str, Any]:
    """
    Run a speed audit for a specific URL
    
    Args:
        project_id: Project UUID as string
        page_url: URL to audit
        page_id: Optional page UUID as string
        strategy: 'desktop' or 'mobile'
        
    Returns:
        Audit results dictionary
    """
    import asyncio
    
    async def _run():
        async with get_async_session() as session:
            # Get task record if exists
            task = None
            
            try:
                agent = SpeedAuditAgent()
                
                result = await agent.run_audit(
                    session=session,
                    project_id=UUID(project_id),
                    page_url=page_url,
                    page_id=UUID(page_id) if page_id else None,
                    strategy=strategy
                )
                
                return result
                
            except Exception as e:
                logger.error(f"Speed audit task failed: {str(e)}")
                raise self.retry(exc=e)
    
    return asyncio.run(_run())


@shared_task(
    bind=True,
    name="tasks.speed.run_project_speed_audit",
    queue="speed",
    max_retries=2,
    default_retry_delay=120,
)
def run_project_speed_audit_task(
    self,
    project_id: str,
    strategy: str = "desktop"
) -> Dict[str, Any]:
    """
    Run speed audits for all pages in a project
    
    Args:
        project_id: Project UUID as string
        strategy: 'desktop' or 'mobile'
        
    Returns:
        Summary of audit results
    """
    import asyncio
    
    async def _run():
        async with get_async_session() as session:
            try:
                from sqlalchemy import select
                
                # Get project
                stmt = select(Project).where(Project.id == UUID(project_id))
                result = await session.execute(stmt)
                project = result.scalar_one_or_none()
                
                if not project:
                    return {"success": False, "error": "Project not found"}
                
                agent = SpeedAuditAgent()
                
                results = await agent.run_project_audit(
                    session=session,
                    project=project,
                    strategy=strategy
                )
                
                success_count = sum(1 for r in results if r.get("success"))
                fail_count = len(results) - success_count
                
                return {
                    "success": True,
                    "total_pages": len(results),
                    "successful_audits": success_count,
                    "failed_audits": fail_count,
                    "results": results
                }
                
            except Exception as e:
                logger.error(f"Project speed audit task failed: {str(e)}")
                raise self.retry(exc=e)
    
    return asyncio.run(_run())


@shared_task(
    bind=True,
    name="tasks.speed.sync_core_web_vitals",
    queue="speed",
    max_retries=3,
    default_retry_delay=300,
)
def sync_core_web_vitals_task(
    self,
    project_id: str
) -> Dict[str, Any]:
    """
    Sync Core Web Vitals data from GSC to project pages
    
    Args:
        project_id: Project UUID as string
        
    Returns:
        Sync summary
    """
    import asyncio
    
    async def _run():
        async with get_async_session() as session:
            try:
                from sqlalchemy import select
                
                # Get project
                stmt = select(Project).where(Project.id == UUID(project_id))
                result = await session.execute(stmt)
                project = result.scalar_one_or_none()
                
                if not project:
                    return {"success": False, "error": "Project not found"}
                
                # TODO: Implement GSC Core Web Vitals API integration
                # For now, return placeholder
                return {
                    "success": True,
                    "message": "Core Web Vitals sync completed (placeholder)",
                    "pages_updated": 0
                }
                
            except Exception as e:
                logger.error(f"Core Web Vitals sync task failed: {str(e)}")
                raise self.retry(exc=e)
    
    return asyncio.run(_run())
