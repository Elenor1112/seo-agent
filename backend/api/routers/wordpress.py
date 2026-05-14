"""WordPress router - connection testing and post management."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from db.session import get_db
from db.models import Project

router = APIRouter()


class WPCredentials(BaseModel):
    wp_base_url: str
    wp_username: str
    wp_app_password: str


@router.post("/project/{project_id}/test")
async def test_wordpress_connection(
    project_id: UUID,
    creds: WPCredentials,
    db: AsyncSession = Depends(get_db),
):
    """Test WordPress credentials before saving."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Temporarily set creds for testing
    project.wp_base_url = creds.wp_base_url
    project.wp_username = creds.wp_username
    project.wp_app_password = creds.wp_app_password

    from integrations.wordpress.client import WordPressClient
    try:
        wp = WordPressClient(project)
        connected = await wp.test_connection()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if connected:
        # Save credentials
        await db.commit()
        return {"status": "connected", "message": "WordPress credentials saved"}
    else:
        await db.rollback()
        raise HTTPException(status_code=401, detail="Could not authenticate with WordPress")
