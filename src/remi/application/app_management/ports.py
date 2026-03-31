"""Ports used by app management use cases."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from remi.domain.graph.definitions import AppDefinition
    from remi.shared.ids import AppId


class AppRegistry(abc.ABC):
    """Port: stores and retrieves app definitions."""

    @abc.abstractmethod
    def register(self, app: AppDefinition) -> None: ...

    @abc.abstractmethod
    def get(self, app_id: AppId) -> AppDefinition | None: ...

    @abc.abstractmethod
    def has(self, app_id: AppId) -> bool: ...

    @abc.abstractmethod
    def list_apps(self) -> list[AppDefinition]: ...

    @abc.abstractmethod
    def remove(self, app_id: AppId) -> bool: ...

    def search_by_tags(self, tags: list[str]) -> list[AppDefinition]:
        """Find apps whose semantic_tags overlap with the given tags."""
        tag_set = set(t.lower() for t in tags)
        return [
            app for app in self.list_apps()
            if tag_set & set(t.lower() for t in app.metadata.semantic_tags)
        ]

    def search_by_domain(self, domain: str) -> list[AppDefinition]:
        """Find apps matching a domain string."""
        domain_lower = domain.lower()
        return [
            app for app in self.list_apps()
            if app.metadata.domain and domain_lower in app.metadata.domain.lower()
        ]

    def search_semantic(self, query: str) -> list[AppDefinition]:
        """Simple text search across app names, descriptions, tags, and domains."""
        query_lower = query.lower()
        results = []
        for app in self.list_apps():
            searchable = " ".join(filter(None, [
                app.metadata.name,
                app.metadata.description or "",
                app.metadata.domain or "",
                " ".join(app.metadata.semantic_tags),
                " ".join(str(v) for v in app.metadata.tags.values()),
            ])).lower()
            if query_lower in searchable:
                results.append(app)
        return results

    def list_for_llm(self) -> list[str]:
        """Return LLM-readable descriptions of all registered apps."""
        return [app.metadata.to_llm_description() for app in self.list_apps()]
