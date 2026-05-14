"""
Storage Service
================
Async S3-compatible storage (MinIO locally, AWS S3 in production).
"""
from __future__ import annotations

import json
from typing import Any, Optional

import aioboto3
from botocore.exceptions import ClientError

from core.config import settings
from core.logging import get_logger

logger = get_logger("storage")


class StorageService:
    def __init__(self) -> None:
        self.bucket = settings.s3_bucket
        self._session = aioboto3.Session()

    def _client_kwargs(self) -> dict:
        kwargs: dict = {
            "region_name": settings.s3_region,
            "aws_access_key_id": settings.s3_access_key,
            "aws_secret_access_key": settings.s3_secret_key,
        }
        if settings.s3_endpoint:
            kwargs["endpoint_url"] = settings.s3_endpoint
        return kwargs

    async def ensure_bucket(self) -> None:
        """Create bucket if it doesn't exist (MinIO / local dev)."""
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            try:
                await s3.head_bucket(Bucket=self.bucket)
            except ClientError:
                await s3.create_bucket(Bucket=self.bucket)
                logger.info("storage.bucket_created", bucket=self.bucket)

    async def put_json(self, key: str, data: Any) -> str:
        """Upload a Python dict as JSON to S3. Returns the key."""
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            await s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType="application/json",
            )
        logger.debug("storage.put", key=key, bytes=len(body))
        return key

    async def get_json(self, key: str) -> Optional[Any]:
        """Download and parse a JSON object from S3."""
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            try:
                resp = await s3.get_object(Bucket=self.bucket, Key=key)
                body = await resp["Body"].read()
                return json.loads(body.decode("utf-8"))
            except ClientError as e:
                if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                    return None
                raise

    async def put_text(self, key: str, text: str, content_type: str = "text/html") -> str:
        """Upload raw text/HTML to S3."""
        body = text.encode("utf-8")
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            await s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
            )
        return key

    async def delete(self, key: str) -> None:
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            await s3.delete_object(Bucket=self.bucket, Key=key)

    def get_public_url(self, key: str) -> str:
        """Return the URL for a stored object (MinIO local URL)."""
        return f"{settings.s3_endpoint}/{self.bucket}/{key}"
