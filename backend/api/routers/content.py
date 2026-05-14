"""Content router - manage content versions and approval workflow."""
from uuid import UUID
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from db.models import ContentVersion, ContentStatus, Project
from services.storage import StorageService

router = APIRouter()
storage = StorageService()


class ApproveRequest(BaseModel):
    approved_by: str = "human_editor"


class PublishRequest(BaseModel):
    wp_status: str = "draft"  # draft | publish


@router.get("/project/{project_id}")
async def list_content_versions(
    project_id: UUID,
    status: Optional[str] = Query(None),
    content_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(ContentVersion).where(ContentVersion.project_id == project_id)
    if status:
        query = query.where(ContentVersion.status == status)
    if content_type:
        query = query.where(ContentVersion.content_type == content_type)
    query = query.order_by(ContentVersion.created_at.desc()).limit(limit)

    result = await db.execute(query)
    versions = result.scalars().all()

    return [
        {
            "id": str(v.id),
            "title": v.title,
            "target_keyword": v.target_keyword,
            "status": v.status,
            "content_type": v.content_type,
            "word_count": v.word_count,
            "semantic_score": v.semantic_score,
            "wp_post_id": v.wp_post_id,
            "created_at": v.created_at,
        }
        for v in versions
    ]


@router.get("/{version_id}")
async def get_content_version(version_id: UUID, db: AsyncSession = Depends(get_db)):
    version = await db.get(ContentVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Content version not found")

    # Load full content from S3
    content_data = None
    if version.s3_key:
        content_data = await storage.get_json(version.s3_key)

    return {
        "id": str(version.id),
        "title": version.title,
        "meta_description": version.meta_description,
        "slug": version.slug,
        "target_keyword": version.target_keyword,
        "secondary_keywords": version.secondary_keywords,
        "status": version.status,
        "content_type": version.content_type,
        "word_count": version.word_count,
        "semantic_score": version.semantic_score,
        "generation_meta": version.generation_meta,
        "wp_post_id": version.wp_post_id,
        "published_at": version.published_at,
        "rank_at_publish": version.rank_at_publish,
        "rank_30d": version.rank_30d,
        "rank_delta_30d": version.rank_delta_30d,
        "content": content_data,
        "created_at": version.created_at,
    }


@router.post("/{version_id}/approve")
async def approve_content(
    version_id: UUID,
    body: ApproveRequest,
    db: AsyncSession = Depends(get_db),
):
    version = await db.get(ContentVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Content version not found")
    if version.status not in (ContentStatus.draft, ContentStatus.review):
        raise HTTPException(status_code=400, detail=f"Cannot approve content in status: {version.status}")

    version.status = ContentStatus.approved
    version.approved_by = body.approved_by
    await db.commit()
    return {"status": "approved", "version_id": str(version_id)}


@router.post("/{version_id}/reject")
async def reject_content(version_id: UUID, db: AsyncSession = Depends(get_db)):
    version = await db.get(ContentVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Content version not found")
    version.status = ContentStatus.rejected
    await db.commit()
    return {"status": "rejected"}


@router.post("/{version_id}/publish")
async def publish_to_wordpress(
    version_id: UUID,
    body: PublishRequest,
    db: AsyncSession = Depends(get_db),
):
    """Publish an approved content version to WordPress."""
    version = await db.get(ContentVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Content version not found")
    if version.status != ContentStatus.approved:
        raise HTTPException(status_code=400, detail="Content must be approved before publishing")

    project = await db.get(Project, version.project_id)
    if not project or not project.wp_base_url:
        raise HTTPException(status_code=400, detail="WordPress not configured for this project")

    # Load content from S3
    content_data = await storage.get_json(version.s3_key)
    if not content_data:
        raise HTTPException(status_code=404, detail="Content data not found in storage")

    from integrations.wordpress.client import WordPressClient
    wp = WordPressClient(project)
    result = await wp.publish_content_version(version, content_data, status=body.wp_status)

    # Update version record
    version.wp_post_id = result["wp_post_id"]
    version.status = ContentStatus.published
    version.published_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "status": "published",
        "wp_post_id": result["wp_post_id"],
        "wp_post_url": result.get("wp_post_url"),
    }
