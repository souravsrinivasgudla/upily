"""Fire-and-forget background tasks that are kept alive and whose errors get logged."""
import asyncio
import logging
from typing import Coroutine

log = logging.getLogger(__name__)

_tasks: set[asyncio.Task] = set()


def spawn(coro: Coroutine, name: str) -> asyncio.Task:
    task = asyncio.create_task(coro, name=name)
    _tasks.add(task)   # strong reference: un-referenced tasks can be garbage-collected mid-run

    def _done(t: asyncio.Task) -> None:
        _tasks.discard(t)
        if not t.cancelled() and t.exception():
            log.error("Background task %s failed", name, exc_info=t.exception())

    task.add_done_callback(_done)
    return task


async def cancel_all() -> None:
    for t in list(_tasks):
        t.cancel()
    if _tasks:
        await asyncio.gather(*_tasks, return_exceptions=True)
