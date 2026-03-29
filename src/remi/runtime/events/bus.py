"""Event bus for publishing and subscribing to lifecycle events."""

from __future__ import annotations

import abc
from collections import defaultdict
from typing import Any, Callable

from remi.runtime.events.lifecycle import InterAppEvent, LifecycleEvent
from remi.shared.ids import AppId

EventHandler = Callable[[LifecycleEvent], Any]
AppTriggerHandler = Callable[[InterAppEvent], Any]


class EventBus(abc.ABC):
    @abc.abstractmethod
    def subscribe(self, event_type: str, handler: EventHandler) -> None: ...

    @abc.abstractmethod
    async def publish(self, event: LifecycleEvent) -> None: ...

    def subscribe_app(self, app_id: AppId, event_type: str, handler: AppTriggerHandler) -> None:
        """Subscribe to events scoped to a specific app."""
        self.subscribe(f"{app_id}:{event_type}", handler)  # type: ignore[arg-type]

    async def publish_inter_app(self, event: InterAppEvent) -> None:
        """Publish an event that targets a specific app or broadcasts."""
        await self.publish(event)
        if event.target_app_id:
            scoped_key = f"{event.target_app_id}:{event.event_type}"
            if hasattr(self, "_handlers"):
                for handler in self._handlers.get(scoped_key, []):  # type: ignore[attr-defined]
                    result = handler(event)
                    if hasattr(result, "__await__"):
                        await result


class InMemoryEventBus(EventBus):
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: LifecycleEvent) -> None:
        for handler in self._handlers.get(event.event_type, []):
            result = handler(event)
            if hasattr(result, "__await__"):
                await result

        for handler in self._handlers.get("*", []):
            result = handler(event)
            if hasattr(result, "__await__"):
                await result

    async def publish_inter_app(self, event: InterAppEvent) -> None:
        await self.publish(event)
        if event.target_app_id:
            scoped_key = f"{event.target_app_id}:{event.event_type}"
            for handler in self._handlers.get(scoped_key, []):
                result = handler(event)
                if hasattr(result, "__await__"):
                    await result
