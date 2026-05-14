"""Celery tasks for the Crawler agent."""
import asyncio
from datetime import datetime, timezone

from workers.celery_app import celery_app
from core.logging import get_logger
from db.models import TaskStatus, TaskType

logger = get_logger("task.crawl")


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="workers.tasks.crawl_tasks.run_crawl_task",
    max_retries=3,
    default_retry_delay=60,
    queue="crawl",
)
def run_crawl_task(
    self,
    project_id: str,
    task_id: str,
    keyword_task_id: str,
    serp_task_id: str,
    content_task_id: str,
    optimize_task_id: str,
):
    """Run the crawler agent and chain downstream tasks on success."""
    logger.info("task.crawl.start", project_id=project_id, task_id=task_id)

    async def _run():
        from agents.crawler_agent import CrawlerAgent
        from db.worker_session import create_worker_session_factory
        from db.models import Project, Task

        SessionLocal = create_worker_session_factory()

        async with SessionLocal() as session:
            project = await session.get(Project, project_id)
            task = await session.get(Task, task_id)
            if not project or not task:
                return

            task.status = TaskStatus.running
            task.started_at = datetime.now(timezone.utc)
            task.celery_task_id = self.request.id
            await session.commit()

        try:
            agent = CrawlerAgent(project)
            payload = task.payload or {}
            result = await agent.run(
                max_depth=payload.get("max_depth", 5),
                max_pages=payload.get("max_pages", 500),
            )

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
        # Chain keyword task
        from workers.tasks.keyword_tasks import run_keyword_task
        run_keyword_task.apply_async(
            args=[project_id, keyword_task_id, serp_task_id, content_task_id, optimize_task_id],
            queue="keywords",
        )
        return result
    except Exception as exc:
        logger.error("task.crawl.error", error=str(exc))
        raise self.retry(exc=exc)
