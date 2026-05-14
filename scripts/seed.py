#!/usr/bin/env python3
"""
scripts/seed.py
===============
Creates a demo project for local development and testing.
Run with: docker compose run --rm api python scripts/seed.py
"""
import asyncio
import os
import sys
sys.path.insert(0, "/app")

from backend.db.session import AsyncSessionLocal, engine
from backend.db.models import Base, Project, Keyword, SearchIntent
from sqlalchemy import select


DEMO_KEYWORDS = [
    ("best project management software", 8200, 12.3, 0.042, True, SearchIntent.commercial),
    ("project management tools comparison", 3400, 18.7, 0.031, True, SearchIntent.commercial),
    ("how to manage remote teams", 12000, 22.1, 0.021, True, SearchIntent.informational),
    ("agile vs scrum methodology", 5600, 9.8, 0.058, True, SearchIntent.informational),
    ("project timeline template free", 9800, 14.5, 0.038, True, SearchIntent.transactional),
    ("jira alternative", 4200, 7.2, 0.071, True, SearchIntent.commercial),
    ("asana pricing", 8900, 3.1, 0.125, False, SearchIntent.commercial),
    ("kanban board software", 6700, 11.4, 0.049, True, SearchIntent.commercial),
    ("project management certification", 2800, 31.2, 0.018, True, SearchIntent.informational),
    ("free gantt chart maker", 15000, 19.6, 0.027, True, SearchIntent.transactional),
]


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # Check if demo project already exists
        result = await session.execute(
            select(Project).where(Project.domain == "demo.example.com")
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"✅ Demo project already exists: {existing.id}")
            project = existing
        else:
            project = Project(
                name="Demo Project",
                domain="demo.example.com",
                base_url="https://demo.example.com",
                brand_voice="Professional, data-driven, helpful. We explain complex topics clearly.",
                target_audience="Project managers and team leads at mid-size companies",
                content_language="en",
            )
            session.add(project)
            await session.flush()
            print(f"✅ Created demo project: {project.id}")

        # Seed demo keywords
        kw_count = 0
        for query, impressions, position, ctr, is_gap, intent in DEMO_KEYWORDS:
            result = await session.execute(
                select(Keyword).where(
                    Keyword.project_id == project.id,
                    Keyword.query == query,
                )
            )
            if result.scalar_one_or_none():
                continue

            import math
            pos_score = max(0.0, (100 - position) / 100)
            imp_score = min(1.0, math.log1p(impressions) / math.log1p(10000))
            ctr_gap = max(0.0, 1.0 - ctr) if is_gap else 0.0
            opp = round((pos_score * 0.4 + imp_score * 0.4 + ctr_gap * 0.2) * 100, 2)

            kw = Keyword(
                project_id=project.id,
                query=query,
                impressions=impressions,
                clicks=int(impressions * ctr),
                ctr=ctr,
                avg_position=position,
                opportunity_score=opp,
                search_intent=intent,
                is_gap=is_gap,
                cluster_label="Project Management Tools" if "management" in query else "Methodologies",
            )
            session.add(kw)
            kw_count += 1

        await session.commit()
        print(f"✅ Seeded {kw_count} demo keywords")
        print(f"\n🎉 Demo ready!")
        print(f"   Project ID: {project.id}")
        print(f"   Open http://localhost:3000 to explore")


if __name__ == "__main__":
    asyncio.run(seed())
