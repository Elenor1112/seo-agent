"""
Rating Engine for AI SEO Agent System
Generates overall SEO scores and category breakdowns
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.db.models import Project, ProjectScore, SpeedAudit, Page, Keyword, ContentVersion
from backend.core.logging import get_logger

logger = get_logger(__name__)


class RatingEngine:
    """
    Engine for calculating overall SEO scores
    
    Scoring weights:
    - Technical SEO: 25%
    - Speed/Core Web Vitals: 25%
    - Content Quality: 20%
    - Keyword Rankings: 15%
    - Backlink/Profile Signals: 10%
    - Structured Data: 5%
    """

    # Weights for each category
    WEIGHTS = {
        "technical": 0.25,
        "speed": 0.25,
        "content": 0.20,
        "keyword": 0.15,
        "backlink": 0.10,
        "schema": 0.05,
    }

    # Grade thresholds
    GRADES = [
        (90, "A"),
        (80, "B"),
        (70, "C"),
        (60, "D"),
        (0, "F"),
    ]

    async def calculate_project_score(
        self,
        session: AsyncSession,
        project_id: UUID
    ) -> Dict[str, Any]:
        """
        Calculate overall SEO score for a project
        
        Args:
            session: Database session
            project_id: Project UUID
            
        Returns:
            Score calculation results
        """
        logger.info(f"Calculating SEO score for project {project_id}")

        try:
            # Get project
            stmt = select(Project).where(Project.id == project_id)
            result = await session.execute(stmt)
            project = result.scalar_one_or_none()

            if not project:
                return {"success": False, "error": "Project not found"}

            # Calculate category scores
            technical_score = await self._calculate_technical_score(session, project_id)
            speed_score = await self._calculate_speed_score(session, project_id)
            content_score = await self._calculate_content_score(session, project_id)
            keyword_score = await self._calculate_keyword_score(session, project_id)
            schema_score = await self._calculate_schema_score(session, project_id)
            backlink_score = await self._calculate_backlink_score(session, project_id)

            # Calculate weighted overall score
            overall_score = (
                technical_score * self.WEIGHTS["technical"] +
                speed_score * self.WEIGHTS["speed"] +
                content_score * self.WEIGHTS["content"] +
                keyword_score * self.WEIGHTS["keyword"] +
                schema_score * self.WEIGHTS["schema"] +
                backlink_score * self.WEIGHTS["backlink"]
            )

            # Determine letter grade
            grade = self._get_grade(overall_score)

            # Generate recommendations
            recommendations = await self._generate_recommendations(
                session=session,
                project_id=project_id,
                technical_score=technical_score,
                speed_score=speed_score,
                content_score=content_score,
                keyword_score=keyword_score,
                schema_score=schema_score,
                backlink_score=backlink_score
            )

            # Save score record
            score_record = await self._save_score(
                session=session,
                project_id=project_id,
                overall_score=round(overall_score, 2),
                technical_score=round(technical_score, 2),
                speed_score=round(speed_score, 2),
                content_score=round(content_score, 2),
                keyword_score=round(keyword_score, 2),
                schema_score=round(schema_score, 2),
                backlink_score=round(backlink_score, 2),
                grade=grade,
                recommendations=recommendations
            )

            logger.info(f"SEO score calculated: {overall_score:.2f} ({grade})")

            return {
                "success": True,
                "score_id": str(score_record.id),
                "overall_score": round(overall_score, 2),
                "grade": grade,
                "category_scores": {
                    "technical": round(technical_score, 2),
                    "speed": round(speed_score, 2),
                    "content": round(content_score, 2),
                    "keyword": round(keyword_score, 2),
                    "schema": round(schema_score, 2),
                    "backlink": round(backlink_score, 2),
                },
                "recommendations": recommendations
            }

        except Exception as e:
            logger.error(f"Score calculation failed: {str(e)}")
            return {"success": False, "error": str(e)}

    async def _calculate_technical_score(
        self, 
        session: AsyncSession, 
        project_id: UUID
    ) -> float:
        """Calculate technical SEO score (0-100)"""
        
        # Get pages
        stmt = select(Page).where(Page.project_id == project_id)
        result = await session.execute(stmt)
        pages = result.scalars().all()

        if not pages:
            return 50.0  # Default score if no pages

        total_pages = len(pages)
        
        # Factors to check
        indexable_count = sum(1 for p in pages if p.is_indexable)
        has_title_count = sum(1 for p in pages if p.title)
        has_meta_desc_count = sum(1 for p in pages if p.meta_description)
        has_h1_count = sum(1 for p in pages if p.h1)
        valid_status_count = sum(1 for p in pages if p.http_status and 200 <= p.http_status < 400)

        # Calculate sub-scores
        indexable_ratio = indexable_count / total_pages
        title_ratio = has_title_count / total_pages
        meta_desc_ratio = has_meta_desc_count / total_pages
        h1_ratio = has_h1_count / total_pages
        status_ratio = valid_status_count / total_pages

        # Weighted average
        score = (
            indexable_ratio * 30 +
            title_ratio * 20 +
            meta_desc_ratio * 20 +
            h1_ratio * 15 +
            status_ratio * 15
        )

        return min(100, max(0, score))

    async def _calculate_speed_score(
        self, 
        session: AsyncSession, 
        project_id: UUID
    ) -> float:
        """Calculate speed/Core Web Vitals score (0-100)"""
        
        # Get latest speed audits
        stmt = select(SpeedAudit).where(
            SpeedAudit.project_id == project_id
        ).order_by(SpeedAudit.created_at.desc())
        
        result = await session.execute(stmt)
        audits = result.scalars().all()

        if not audits:
            return 50.0  # Default if no audits

        # Use most recent audit per page (limit to first 10 unique pages)
        page_audits = {}
        for audit in audits:
            if audit.page_id not in page_audits:
                page_audits[audit.page_id] = audit
            if len(page_audits) >= 10:
                break

        if not page_audits:
            return 50.0

        # Average performance scores
        perf_scores = [a.performance_score for a in page_audits.values() if a.performance_score]
        
        if not perf_scores:
            return 50.0

        avg_performance = sum(perf_scores) / len(perf_scores)

        # Check Core Web Vitals pass rate
        cwv_pass = 0
        cwv_total = 0
        
        for audit in page_audits.values():
            # LCP < 2.5s is good
            if audit.lcp and audit.lcp < 2.5:
                cwv_pass += 0.25
            # CLS < 0.1 is good
            if audit.cls is not None and audit.cls < 0.1:
                cwv_pass += 0.25
            # INP < 200ms is good
            if audit.inp and audit.inp < 0.2:
                cwv_pass += 0.25
            # TTFB < 800ms is good
            if audit.ttfb and audit.ttfb < 0.8:
                cwv_pass += 0.25
            cwv_total += 1

        cwv_ratio = cwv_pass / cwv_total if cwv_total > 0 else 0.5

        # Combine performance score and CWV pass rate
        score = avg_performance * 0.6 + (cwv_ratio * 100) * 0.4

        return min(100, max(0, score))

    async def _calculate_content_score(
        self, 
        session: AsyncSession, 
        project_id: UUID
    ) -> float:
        """Calculate content quality score (0-100)"""
        
        # Get content versions
        stmt = select(ContentVersion).where(
            ContentVersion.project_id == project_id
        )
        result = await session.execute(stmt)
        content_versions = result.scalars().all()

        if not content_versions:
            return 50.0

        # Filter for published/approved content
        published_content = [
            c for c in content_versions 
            if c.status.value in ["approved", "published"]
        ]

        if not published_content:
            return 50.0

        # Calculate average scores
        semantic_scores = [c.semantic_score for c in published_content if c.semantic_score]
        readability_scores = [c.readability_score for c in published_content if c.readability_score]
        word_counts = [c.word_count for c in published_content if c.word_count]

        avg_semantic = sum(semantic_scores) / len(semantic_scores) if semantic_scores else 50
        avg_readability = sum(readability_scores) / len(readability_scores) if readability_scores else 50
        
        # Word count scoring (ideal: 1000+ words)
        avg_word_count = sum(word_counts) / len(word_counts) if word_counts else 0
        word_count_score = min(100, (avg_word_count / 1000) * 100)

        # Weighted average
        score = (
            avg_semantic * 0.4 +
            avg_readability * 0.3 +
            word_count_score * 0.3
        )

        return min(100, max(0, score))

    async def _calculate_keyword_score(
        self, 
        session: AsyncSession, 
        project_id: UUID
    ) -> float:
        """Calculate keyword rankings score (0-100)"""
        
        # Get keywords
        stmt = select(Keyword).where(Keyword.project_id == project_id)
        result = await session.execute(stmt)
        keywords = result.scalars().all()

        if not keywords:
            return 50.0

        total_keywords = len(keywords)
        
        # Count keywords by position
        top_3_count = sum(1 for k in keywords if k.avg_position and k.avg_position <= 3)
        top_10_count = sum(1 for k in keywords if k.avg_position and k.avg_position <= 10)
        top_30_count = sum(1 for k in keywords if k.avg_position and k.avg_position <= 30)
        
        # Calculate score based on distribution
        top_3_ratio = top_3_count / total_keywords
        top_10_ratio = (top_10_count - top_3_count) / total_keywords
        top_30_ratio = (top_30_count - top_10_count) / total_keywords
        below_30_ratio = (total_keywords - top_30_count) / total_keywords

        score = (
            top_3_ratio * 100 +
            top_10_ratio * 70 +
            top_30_ratio * 40 +
            below_30_ratio * 10
        )

        return min(100, max(0, score))

    async def _calculate_schema_score(
        self, 
        session: AsyncSession, 
        project_id: UUID
    ) -> float:
        """Calculate structured data score (0-100)"""
        
        # Get pages
        stmt = select(Page).where(Page.project_id == project_id)
        result = await session.execute(stmt)
        pages = result.scalars().all()

        if not pages:
            return 50.0

        total_pages = len(pages)
        
        # Count pages with structured data
        pages_with_schema = sum(1 for p in pages if p.structured_data and len(p.structured_data) > 0)
        pages_with_multiple_schema = sum(1 for p in pages if p.schema_types and len(p.schema_types) > 1)

        schema_ratio = pages_with_schema / total_pages
        multi_schema_ratio = pages_with_multiple_schema / total_pages

        score = (schema_ratio * 70) + (multi_schema_ratio * 30)

        return min(100, max(0, score))

    async def _calculate_backlink_score(
        self, 
        session: AsyncSession, 
        project_id: UUID
    ) -> float:
        """
        Calculate backlink/profile signals score (0-100)
        
        Note: This is a placeholder. In production, integrate with 
        backlink APIs (Ahrefs, Moz, SEMrush, etc.)
        """
        
        # Placeholder: Return moderate score
        # TODO: Integrate with actual backlink data source
        return 60.0

    async def _generate_recommendations(
        self,
        session: AsyncSession,
        project_id: UUID,
        technical_score: float,
        speed_score: float,
        content_score: float,
        keyword_score: float,
        schema_score: float,
        backlink_score: float
    ) -> List[Dict[str, Any]]:
        """Generate recommendations based on scores"""
        
        recommendations = []

        # Technical recommendations
        if technical_score < 70:
            recommendations.append({
                "category": "technical",
                "priority": "high" if technical_score < 50 else "medium",
                "title": "Improve Technical SEO",
                "description": "Fix indexation issues, add missing titles and meta descriptions",
                "impact": "High impact on search visibility"
            })

        # Speed recommendations
        if speed_score < 70:
            recommendations.append({
                "category": "speed",
                "priority": "high" if speed_score < 50 else "medium",
                "title": "Optimize Page Speed",
                "description": "Improve Core Web Vitals (LCP, CLS, INP)",
                "impact": "Direct ranking factor and user experience"
            })

        # Content recommendations
        if content_score < 70:
            recommendations.append({
                "category": "content",
                "priority": "medium",
                "title": "Enhance Content Quality",
                "description": "Improve semantic coverage and readability",
                "impact": "Better engagement and rankings"
            })

        # Keyword recommendations
        if keyword_score < 70:
            recommendations.append({
                "category": "keywords",
                "priority": "medium",
                "title": "Improve Keyword Rankings",
                "description": "Target keywords with ranking opportunities",
                "impact": "Increased organic traffic"
            })

        # Schema recommendations
        if schema_score < 70:
            recommendations.append({
                "category": "schema",
                "priority": "low",
                "title": "Add Structured Data",
                "description": "Implement schema markup for rich snippets",
                "impact": "Enhanced SERP appearance"
            })

        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(key=lambda x: priority_order.get(x["priority"], 3))

        return recommendations[:5]  # Return top 5

    def _get_grade(self, score: float) -> str:
        """Convert score to letter grade"""
        for threshold, grade in self.GRADES:
            if score >= threshold:
                return grade
        return "F"

    async def _save_score(
        self,
        session: AsyncSession,
        project_id: UUID,
        overall_score: float,
        technical_score: float,
        speed_score: float,
        content_score: float,
        keyword_score: float,
        schema_score: float,
        backlink_score: float,
        grade: str,
        recommendations: List[Dict[str, Any]]
    ) -> ProjectScore:
        """Save score record to database"""
        
        score = ProjectScore(
            project_id=project_id,
            overall_score=overall_score,
            technical_score=technical_score,
            speed_score=speed_score,
            content_score=content_score,
            keyword_score=keyword_score,
            schema_score=schema_score,
            backlink_score=backlink_score,
            grade=grade,
            recommendations=recommendations
        )

        session.add(score)
        await session.commit()
        await session.refresh(score)

        return score
