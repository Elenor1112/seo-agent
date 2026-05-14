import uuid
from datetime import datetime
from typing import Optional, Any
from sqlalchemy import (
    String, Text, Integer, Float, Boolean, DateTime, JSON,
    ForeignKey, Index, UniqueConstraint, Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import enum


class Base(DeclarativeBase):
    pass


# ── Enums ──────────────────────────────────────────────────────────────────────

class ProjectStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    archived = "archived"


class TaskStatus(str, enum.Enum):
    pending = "pending"
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    retrying = "retrying"
    dead = "dead"


class TaskType(str, enum.Enum):
    crawl = "crawl"
    keywords = "keywords"
    serp = "serp"
    content_generate = "content_generate"
    content_optimize = "content_optimize"
    track_performance = "track_performance"
    feedback_loop = "feedback_loop"


class ContentStatus(str, enum.Enum):
    draft = "draft"
    review = "review"
    approved = "approved"
    published = "published"
    rejected = "rejected"


class SearchIntent(str, enum.Enum):
    informational = "informational"
    navigational = "navigational"
    commercial = "commercial"
    transactional = "transactional"


# ── Core Models ────────────────────────────────────────────────────────────────

class Project(Base):
    """A website / domain being managed by the SEO agent."""
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(SAEnum(ProjectStatus), default=ProjectStatus.active)

    # GSC OAuth tokens (encrypted at rest in production)
    gsc_access_token: Mapped[Optional[str]] = mapped_column(Text)
    gsc_refresh_token: Mapped[Optional[str]] = mapped_column(Text)
    gsc_token_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    gsc_property_url: Mapped[Optional[str]] = mapped_column(String(512))

    # WordPress integration
    wp_base_url: Mapped[Optional[str]] = mapped_column(String(512))
    wp_username: Mapped[Optional[str]] = mapped_column(String(255))
    wp_app_password: Mapped[Optional[str]] = mapped_column(Text)

    # Brand / content settings
    brand_voice: Mapped[Optional[str]] = mapped_column(Text)
    target_audience: Mapped[Optional[str]] = mapped_column(Text)
    content_language: Mapped[str] = mapped_column(String(10), default="en")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    pages: Mapped[list["Page"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    keywords: Mapped[list["Keyword"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    tasks: Mapped[list["Task"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    content_versions: Mapped[list["ContentVersion"]] = relationship(back_populates="project")


class Page(Base):
    """A crawled page within a project."""
    __tablename__ = "pages"
    __table_args__ = (
        UniqueConstraint("project_id", "url", name="uq_page_project_url"),
        Index("ix_pages_project_status", "project_id", "http_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    canonical_url: Mapped[Optional[str]] = mapped_column(String(2048))
    http_status: Mapped[Optional[int]] = mapped_column(Integer)
    redirect_to: Mapped[Optional[str]] = mapped_column(String(2048))

    # Meta
    title: Mapped[Optional[str]] = mapped_column(String(512))
    meta_description: Mapped[Optional[str]] = mapped_column(Text)
    h1: Mapped[Optional[str]] = mapped_column(String(512))
    h_tags: Mapped[Optional[dict]] = mapped_column(JSONB)  # {h1:[], h2:[], h3:[]}

    # Technical SEO
    robots_directives: Mapped[Optional[str]] = mapped_column(String(255))
    is_indexable: Mapped[bool] = mapped_column(Boolean, default=True)
    hreflang: Mapped[Optional[dict]] = mapped_column(JSONB)
    structured_data: Mapped[Optional[list]] = mapped_column(JSONB)  # extracted JSON-LD
    schema_types: Mapped[Optional[list]] = mapped_column(JSONB)  # ["Article", "FAQPage"]

    # Internal linking
    internal_links_in: Mapped[int] = mapped_column(Integer, default=0)
    internal_links_out: Mapped[int] = mapped_column(Integer, default=0)

    # Content metrics
    word_count: Mapped[Optional[int]] = mapped_column(Integer)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64))  # SHA256 for change detection

    # Core Web Vitals (Lighthouse)
    lcp_ms: Mapped[Optional[float]] = mapped_column(Float)
    cls_score: Mapped[Optional[float]] = mapped_column(Float)
    fid_ms: Mapped[Optional[float]] = mapped_column(Float)
    performance_score: Mapped[Optional[int]] = mapped_column(Integer)

    # Issues detected
    issues: Mapped[Optional[list]] = mapped_column(JSONB)  # ["missing_meta", "slow_lcp"]

    crawled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped["Project"] = relationship(back_populates="pages")
    content_versions: Mapped[list["ContentVersion"]] = relationship(back_populates="page")


class Keyword(Base):
    """A search keyword tracked for a project."""
    __tablename__ = "keywords"
    __table_args__ = (
        UniqueConstraint("project_id", "query", name="uq_keyword_project_query"),
        Index("ix_keywords_opportunity", "project_id", "opportunity_score"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    query: Mapped[str] = mapped_column(String(512), nullable=False)

    # GSC data (rolling 16-month aggregate)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    ctr: Mapped[float] = mapped_column(Float, default=0.0)
    avg_position: Mapped[Optional[float]] = mapped_column(Float)

    # Opportunity scoring
    search_volume_estimate: Mapped[Optional[int]] = mapped_column(Integer)
    keyword_difficulty: Mapped[Optional[float]] = mapped_column(Float)  # 0-100
    opportunity_score: Mapped[Optional[float]] = mapped_column(Float)   # 0-100 composite
    search_intent: Mapped[Optional[SearchIntent]] = mapped_column(SAEnum(SearchIntent))

    # Clustering
    cluster_id: Mapped[Optional[str]] = mapped_column(String(64))  # UUID of parent cluster
    cluster_label: Mapped[Optional[str]] = mapped_column(String(255))

    # Embedding vector stored in Pinecone; keep the ID here for lookups
    embedding_id: Mapped[Optional[str]] = mapped_column(String(255))

    is_gap: Mapped[bool] = mapped_column(Boolean, default=False)  # ranking 11-30 with volume

    last_gsc_sync: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped["Project"] = relationship(back_populates="keywords")
    serp_snapshots: Mapped[list["SerpSnapshot"]] = relationship(back_populates="keyword", cascade="all, delete-orphan")


class SerpSnapshot(Base):
    """A point-in-time SERP result for a keyword."""
    __tablename__ = "serp_snapshots"
    __table_args__ = (
        Index("ix_serp_keyword_date", "keyword_id", "scraped_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    keyword_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("keywords.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[Optional[str]] = mapped_column(String(512))
    meta_description: Mapped[Optional[str]] = mapped_column(Text)
    domain: Mapped[Optional[str]] = mapped_column(String(255))

    # Competitive signals
    word_count: Mapped[Optional[int]] = mapped_column(Integer)
    schema_types: Mapped[Optional[list]] = mapped_column(JSONB)
    has_featured_snippet: Mapped[bool] = mapped_column(Boolean, default=False)
    has_faq_schema: Mapped[bool] = mapped_column(Boolean, default=False)
    paa_questions: Mapped[Optional[list]] = mapped_column(JSONB)  # People Also Ask
    entities: Mapped[Optional[list]] = mapped_column(JSONB)
    h2_headings: Mapped[Optional[list]] = mapped_column(JSONB)

    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    keyword: Mapped["Keyword"] = relationship(back_populates="serp_snapshots")


class ContentVersion(Base):
    """A version of content for a page (draft, approved, published)."""
    __tablename__ = "content_versions"
    __table_args__ = (
        Index("ix_content_page_status", "page_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    page_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("pages.id", ondelete="SET NULL"))
    keyword_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("keywords.id", ondelete="SET NULL"))

    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[ContentStatus] = mapped_column(SAEnum(ContentStatus), default=ContentStatus.draft)
    content_type: Mapped[str] = mapped_column(String(50), default="article")  # article | optimize_diff

    # Metadata
    title: Mapped[Optional[str]] = mapped_column(String(512))
    meta_description: Mapped[Optional[str]] = mapped_column(Text)
    slug: Mapped[Optional[str]] = mapped_column(String(512))
    target_keyword: Mapped[Optional[str]] = mapped_column(String(512))
    secondary_keywords: Mapped[Optional[list]] = mapped_column(JSONB)

    # Storage
    s3_key: Mapped[Optional[str]] = mapped_column(String(1024))  # full HTML/MD content
    word_count: Mapped[Optional[int]] = mapped_column(Integer)

    # Quality signals
    semantic_score: Mapped[Optional[float]] = mapped_column(Float)   # 0-100 NLP coverage
    readability_score: Mapped[Optional[float]] = mapped_column(Float)

    # Agent metadata
    generated_by: Mapped[str] = mapped_column(String(50), default="content_gen_agent")
    prompt_version: Mapped[Optional[str]] = mapped_column(String(50))
    generation_meta: Mapped[Optional[dict]] = mapped_column(JSONB)  # tokens used, model, etc.

    # Publishing
    wp_post_id: Mapped[Optional[int]] = mapped_column(Integer)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[Optional[str]] = mapped_column(String(255))

    # Feedback loop signals
    rank_at_publish: Mapped[Optional[float]] = mapped_column(Float)
    rank_30d: Mapped[Optional[float]] = mapped_column(Float)
    rank_delta_30d: Mapped[Optional[float]] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped["Project"] = relationship(back_populates="content_versions")
    page: Mapped[Optional["Page"]] = relationship(back_populates="content_versions")


class Task(Base):
    """An agent task tracked through its lifecycle."""
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_project_status", "project_id", "status"),
        Index("ix_tasks_type_status", "task_type", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    parent_task_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("tasks.id"))

    task_type: Mapped[TaskType] = mapped_column(SAEnum(TaskType), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), default=TaskStatus.pending)
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1=highest, 5=lowest

    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255))

    # Input / output payloads
    payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    result: Mapped[Optional[dict]] = mapped_column(JSONB)
    error: Mapped[Optional[str]] = mapped_column(Text)

    retries: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped["Project"] = relationship(back_populates="tasks")
    subtasks: Mapped[list["Task"]] = relationship("Task")
