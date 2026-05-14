"""Celery tasks for the SERP agent."""
import asyncio
from datetime import datetime, timezone

from workers.celery_app import celery_app
from core.logging import get_logger
from db.models import TaskStatus

logger = get_logger("task.serp")


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="workers.tasks.serp_tasks.run_serp_task",
    max_retries=3,
    default_retry_delay=120,
    queue="serp",
)
def run_serp_task(self, project_id, task_id, content_task_id, optimize_task_id):
    async def _run():
        from agents.serp_agent import SerpAgent
        from db.worker_session import create_worker_session_factory
        from db.models import Task, Keyword
        from sqlalchemy import select

        SessionLocal = create_worker_session_factory()

        async with SessionLocal() as session:
            task = await session.get(Task, task_id)
            task.status = TaskStatus.running
            task.started_at = datetime.now(timezone.utc)
            await session.commit()

            # Prefer GSC gap keywords (real ranking opportunities).
            # Fall back to top keywords by opportunity score when none exist
            # (e.g. crawl-derived keywords which have no GSC position data).
            result = await session.execute(
                select(Keyword.id)
                .where(
                    Keyword.project_id == project_id,
                    Keyword.is_gap == True,
                )
                .order_by(Keyword.opportunity_score.desc())
                .limit(50)
            )
            keyword_ids = [str(row[0]) for row in result.all()]

            if not keyword_ids:
                logger.info(
                    "serp_task.no_gaps_fallback",
                    project_id=str(project_id),
                    reason="no gap keywords found, using top opportunity keywords",
                )
                result = await session.execute(
                    select(Keyword.id)
                    .where(Keyword.project_id == project_id)
                    .order_by(Keyword.opportunity_score.desc())
                    .limit(50)
                )
                keyword_ids = [str(row[0]) for row in result.all()]

        logger.info("serp_task.keyword_ids", count=len(keyword_ids))

        try:
            agent = SerpAgent(project_id)
            country_code = (task.payload or {}).get("country_code", "en")
            result = await agent.run(keyword_ids=keyword_ids, country_code=country_code)

            async with SessionLocal() as session:
                task = await session.get(Task, task_id)
                task.status = TaskStatus.completed
                task.result = result
                task.completed_at = datetime.now(timezone.utc)
                await session.commit()
            return result
        except Exception as exc:
            async with SessionLocal() as session:
                task = await session.get(Task, task_id)
                task.status = TaskStatus.failed
                task.error = str(exc)
                await session.commit()
            raise
        finally:
            await SessionLocal.kw["bind"].dispose()

    try:
        result = _run_async(_run())
        from workers.tasks.content_tasks import generate_bulk_content_task, run_bulk_optimize_task
        generate_bulk_content_task.apply_async(
            args=[project_id, content_task_id],
            queue="content",
        )
        run_bulk_optimize_task.apply_async(
            args=[project_id, optimize_task_id],
            queue="optimize",
        )
        return result
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(
    name="workers.tasks.serp_tasks.fetch_serp_data",
    queue="serp",
)
def fetch_serp_data(project_id: str, keyword_id: str):
    """Single keyword SERP fetch (used for on-demand requests)."""
    async def _run():
        from agents.serp_agent import SerpAgent
        agent = SerpAgent(project_id)
        return await agent.run(keyword_ids=[keyword_id])
    return _run_async(_run())