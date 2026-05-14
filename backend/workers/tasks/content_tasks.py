"""Celery tasks for content generation and optimization agents."""
import asyncio
from datetime import datetime, timezone

from workers.celery_app import celery_app
from core.logging import get_logger
from db.models import TaskStatus

logger = get_logger("task.content")


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Content Generation ─────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="workers.tasks.content_tasks.generate_content_task",
    max_retries=2,
    default_retry_delay=60,
    queue="content",
)
def generate_content_task(self, project_id: str, keyword_id: str, task_id: str):
    """Generate content for a single keyword."""
    async def _run():
        from agents.content_gen_agent import ContentGenAgent
        from db.worker_session import create_worker_session_factory
        from db.models import Project, Task

        SessionLocal = create_worker_session_factory()

        async with SessionLocal() as session:
            project = await session.get(Project, project_id)
            task = await session.get(Task, task_id)
            if task:
                task.status = TaskStatus.running
                task.started_at = datetime.now(timezone.utc)
                await session.commit()

        try:
            agent = ContentGenAgent(project)
            result = await agent.run(keyword_id=keyword_id)

            if task_id:
                async with SessionLocal() as session:
                    task = await session.get(Task, task_id)
                    if task:
                        task.status = TaskStatus.completed
                        task.result = result
                        task.completed_at = datetime.now(timezone.utc)
                        await session.commit()
            return result
        except Exception as exc:
            if task_id:
                async with SessionLocal() as session:
                    task = await session.get(Task, task_id)
                    if task:
                        task.status = TaskStatus.failed
                        task.error = str(exc)
                        await session.commit()
            raise
        finally:
            await SessionLocal.kw["bind"].dispose()

    try:
        return _run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="workers.tasks.content_tasks.generate_bulk_content_task",
    queue="content",
)
def generate_bulk_content_task(self, project_id: str, task_id: str):
    """Generate content for top N gap keywords after SERP analysis."""
    async def _run():
        from db.worker_session import create_worker_session_factory
        from db.models import Project, Task, Keyword, SerpSnapshot
        from sqlalchemy import select

        SessionLocal = create_worker_session_factory()

        async with SessionLocal() as session:
            task = await session.get(Task, task_id)
            if task:
                task.status = TaskStatus.running
                task.started_at = datetime.now(timezone.utc)
                await session.commit()

            max_articles = (task.payload or {}).get("max_articles", 10) if task else 10

            # Keywords with SERP data and high opportunity scores
            result = await session.execute(
                select(Keyword)
                .where(
                    Keyword.project_id == project_id,
                     )     
                .order_by(Keyword.opportunity_score.desc())
                .limit(max_articles)
            )   
            keywords = result.scalars().all()
            project = await session.get(Project, project_id)

        generated = []
        for kw in keywords:
            try:
                from agents.content_gen_agent import ContentGenAgent
                agent = ContentGenAgent(project)
                result = await agent.run(keyword_id=str(kw.id))
                generated.append(result)
                logger.info("bulk_content.generated", keyword=kw.query)
            except Exception as exc:
                logger.error("bulk_content.error", keyword=kw.query, error=str(exc))

        async with SessionLocal() as session:
            task = await session.get(Task, task_id)
            if task:
                task.status = TaskStatus.completed
                task.result = {"generated": len(generated), "keywords": [g["keyword"] for g in generated]}
                task.completed_at = datetime.now(timezone.utc)
                await session.commit()

        await SessionLocal.kw["bind"].dispose()
        return {"generated": len(generated)}

    return _run_async(_run())


# ── Content Optimization ───────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="workers.tasks.content_tasks.optimize_content_task",
    max_retries=2,
    default_retry_delay=60,
    queue="optimize",
)
def optimize_content_task(self, project_id: str, page_id: str, keyword_id: str, task_id: str):
    """Generate optimization edit-set for a single page."""
    async def _run():
        from agents.optimizer_agent import ContentOptimizerAgent
        from db.worker_session import create_worker_session_factory
        from db.models import Project, Task

        SessionLocal = create_worker_session_factory()

        async with SessionLocal() as session:
            project = await session.get(Project, project_id)
            task = await session.get(Task, task_id)
            if task:
                task.status = TaskStatus.running
                task.started_at = datetime.now(timezone.utc)
                await session.commit()

        try:
            agent = ContentOptimizerAgent(project)
            result = await agent.run(page_id=page_id, keyword_id=keyword_id)

            if task_id:
                async with SessionLocal() as session:
                    task = await session.get(Task, task_id)
                    if task:
                        task.status = TaskStatus.completed
                        task.result = result
                        task.completed_at = datetime.now(timezone.utc)
                        await session.commit()
            return result
        except Exception as exc:
            if task_id:
                async with SessionLocal() as session:
                    task = await session.get(Task, task_id)
                    if task:
                        task.status = TaskStatus.failed
                        task.error = str(exc)
                        await session.commit()
            raise
        finally:
            await SessionLocal.kw["bind"].dispose()

    try:
        return _run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="workers.tasks.content_tasks.run_bulk_optimize_task",
    queue="optimize",
)
def run_bulk_optimize_task(self, project_id: str, task_id: str):
    """Optimize top ranking pages (position 11-30) with SERP data."""
    async def _run():
        from db.worker_session import create_worker_session_factory
        from db.models import Project, Task, Page, Keyword
        from sqlalchemy import select, and_

        SessionLocal = create_worker_session_factory()

        async with SessionLocal() as session:
            task = await session.get(Task, task_id)
            if task:
                task.status = TaskStatus.running
                task.started_at = datetime.now(timezone.utc)
                await session.commit()

            max_pages = (task.payload or {}).get("max_pages", 20) if task else 20
            project = await session.get(Project, project_id)

            # Pages that need optimization (ranking 8-30, not recently optimized)
            kw_result = await session.execute(
                select(Keyword)
                .where(
                    Keyword.project_id == project_id,
                )
                .order_by(Keyword.opportunity_score.desc())
                .limit(max_pages)
            )
            keywords = kw_result.scalars().all()

        optimized = []
        for kw in keywords:
            try:
                # Find the best matching page for this keyword
                async with SessionLocal() as session:
                    page_result = await session.execute(
                        select(Page)
                        .where(
                            Page.project_id == project_id,
                            Page.is_indexable == True,
                        )
                        .order_by(Page.word_count.desc())
                        .limit(1)
                    )
                    page = page_result.scalar_one_or_none()

                if not page:
                    continue

                from agents.optimizer_agent import ContentOptimizerAgent
                agent = ContentOptimizerAgent(project)
                result = await agent.run(page_id=str(page.id), keyword_id=str(kw.id))
                optimized.append(result)
            except Exception as exc:
                logger.error("bulk_optimize.error", keyword=kw.query, error=str(exc))

        async with SessionLocal() as session:
            task = await session.get(Task, task_id)
            if task:
                task.status = TaskStatus.completed
                task.result = {"optimized": len(optimized)}
                task.completed_at = datetime.now(timezone.utc)
                await session.commit()

        await SessionLocal.kw["bind"].dispose()
        return {"optimized": len(optimized)}

    return _run_async(_run())
