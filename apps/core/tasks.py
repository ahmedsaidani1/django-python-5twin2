import logging
import socket
import threading
import time
from urllib.parse import urlparse

from celery import shared_task
from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from .ai.registry import get_module
from .models import AIJob

logger = logging.getLogger("apps.ai")


def execute_job(job_id: int) -> None:
    """Run one AIJob and persist its output, error and latency. Never raises."""
    job = AIJob.objects.select_related("user").get(pk=job_id)
    job.status = AIJob.Status.RUNNING
    job.save(update_fields=["status"])
    start = time.perf_counter()
    try:
        result = get_module(job.kind).handle(job.input, job.user)
        job.output = result
        job.provider = result.get("provider", "local") if isinstance(result, dict) else "local"
        job.status = AIJob.Status.SUCCESS
    except Exception as exc:  # any failure is stored on the job, shown in French to the user
        logger.exception("AI job %s (%s) failed", job_id, job.kind)
        job.status = AIJob.Status.ERROR
        job.error = str(exc) or exc.__class__.__name__
    job.latency_ms = int((time.perf_counter() - start) * 1000)
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "output", "error", "provider", "latency_ms", "finished_at"])


@shared_task(name="core.run_ai_job")
def run_ai_job(job_id: int) -> None:
    execute_job(job_id)


def _run_in_thread(job_id: int) -> None:
    try:
        execute_job(job_id)
    finally:
        close_old_connections()


_broker_state = {"ok": None, "checked": 0.0}


def broker_available(ttl: float = 30.0) -> bool:
    """Fast TCP probe of the broker (cached), so a missing Redis never slows the request down."""
    now = time.monotonic()
    if _broker_state["ok"] is not None and now - _broker_state["checked"] < ttl:
        return _broker_state["ok"]
    url = urlparse(settings.CELERY_BROKER_URL)
    ok = True
    if url.scheme in ("redis", "rediss", "amqp"):
        try:
            with socket.create_connection((url.hostname or "localhost", url.port or 6379), timeout=0.3):
                pass
        except OSError:
            ok = False
    _broker_state.update(ok=ok, checked=now)
    return ok


def submit_job(job: AIJob) -> None:
    """Queue the job on Celery. If the broker is unreachable (local demo without
    Redis), run it in a background thread so the HTTP request still never blocks."""
    if settings.CELERY_TASK_ALWAYS_EAGER:
        run_ai_job.apply(args=[job.pk])
        return
    try:
        if not broker_available():
            raise ConnectionError(f"broker {settings.CELERY_BROKER_URL} unreachable")
        run_ai_job.apply_async(args=[job.pk], retry=False)
    except Exception as exc:
        logger.warning("Celery broker unavailable (%s); running AI job %s in a thread", exc, job.pk)
        threading.Thread(target=_run_in_thread, args=(job.pk,), daemon=True).start()


def start_ai_job(kind: str, payload: dict, user=None) -> AIJob:
    """Create an AIJob and queue it (used for background screening, e.g. fraud on publish)."""
    job = AIJob.objects.create(user=user, kind=kind, input=payload)
    submit_job(job)
    return job
