from uuid import UUID
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from db.models import Project, ProjectStatus
from agents.orchestrator import OrchestratorAgent

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str
    domain: str
    base_url: str
    brand_voice: Optional[str] = None
    target_audience: Optional[str] = None
    content_language: str = "en"


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    brand_voice: Optional[str] = None
    target_audience: Optional[str] = None
    wp_base_url: Optional[str] = None
    wp_username: Optional[str] = None
    wp_app_password: Optional[str] = None
    gsc_property_url: Optional[str] = None


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    domain: str
    base_url: str
    status: ProjectStatus
    brand_voice: Optional[str]
    target_audience: Optional[str]
    content_language: str
    gsc_property_url: Optional[str]
    wp_base_url: Optional[str]
    has_gsc: bool
    has_wordpress: bool
    created_at: datetime

    class Config:
        from_attributes = True


class RunConfig(BaseModel):
    max_depth: int = 5
    max_pages: int = 500
    date_range_days: int = 480
    country_code: str = "en"
    serp_top_n: int = 10
    max_articles: int = 10
    max_optimize_pages: int = 20


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[ProjectResponse])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    projects = result.scalars().all()
    return [_to_response(p) for p in projects]


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Project).where(Project.domain == body.domain))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Project with this domain already exists")

    project = Project(**body.model_dump())
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return _to_response(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: UUID, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return _to_response(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(project, field, value)

    await db.commit()
    await db.refresh(project)
    return _to_response(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: UUID, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.delete(project)
    await db.commit()


@router.post("/{project_id}/run")
async def run_full_analysis(
    project_id: UUID,
    config: RunConfig = RunConfig(),
    db: AsyncSession = Depends(get_db),
):
    """Kick off a full SEO analysis run for a project."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    orchestrator = OrchestratorAgent(str(project_id))
    result = await orchestrator.run_full_analysis(run_config=config.model_dump())
    return result


@router.post("/{project_id}/run/content")
async def run_content_generation(
    project_id: UUID,
    keyword_ids: list[str],
    db: AsyncSession = Depends(get_db),
):
    """Trigger content generation for specific keyword IDs."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    orchestrator = OrchestratorAgent(str(project_id))
    return await orchestrator.run_content_only(keyword_ids)


@router.post("/{project_id}/run/optimize")
async def run_optimization(
    project_id: UUID,
    page_keyword_pairs: list[dict],
    db: AsyncSession = Depends(get_db),
):
    """Trigger page optimization for specific page+keyword pairs."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    orchestrator = OrchestratorAgent(str(project_id))
    return await orchestrator.run_optimize_only(page_keyword_pairs)


# ── Helper ─────────────────────────────────────────────────────────────────────

def _to_response(p: Project) -> ProjectResponse:
    return ProjectResponse(
        id=p.id,
        name=p.name,
        domain=p.domain,
        base_url=p.base_url,
        status=p.status,
        brand_voice=p.brand_voice,
        target_audience=p.target_audience,
        content_language=p.content_language,
        gsc_property_url=p.gsc_property_url,
        wp_base_url=p.wp_base_url,
        has_gsc=bool(p.gsc_access_token),
        has_wordpress=bool(p.wp_base_url and p.wp_app_password),
        created_at=p.created_at,
    )
