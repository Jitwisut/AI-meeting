"""Job queue abstraction.

* ``rq``     — Redis + RQ worker (docker-compose / multi-replica deployments)
* ``thread`` — in-process background threads; for single-container hosts without Redis
               (e.g. Render free tier). Jobs lost on restart are recoverable via the
               stale-processing retry in ``POST /process``.
* ``sync``   — inline, for tests and local dev
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from app.config import get_settings

QUEUE_NAME = "meetings"
JOB_TIMEOUT_SECONDS = 3 * 60 * 60
THREAD_WORKERS = 2

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _thread_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=THREAD_WORKERS, thread_name_prefix="meeting-job")
        return _executor


def _run_in_thread(meeting_id: str) -> None:
    from app.workers.pipeline import process_meeting

    try:
        process_meeting(meeting_id)
    except Exception:  # noqa: BLE001 - process_meeting records failures itself; never kill the pool
        logging.getLogger("worker").exception("background job crashed meeting=%s", meeting_id)


def enqueue_processing(meeting_id: str) -> str | None:
    s = get_settings()
    if s.queue_mode == "sync":
        from app.workers.pipeline import process_meeting

        process_meeting(meeting_id)
        return None
    if s.queue_mode == "thread":
        _thread_executor().submit(_run_in_thread, meeting_id)
        return None
    from redis import Redis
    from rq import Queue

    queue = Queue(QUEUE_NAME, connection=Redis.from_url(s.redis_url))
    job = queue.enqueue("app.workers.pipeline.process_meeting", meeting_id,
                        job_id=f"process-{meeting_id}-{_attempt_suffix()}",
                        job_timeout=JOB_TIMEOUT_SECONDS, result_ttl=3600, failure_ttl=7 * 24 * 3600)
    return job.id


def _attempt_suffix() -> str:
    import uuid

    return uuid.uuid4().hex[:8]


def processing_is_stale(meeting) -> bool:  # noqa: ANN001
    """True when a meeting has been 'processing' with no stage activity for longer than the job timeout
    (e.g. the worker container restarted mid-job), so the user may safely retry."""
    stamps = [meeting.created_at] + [t for j in meeting.jobs for t in (j.started_at, j.finished_at) if t]
    latest = max(t if t.tzinfo else t.replace(tzinfo=timezone.utc) for t in stamps)
    return datetime.now(timezone.utc) - latest > timedelta(seconds=JOB_TIMEOUT_SECONDS)
