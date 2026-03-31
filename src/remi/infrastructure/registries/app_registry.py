"""In-memory app registry — stores and retrieves app definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from remi.application.app_management.ports import AppRegistry

if TYPE_CHECKING:
    from remi.domain.graph.definitions import AppDefinition
    from remi.shared.ids import AppId


class InMemoryAppRegistry(AppRegistry):
    def __init__(self) -> None:
        self._apps: dict[AppId, AppDefinition] = {}

    def register(self, app: AppDefinition) -> None:
        self._apps[app.app_id] = app

    def get(self, app_id: AppId) -> AppDefinition | None:
        return self._apps.get(app_id)

    def has(self, app_id: AppId) -> bool:
        return app_id in self._apps

    def list_apps(self) -> list[AppDefinition]:
        return list(self._apps.values())

    def remove(self, app_id: AppId) -> bool:
        return self._apps.pop(app_id, None) is not None
