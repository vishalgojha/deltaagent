from celery import Celery

from backend.config import get_settings


settings = get_settings()
celery_app = Celery("trading_agent", broker=settings.redis_url, backend=settings.redis_url)


@celery_app.task
def heartbeat_task() -> str:
    return "ok"
