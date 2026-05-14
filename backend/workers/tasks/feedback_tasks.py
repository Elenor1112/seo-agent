"""Celery tasks for the feedback loop agent."""
import asyncio
from workers.celery_app import celery_app
from core.logging import get_logger

logger = get_logger("task.feedback")


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="workers.tasks.feedback_tasks.run_feedback_analysis", queue="optimize")
def run_feedback_analysis():
    """Scheduled weekly: run feedback loop analysis for all projects."""
    async def _run():
        from agents.feedback_agent import FeedbackLoopAgent
        from db.worker_session import create_worker_session_factory
        from db.models import Project
        from sqlalchemy import select

        SessionLocal = create_worker_session_factory()

        async with SessionLocal() as session:
            result = await session.execute(select(Project))
            projects = result.scalars().all()

        agent = FeedbackLoopAgent()
        results = {}
        for project in projects:
            try:
                results[str(project.id)] = await agent.run_for_project(str(project.id))
            except Exception as exc:
                logger.error("feedback.error", project=str(project.id), error=str(exc))

        await SessionLocal.kw["bind"].dispose()
        return results

    return _run_async(_run())


@celery_app.task(name="workers.tasks.feedback_tasks.run_project_feedback", queue="optimize")
def run_project_feedback(project_id: str):
    async def _run():
        from agents.feedback_agent import FeedbackLoopAgent
        agent = FeedbackLoopAgent()
        return await agent.run_for_project(project_id)
    return _run_async(_run())
