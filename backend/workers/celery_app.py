from celery import Celery
from celery.schedules import crontab
from core.config import settings

celery_app = Celery(
    "seo_agent",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "workers.tasks.crawl_tasks",
        "workers.tasks.keyword_tasks",
        "workers.tasks.serp_tasks",
        "workers.tasks.content_tasks",
        "workers.tasks.tracker_tasks",
        "workers.tasks.feedback_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # one task at a time per worker slot (long tasks)
    result_expires=86400 * 7,      # keep results 7 days

    # Task routing
    task_routes={
        "workers.tasks.crawl_tasks.*": {"queue": "crawl"},
        "workers.tasks.keyword_tasks.*": {"queue": "keywords"},
        "workers.tasks.serp_tasks.*": {"queue": "serp"},
        "workers.tasks.content_tasks.*": {"queue": "content"},
        "workers.tasks.tracker_tasks.*": {"queue": "tracker"},
        "workers.tasks.feedback_tasks.*": {"queue": "optimize"},
    },

    # Rate limits
    task_annotations={
        "workers.tasks.serp_tasks.fetch_serp_data": {"rate_limit": "60/m"},
        "workers.tasks.content_tasks.generate_content": {"rate_limit": "10/m"},
    },

    # Scheduled tasks
    beat_schedule={
        # Run performance tracker daily at 6am UTC
        "daily-performance-tracker": {
            "task": "workers.tasks.tracker_tasks.run_daily_tracker",
            "schedule": crontab(hour=6, minute=0),
        },
        # Run feedback loop analysis weekly
        "weekly-feedback-loop": {
            "task": "workers.tasks.feedback_tasks.run_feedback_analysis",
            "schedule": crontab(day_of_week=1, hour=7, minute=0),  # Monday 7am
        },
        # Refresh GSC data every 6 hours
        "gsc-refresh": {
            "task": "workers.tasks.keyword_tasks.refresh_all_gsc_data",
            "schedule": crontab(minute=0, hour="*/6"),
        },
    },
)
