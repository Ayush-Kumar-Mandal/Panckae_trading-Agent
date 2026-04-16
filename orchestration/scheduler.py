"""
Scheduler: runs agents at configured intervals.
Used by the orchestrator for periodic tasks.
"""

import asyncio
from typing import Callable, Coroutine
from utils.logger import get_logger

logger = get_logger(__name__)


class TradingScheduler:
    """Schedule async tasks to run at fixed intervals."""

    def __init__(self):
        self._tasks: list[asyncio.Task] = []

    def schedule(
        self,
        name: str,
        coro_func: Callable[..., Coroutine],
        interval_seconds: float,
    ) -> None:
        """Schedule an async function to run repeatedly at an interval."""

        async def _loop():
            while True:
                try:
                    await coro_func()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Scheduled task '{name}' failed: {e}")
                await asyncio.sleep(interval_seconds)

        task = asyncio.create_task(_loop())
        self._tasks.append(task)
        logger.info(f"Scheduled '{name}' every {interval_seconds}s")

    async def stop_all(self) -> None:
        """Cancel all scheduled tasks."""
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("All scheduled tasks stopped")
