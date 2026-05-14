"""Auth router - Google Search Console OAuth2 flow."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from db.session import get_db
from db.models import Project
from integrations.gsc.client import get_oauth_url, exchange_code_for_tokens

router = APIRouter()


@router.get("/gsc/connect/{project_id}")
async def gsc_connect(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """Redirect user to Google OAuth2 consent screen."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Store project_id in state for callback
    import base64, json
    state = base64.b64encode(json.dumps({"project_id": str(project_id)}).encode()).decode()
    url = get_oauth_url() + f"&state={state}"
    return {"oauth_url": url}


@router.get("/gsc/callback")
async def gsc_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle OAuth2 callback, save tokens, redirect to dashboard."""
    import base64, json
    try:
        state_data = json.loads(base64.b64decode(state).decode())
        project_id = state_data["project_id"]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    result = await exchange_code_for_tokens(code=code, project_id=project_id)
    return RedirectResponse(url=f"http://localhost:3000/projects/{project_id}?gsc=connected")


@router.delete("/gsc/disconnect/{project_id}")
async def gsc_disconnect(project_id: UUID, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project.gsc_access_token = None
    project.gsc_refresh_token = None
    project.gsc_token_expiry = None
    await db.commit()
    return {"status": "disconnected"}
