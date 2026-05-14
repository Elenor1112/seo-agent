from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import projects, tasks, keywords, content, analytics, auth, wordpress
from core.config import settings
from core.logging import setup_logging
from db.session import engine
from db.models import Base
from services.storage import StorageService


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()

    # Create all DB tables on startup (use Alembic migrations in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Ensure S3 bucket exists
    storage = StorageService()
    await storage.ensure_bucket()

    yield

    await engine.dispose()


app = FastAPI(
    title="SEO Agent API",
    description="Production-ready AI SEO Agent System",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(projects.router, prefix="/api/v1/projects", tags=["projects"])
app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["tasks"])
app.include_router(keywords.router, prefix="/api/v1/keywords", tags=["keywords"])
app.include_router(content.router, prefix="/api/v1/content", tags=["content"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(wordpress.router, prefix="/api/v1/wordpress", tags=["wordpress"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
