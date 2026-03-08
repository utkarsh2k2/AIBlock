"""Celery application factory.

Workers are started separately from the API:
  celery -A aiblock.workers.celery_app worker --loglevel=info --concurrency=4

Use Redis as both broker and result backend for cost-effective single-infra deploys.
Switch to SQS + RDS for larger scale without changing task code.
"""

from celery import Celery

from aiblock.settings import get_settings


def create_celery_app() -> Celery:
    settings = get_settings()
    app = Celery("aiblock")
    app.config_from_object(
        {
            "broker_url": settings.celery_broker(),
            "result_backend": settings.celery_backend(),
            "task_serializer": "json",
            "result_serializer": "json",
            "accept_content": ["json"],
            "timezone": "UTC",
            "enable_utc": True,
            # Retry failed tasks up to 3 times with exponential back-off
            "task_acks_late": True,
            "task_reject_on_worker_lost": True,
            # Keep results for 1 hour (matching job_ttl_seconds)
            "result_expires": settings.job_ttl_seconds,
            # Routing — all tasks go to the "detection" queue by default
            "task_default_queue": "detection",
            "task_routes": {
                "aiblock.workers.tasks.run_detection": {"queue": "detection"},
            },
        }
    )
    app.autodiscover_tasks(["aiblock.workers"])
    return app


celery_app = create_celery_app()
