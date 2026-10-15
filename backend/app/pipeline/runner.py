"""Tiny in-process job runner. Jobs are idempotent and driven entirely by DB state, so swapping this for Celery/RQ later
means wrapping the orchestrator functions in tasks — nothing else changes."""
import asyncio
import logging
from typing import Awaitable, Callable

logger = logging.getLogger("app.runner")

_running: dict[str, asyncio.Task] = {}
_semaphores: dict[int, asyncio.Semaphore] = {}


def image_semaphore(limit: int) -> asyncio.Semaphore:
    """One semaphore per event loop (the test suite creates several loops)."""
    loop_id = id(asyncio.get_running_loop())
    if loop_id not in _semaphores:
        _semaphores[loop_id] = asyncio.Semaphore(limit)
    return _semaphores[loop_id]


def spawn(key: str, fn: Callable[..., Awaitable], *args) -> bool:
    """Starts fn(*args) in the background unless a job with the same key is already running."""
    existing = _running.get(key)
    if existing and not existing.done():
        return False

    async def _wrapped():
        try:
            await fn(*args)
        except Exception:  # noqa: BLE001 — jobs record their own failures; this is the last-resort log
            logger.exception("background job %s crashed", key)

    task = asyncio.create_task(_wrapped(), name=key)
    _running[key] = task
    task.add_done_callback(lambda t, k=key: _running.pop(k, None) if _running.get(k) is t else None)
    return True


async def wait_all() -> None:
    """For tests / graceful shutdown."""
    while True:
        pending = [t for t in _running.values() if not t.done()]
        if not pending:
            return
        await asyncio.gather(*pending, return_exceptions=True)
