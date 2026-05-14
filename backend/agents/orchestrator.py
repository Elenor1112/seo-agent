"""
Orchestrator Agent
==================
Entry point for all SEO runs. Decomposes a domain analysis request into
a DAG of tasks, pushes them to the correct Celery queues, and tracks
completion to gate downstream work.

Inputs:  project_id, run_config
Outputs: Task records in PostgreSQL, triggers all downstream agents
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from core.logging import get_logger
from db.models import Project, Task, TaskStatus, TaskType
from db.worker_session import create_worker_session_factory

logger = get_logger("orchestrator")


class OrchestratorAgent:
    """
    Coordinates a full SEO analysis run for a project.
    Creates task records and dispatches Celery tasks in the correct order.
    """

    def __init__(self, project_id: str) -> None:
        self.project_id = project_id

    # ── Main entry point ───────────────────────────────────────────────────

    async def run_full_analysis(self, run_config: Optional[dict] = None) -> dict:
        """Kick off a complete SEO analysis run for the project."""
        config = run_config or {}
        logger.info("orchestrator.start", project_id=self.project_id)

        SessionLocal = create_worker_session_factory()
        async with SessionLocal() as session:
            project = await session.get(Project, self.project_id)
            if not project:
                raise ValueError(f"Project {self.project_id} not found")

        # Step 1: Create the root task DAG
        crawl_task = await self._create_task(TaskType.crawl, payload={
            "max_depth": config.get("max_depth", 5),
            "max_pages": config.get("max_pages", 500),
        }, priority=1)

        keyword_task = await self._create_task(TaskType.keywords, payload={
            "date_range_days": config.get("date_range_days", 480),
        }, parent_task_id=crawl_task, priority=2)

        serp_task = await self._create_task(TaskType.serp, payload={
            "country_code": config.get("country_code", "en"),
            "top_n": config.get("serp_top_n", 10),
        }, parent_task_id=keyword_task, priority=2)

        content_task = await self._create_task(TaskType.content_generate, payload={
            "max_articles": config.get("max_articles", 10),
        }, parent_task_id=serp_task, priority=3)

        optimize_task = await self._create_task(TaskType.content_optimize, payload={
            "max_pages": config.get("max_optimize_pages", 20),
        }, parent_task_id=serp_task, priority=3)

        # Step 2: Dispatch the first task — crawl (others are chained in Celery)
        await self._dispatch_crawl(crawl_task, keyword_task, serp_task, content_task, optimize_task)

        logger.info("orchestrator.dispatched", crawl_task=str(crawl_task))
        return {
            "run_id": str(crawl_task),
            "tasks": {
                "crawl": str(crawl_task),
                "keywords": str(keyword_task),
                "serp": str(serp_task),
                "content_generate": str(content_task),
                "content_optimize": str(optimize_task),
            },
            "status": "dispatched",
        }

    async def run_content_only(self, keyword_ids: list[str]) -> dict:
        """Trigger content generation for specific keyword IDs."""
        tasks = []
        for kw_id in keyword_ids:
            task_id = await self._create_task(TaskType.content_generate, payload={
                "keyword_id": kw_id,
            }, priority=2)
            tasks.append(str(task_id))

        from workers.tasks.content_tasks import generate_content_task
        for i, kw_id in enumerate(keyword_ids):
            generate_content_task.apply_async(
                args=[self.project_id, kw_id, tasks[i]],
                queue="content",
            )

        return {"tasks_dispatched": len(tasks), "task_ids": tasks}

    async def run_optimize_only(self, page_keyword_pairs: list[dict]) -> dict:
        """Trigger optimizer for specific page+keyword pairs."""
        tasks = []
        for pair in page_keyword_pairs:
            task_id = await self._create_task(TaskType.content_optimize, payload=pair, priority=2)
            tasks.append(str(task_id))

        from workers.tasks.content_tasks import optimize_content_task
        for i, pair in enumerate(page_keyword_pairs):
            optimize_content_task.apply_async(
                args=[self.project_id, pair["page_id"], pair["keyword_id"], tasks[i]],
                queue="optimize",
            )

        return {"tasks_dispatched": len(tasks), "task_ids": tasks}

    # ── Task creation ──────────────────────────────────────────────────────

    async def _create_task(
        self,
        task_type: TaskType,
        payload: Optional[dict] = None,
        parent_task_id: Optional[uuid.UUID] = None,
        priority: int = 3,
    ) -> uuid.UUID:
        SessionLocal = create_worker_session_factory()
        async with SessionLocal() as session:
            task = Task(
                project_id=self.project_id,
                parent_task_id=parent_task_id,
                task_type=task_type,
                status=TaskStatus.pending,
                priority=priority,
                payload=payload or {},
            )
            session.add(task)
            await session.commit()
            await session.refresh(task)
            return task.id

    # ── Dispatch ───────────────────────────────────────────────────────────

    async def _dispatch_crawl(
        self,
        crawl_task_id: uuid.UUID,
        keyword_task_id: uuid.UUID,
        serp_task_id: uuid.UUID,
        content_task_id: uuid.UUID,
        optimize_task_id: uuid.UUID,
    ) -> None:
        from workers.tasks.crawl_tasks import run_crawl_task
        run_crawl_task.apply_async(
            args=[
                self.project_id,
                str(crawl_task_id),
                str(keyword_task_id),
                str(serp_task_id),
                str(content_task_id),
                str(optimize_task_id),
            ],
            queue="crawl",
            priority=1,
            task_id=str(crawl_task_id),
        )
