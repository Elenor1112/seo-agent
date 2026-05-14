"""Celery tasks for tracker and feedback loop agents."""
import asyncio
from workers.celery_app import celery_app
from core.logging import get_logger

logger = get_logger("task.tracker")


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="workers.tasks.tracker_tasks.run_daily_tracker", queue="tracker")
def run_daily_tracker():
    """Scheduled: run performance tracker for all projects."""
    async def _run():
        from agents.tracker_agent import TrackerAgent
        agent = TrackerAgent()
        return await agent.run_all_projects()
    return _run_async(_run())


@celery_app.task(name="workers.tasks.tracker_tasks.track_project", queue="tracker")
def track_project(project_id: str):
    """Track a single project on demand."""
    async def _run():
        from agents.tracker_agent import TrackerAgent
        agent = TrackerAgent()
        return await agent.run_for_project(project_id)
    return _run_async(_run())
