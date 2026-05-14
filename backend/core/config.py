from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_name: str = "SEO Agent"
    environment: Literal["development", "staging", "production"] = "development"
    secret_key: str = "dev-secret-change-in-production"
    debug: bool = True

    # Database
    database_url: str = "postgresql+asyncpg://seo:seopass@postgres:5432/seoagent"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # ClickHouse
    clickhouse_url: str = "clickhouse://seo:seopass@clickhouse:9000/analytics"
    clickhouse_host: str = "clickhouse"
    clickhouse_port: int = 9000
    clickhouse_user: str = "seo"
    clickhouse_password: str = "seopass"
    clickhouse_database: str = "analytics"

    # S3 / MinIO
    s3_endpoint: str = "http://minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin123"
    s3_bucket: str = "seo-content"
    s3_region: str = "us-east-1"

    # LLM
    anthropic_api_key: str = ""
    anthropic_model: str = "mistralai/mistral-7b-instruct:free"
    anthropic_max_tokens: int = 8192

    # SERP
    serper_api_key: str = ""
    # Google
    gsc_client_id: str = ""
    gsc_client_secret: str = ""
    gsc_redirect_uri: str = "http://localhost:8000/api/v1/auth/gsc/callback"

    # Celery
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"

    # Crawler
    crawler_max_depth: int = 5
    crawler_max_pages: int = 500
    crawler_concurrency: int = 3
    crawler_timeout_ms: int = 30000
    crawler_respect_robots: bool = True

    # Content generation
    content_min_words: int = 800
    content_max_words: int = 3000


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()