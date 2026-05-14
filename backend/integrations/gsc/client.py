"""
Google Search Console API Client
=================================
Handles OAuth2 token refresh and exposes query-level performance data.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import httpx
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from core.config import settings
from core.logging import get_logger
from db.models import Project
from db.worker_session import create_worker_session_factory

logger = get_logger("gsc_client")

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


class GSCClient:
    def __init__(self, project: Project) -> None:
        self.project = project

    def _get_credentials(self) -> Credentials:
        creds = Credentials(
            token=self.project.gsc_access_token,
            refresh_token=self.project.gsc_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.gsc_client_id,
            client_secret=settings.gsc_client_secret,
            scopes=SCOPES,
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Persist refreshed token
            import asyncio
            asyncio.create_task(self._save_refreshed_token(creds))
        return creds

    async def _save_refreshed_token(self, creds: Credentials) -> None:
        SessionLocal = create_worker_session_factory()
        async with SessionLocal() as session:
            project = await session.get(Project, self.project.id)
            if project:
                project.gsc_access_token = creds.token
                project.gsc_token_expiry = creds.expiry
                await session.commit()

    async def fetch_queries(
        self,
        start_date: str,
        end_date: str,
        row_limit: int = 25000,
        dimensions: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Fetch query-level data from GSC Search Analytics API.
        Returns list of {query, impressions, clicks, ctr, position}.
        """
        if not self.project.gsc_property_url:
            logger.warning("gsc.no_property_url", project=str(self.project.id))
            return []

        dims = dimensions or ["query"]
        creds = self._get_credentials()

        # Use httpx for async-compatible call
        token = creds.token
        property_url = self.project.gsc_property_url

        url = (
            f"https://searchconsole.googleapis.com/v1/sites/"
            f"{property_url.replace('/', '%2F').replace(':', '%3A')}"
            f"/searchAnalytics/query"
        )

        body = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": dims,
            "rowLimit": row_limit,
            "dataState": "final",
        }

        all_rows: list[dict] = []
        start_row = 0

        async with httpx.AsyncClient(timeout=60) as client:
            while True:
                body["startRow"] = start_row
                resp = await client.post(
                    url,
                    json=body,
                    headers={"Authorization": f"Bearer {token}"},
                )

                if resp.status_code == 401:
                    logger.error("gsc.auth_error", project=str(self.project.id))
                    break

                if resp.status_code != 200:
                    logger.error("gsc.api_error", status=resp.status_code, body=resp.text[:500])
                    break

                data = resp.json()
                rows = data.get("rows", [])
                if not rows:
                    break

                for row in rows:
                    keys = row.get("keys", [])
                    all_rows.append({
                        "query": keys[0] if keys else "",
                        "impressions": row.get("impressions", 0),
                        "clicks": row.get("clicks", 0),
                        "ctr": row.get("ctr", 0.0),
                        "position": row.get("position", 100.0),
                    })

                if len(rows) < row_limit:
                    break  # No more pages
                start_row += row_limit

        logger.info("gsc.fetched", rows=len(all_rows), project=str(self.project.id))
        return all_rows

    async def fetch_pages(
        self,
        start_date: str,
        end_date: str,
        row_limit: int = 5000,
    ) -> list[dict]:
        """Fetch page-level performance data."""
        return await self.fetch_queries(
            start_date=start_date,
            end_date=end_date,
            row_limit=row_limit,
            dimensions=["page", "query"],
        )


def get_oauth_url() -> str:
    """Generate OAuth2 authorization URL for GSC."""
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.gsc_client_id,
                "client_secret": settings.gsc_client_secret,
                "redirect_uris": [settings.gsc_redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=settings.gsc_redirect_uri,
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return auth_url


async def exchange_code_for_tokens(code: str, project_id: str) -> dict:
    """Exchange OAuth2 code for tokens and save to project."""
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.gsc_client_id,
                "client_secret": settings.gsc_client_secret,
                "redirect_uris": [settings.gsc_redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=settings.gsc_redirect_uri,
    )
    flow.fetch_token(code=code)
    creds = flow.credentials

    SessionLocal = create_worker_session_factory()
    async with SessionLocal() as session:
        project = await session.get(Project, project_id)
        if project:
            project.gsc_access_token = creds.token
            project.gsc_refresh_token = creds.refresh_token
            project.gsc_token_expiry = creds.expiry
            await session.commit()

    return {"status": "connected", "project_id": project_id}
