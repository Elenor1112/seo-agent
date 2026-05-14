"""
Export API Router for AI SEO Agent System
Endpoints for exporting content in various formats
"""

import logging
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_async_session
from backend.services.export_service import ExportService
from backend.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/content", tags=["export"])


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get("/{content_id}/export")
async def export_content(
    content_id: UUID,
    format: str = Query(default="json", description="Export format: pdf, docx, md, html, json"),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Export content in specified format
    
    Supported formats:
    - json: Structured JSON with metadata
    - md: Markdown with frontmatter
    - html: Styled HTML document
    - docx: Microsoft Word document
    - pdf: PDF document (print-ready)
    """
    # Validate format
    valid_formats = ["pdf", "docx", "md", "html", "json"]
    if format.lower() not in valid_formats:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid format. Supported formats: {', '.join(valid_formats)}"
        )
    
    try:
        service = ExportService()
        
        result = await service.export_content(
            session=session,
            content_id=content_id,
            format=format.lower()
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Export failed"))
        
        # Return download URL
        return {
            "success": True,
            "download_url": result["url"],
            "filename": result["filename"],
            "format": format,
            "content_id": str(content_id)
        }
        
    except ImportError as e:
        logger.error(f"Export library missing: {str(e)}")
        raise HTTPException(
            status_code=501, 
            detail=f"Export format not available: {str(e)}"
        )
        
    except Exception as e:
        logger.error(f"Export failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
