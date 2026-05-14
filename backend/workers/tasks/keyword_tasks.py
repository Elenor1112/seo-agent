"""Celery tasks for the Keyword agent."""
import asyncio
from datetime import datetime, timezone

from workers.celery_app import celery_app
from core.logging import get_logger
from db.models import TaskStatus

logger = get_logger("task.keywords")


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="workers.tasks.keyword_tasks.run_keyword_task",
    max_retries=3,
    default_retry_delay=120,
    queue="keywords",
)
def run_keyword_task(self, project_id, task_id, serp_task_id, content_task_id, optimize_task_id):
    async def _run():
        from agents.keyword_agent import KeywordAgent
        from db.worker_session import create_worker_session_factory
        from db.models import Project, Task

        SessionLocal = create_worker_session_factory()

        async with SessionLocal() as session:
            project = await session.get(Project, project_id)
            task = await session.get(Task, task_id)
            task.status = TaskStatus.running
            task.started_at = datetime.now(timezone.utc)
            await session.commit()

        payload = task.payload or {}

        try:
            agent = KeywordAgent(project)
            result = await agent.run(
                date_range_days=payload.get("date_range_days", 480),
                # Optional seed keywords passed when triggering a run.
                # e.g. POST /projects/{id}/run with body {"seed_keywords": ["seo tools", ...]}
                seed_keywords=payload.get("seed_keywords"),
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
        from workers.tasks.serp_tasks import run_serp_task
        run_serp_task.apply_async(
            args=[project_id, serp_task_id, content_task_id, optimize_task_id],
            queue="serp",
        )
        return result
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="workers.tasks.keyword_tasks.refresh_all_gsc_data",
    queue="keywords",
)
def refresh_all_gsc_data(self):
    """Scheduled task: refresh GSC data for all active projects."""
    async def _run():
        from db.worker_session import create_worker_session_factory
        from db.models import Project
        from sqlalchemy import select
        from agents.keyword_agent import KeywordAgent

        SessionLocal = create_worker_session_factory()

        async with SessionLocal() as session:
            result = await session.execute(
                select(Project).where(Project.gsc_access_token.isnot(None))
            )
            projects = result.scalars().all()

        for project in projects:
            try:
                agent = KeywordAgent(project)
                await agent.run(date_range_days=90)
            except Exception as exc:
                logger.error("refresh_gsc.error", project=str(project.id), error=str(exc))

        await SessionLocal.kw["bind"].dispose()

    _run_async(_run())