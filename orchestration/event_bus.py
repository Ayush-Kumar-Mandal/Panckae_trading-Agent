"""
In-memory async event bus for agent communication.
Agents publish events; other agents subscribe to relevant event types.
No external dependencies (no Redis required).
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Callable, Coroutine

from utils.logger import get_logger

logger = get_logger(__name__)


class EventBus:
    """
    Lightweight async event bus using asyncio.
    
    Usage:
        bus = EventBus()
        bus.subscribe("market.opportunity", my_handler)
        await bus.publish("market.opportunity", {"pool": "WBNB/USDT", "diff": 0.02})
    """

    def __init__(self):
        self._subscribers: dict[str, list[Callable[..., Coroutine]]] = defaultdict(list)
        self._event_count: int = 0

    def subscribe(self, event_type: str, handler: Callable[..., Coroutine]) -> None:
        """Register an async handler for an event type."""
        self._subscribers[event_type].append(handler)
        logger.debug(
            f"Subscribed {handler.__qualname__} to '{event_type}' "
            f"(total listeners: {len(self._subscribers[event_type])})"
        )

    def unsubscribe(self, event_type: str, handler: Callable[..., Coroutine]) -> None:
        """Remove a handler from an event type."""
        if handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)

    async def publish(self, event_type: str, data: Any = None) -> None:
        """
        Publish an event to all subscribers of that type.
        Handlers are called sequentially to preserve pipeline order.
        """
        handlers = self._subscribers.get(event_type, [])
        if not handlers:
            logger.debug(f"Event '{event_type}' published — no subscribers")
            return

        self._event_count += 1
        logger.debug(
            f"Event #{self._event_count} '{event_type}' → {len(handlers)} handler(s)"
        )

        for handler in handlers:
            try:
                await handler(data)
            except Exception as e:
                logger.error(
                    f"Handler {handler.__qualname__} failed on '{event_type}': {e}",
                    exc_info=True,
                )

    @property
    def stats(self) -> dict:
        """Return event bus statistics."""
        return {
            "total_events_published": self._event_count,
            "registered_event_types": len(self._subscribers),
            "total_handlers": sum(
                len(h) for h in self._subscribers.values()
            ),
        }
