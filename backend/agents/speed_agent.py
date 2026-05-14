"""
Speed Audit Agent for AI SEO Agent System
Performs Lighthouse/PageSpeed audits and analyzes Core Web Vitals
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import SpeedAudit, Page, Project
from backend.core.logging import get_logger

logger = get_logger(__name__)


class SpeedAuditAgent:
    """Agent responsible for running website speed audits"""

    def __init__(self, pagespeed_api_key: Optional[str] = None):
        self.pagespeed_api_key = pagespeed_api_key
        self.base_url = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

    async def run_audit(
        self,
        session: AsyncSession,
        project_id: int,
        page_url: str,
        page_id: Optional[int] = None,
        strategy: str = "desktop"
    ) -> Dict[str, Any]:
        """
        Run a complete speed audit for a URL
        
        Args:
            session: Database session
            project_id: Project ID
            page_url: URL to audit
            page_id: Optional page ID if already exists
            strategy: 'desktop' or 'mobile'
            
        Returns:
            Audit results dictionary
        """
        logger.info(f"Running speed audit for {page_url} ({strategy})")
        
        try:
            # Run PageSpeed Insights API
            audit_data = await self._run_pagespeed_audit(page_url, strategy)
            
            # Extract metrics
            metrics = self._extract_metrics(audit_data)
            
            # Generate recommendations
            recommendations = self._generate_recommendations(audit_data)
            
            # Create audit record
            audit_result = await self._save_audit(
                session=session,
                project_id=project_id,
                page_id=page_id,
                metrics=metrics,
                recommendations=recommendations
            )
            
            logger.info(f"Speed audit completed for {page_url}")
            return {
                "success": True,
                "audit_id": audit_result.id,
                "metrics": metrics,
                "recommendations": recommendations
            }
            
        except Exception as e:
            logger.error(f"Speed audit failed for {page_url}: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def _run_pagespeed_audit(
        self, 
        url: str, 
        strategy: str = "desktop"
    ) -> Dict[str, Any]:
        """Call Google PageSpeed Insights API"""
        
        params = {
            "url": url,
            "strategy": strategy,
            "category": "PERFORMANCE",
            "category": "SEO",
            "category": "ACCESSIBILITY",
            "category": "BEST_PRACTICES",
        }
        
        if self.pagespeed_api_key:
            params["key"] = self.pagespeed_api_key
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(self.base_url, params=params)
            response.raise_for_status()
            return response.json()

    def _extract_metrics(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant metrics from PageSpeed response"""
        
        lighthouse = data.get("lighthouseResult", {})
        categories = lighthouse.get("categories", {})
        audits = lighthouse.get("audits", {})
        
        # Category scores
        performance_score = categories.get("performance", {}).get("score", 0) * 100
        seo_score = categories.get("seo", {}).get("score", 0) * 100
        accessibility_score = categories.get("accessibility", {}).get("score", 0) * 100
        best_practices_score = categories.get("best-practices", {}).get("score", 0) * 100
        
        # Core Web Vitals
        lcp_audit = audits.get("largest-contentful-paint", {})
        cls_audit = audits.get("cumulative-layout-shift", {})
        inp_audit = audits.get("interaction-to-next-paint", {})
        ttfb_audit = audits.get("first-contentful-paint", {})
        tbt_audit = audits.get("total-blocking-time", {})
        
        lcp = lcp_audit.get("numericValue", 0) / 1000  # Convert to seconds
        cls = cls_audit.get("numericValue", 0)
        inp = inp_audit.get("numericValue", 0) / 1000  # Convert to seconds
        ttfb = ttfb_audit.get("numericValue", 0) / 1000  # Using FCP as proxy
        total_blocking_time = tbt_audit.get("numericValue", 0) / 1000  # Convert to seconds
        
        return {
            "performance_score": round(performance_score, 2),
            "seo_score": round(seo_score, 2),
            "accessibility_score": round(accessibility_score, 2),
            "best_practices_score": round(best_practices_score, 2),
            "lcp": round(lcp, 3),
            "cls": round(cls, 4),
            "inp": round(inp, 3),
            "ttfb": round(ttfb, 3),
            "total_blocking_time": round(total_blocking_time, 3)
        }

    def _generate_recommendations(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate optimization recommendations based on audit results"""
        
        recommendations = []
        lighthouse = data.get("lighthouseResult", {})
        audits = lighthouse.get("audits", {})
        
        # Check for failed audits
        for audit_id, audit in audits.items():
            score = audit.get("score", 1)
            if score is not None and score < 0.9:
                title = audit.get("title", "Unknown Issue")
                description = audit.get("description", "")
                
                # Priority based on score
                if score < 0.5:
                    priority = "high"
                elif score < 0.75:
                    priority = "medium"
                else:
                    priority = "low"
                
                recommendations.append({
                    "id": audit_id,
                    "title": title,
                    "description": description,
                    "priority": priority,
                    "score": round(score * 100, 2)
                })
        
        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(key=lambda x: (priority_order.get(x["priority"], 3), -x["score"]))
        
        return recommendations[:10]  # Return top 10 recommendations

    async def _save_audit(
        self,
        session: AsyncSession,
        project_id: int,
        page_id: Optional[int],
        metrics: Dict[str, Any],
        recommendations: List[Dict[str, Any]]
    ) -> SpeedAudit:
        """Save audit results to database"""
        
        audit = SpeedAudit(
            project_id=project_id,
            page_id=page_id,
            performance_score=metrics["performance_score"],
            seo_score=metrics["seo_score"],
            accessibility_score=metrics["accessibility_score"],
            best_practices_score=metrics["best_practices_score"],
            lcp=metrics["lcp"],
            cls=metrics["cls"],
            inp=metrics["inp"],
            ttfb=metrics["ttfb"],
            total_blocking_time=metrics["total_blocking_time"],
            recommendations=recommendations
        )
        
        session.add(audit)
        await session.commit()
        await session.refresh(audit)
        
        return audit

    async def run_project_audit(
        self,
        session: AsyncSession,
        project: Project,
        strategy: str = "desktop"
    ) -> List[Dict[str, Any]]:
        """Run speed audits for all pages in a project"""
        
        results = []
        
        # Get project pages
        from sqlalchemy import select
        stmt = select(Page).where(Page.project_id == project.id)
        result = await session.execute(stmt)
        pages = result.scalars().all()
        
        for page in pages:
            result = await self.run_audit(
                session=session,
                project_id=project.id,
                page_url=page.url,
                page_id=page.id,
                strategy=strategy
            )
            results.append(result)
        
        return results
