"""Tasks router - job status polling."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.session import get_db
from db.models import Task

router = APIRouter()


@router.get("/{task_id}")
async def get_task(task_id: UUID, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "id": str(task.id),
        "task_type": task.task_type,
        "status": task.status,
        "result": task.result,
        "error": task.error,
        "retries": task.retries,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
        "created_at": task.created_at,
    }


@router.get("/project/{project_id}")
async def list_project_tasks(project_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Task)
        .where(Task.project_id == project_id)
        .order_by(Task.created_at.desc())
        .limit(50)
    )
    tasks = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "task_type": t.task_type,
            "status": t.status,
            "priority": t.priority,
            "started_at": t.started_at,
            "completed_at": t.completed_at,
            "created_at": t.created_at,
        }
        for t in tasks
    ]
