"""YAML loader — parses app definition files into domain objects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from remi.domain.graph.definitions import (
    AppDefinition,
    AppMetadata,
    AppSettings,
    EdgeDefinition,
    ModuleDefinition,
)
from remi.shared.errors import ValidationError
from remi.shared.ids import AppId, ModuleId


class YamlAppLoader:
    """Loads and parses app definitions from YAML files."""

    def load(self, path: str | Path) -> AppDefinition:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"App definition not found: {path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        dir_name = path.parent.name if path.parent.name != "." else None
        return self.parse(data, source=str(path), dir_name=dir_name)

    def load_directory(self, directory: str | Path) -> list[AppDefinition]:
        directory = Path(directory)
        apps: list[AppDefinition] = []
        for path in sorted(directory.rglob("app.yaml")):
            apps.append(self.load(path))
        return apps

    def parse(self, data: dict[str, Any], source: str = "<inline>", dir_name: str | None = None) -> AppDefinition:
        if not isinstance(data, dict):
            raise ValidationError(f"Expected dict, got {type(data).__name__}", field="root")

        meta_data = data.get("metadata", {})
        raw_tags = meta_data.get("tags", [])
        if isinstance(raw_tags, dict):
            raw_tags = list(raw_tags.keys())

        explicit_id = meta_data.get("app_id", "")
        if not explicit_id and dir_name:
            explicit_id = dir_name
        elif not explicit_id:
            explicit_id = meta_data.get("name", "unnamed")

        metadata = AppMetadata(
            app_id=AppId(explicit_id),
            name=meta_data.get("name", ""),
            version=meta_data.get("version", "1.0.0"),
            description=meta_data.get("description"),
            tags=raw_tags,
            semantic_tags=meta_data.get("semantic_tags", []),
            input_schema=meta_data.get("input_schema", {}),
            output_schema=meta_data.get("output_schema", {}),
            domain=meta_data.get("domain"),
        )

        settings_data = data.get("settings", {})
        planner_raw = settings_data.get("planner_module")
        settings_tags = settings_data.get("tags", [])
        if isinstance(settings_tags, dict):
            settings_tags = list(settings_tags.keys())
        settings = AppSettings(
            execution_mode=settings_data.get("execution_mode", "full"),
            state_store=settings_data.get("state_store", "in_memory"),
            entrypoints=[
                ModuleId(e) for e in settings_data.get("entrypoints", [])
            ],
            tags=settings_tags,
            planner_module=ModuleId(planner_raw) if planner_raw else None,
        )

        modules = [
            ModuleDefinition(
                id=ModuleId(m["id"]),
                kind=m["kind"],
                version=m.get("version", "1.0.0"),
                config=m.get("config", {}),
                input_contract=m.get("input_contract"),
                output_contract=m.get("output_contract"),
                input_schema=m.get("input_schema", {}),
                output_schema=m.get("output_schema", {}),
                capabilities=m.get("capabilities", []),
                semantic_tags=m.get("semantic_tags", []),
                description=m.get("description"),
            )
            for m in data.get("modules", [])
        ]

        edges = [
            EdgeDefinition(
                from_module=ModuleId(e.get("from_module") or e["from"]),
                to_module=ModuleId(e.get("to_module") or e["to"]),
                condition=e.get("condition"),
            )
            for e in data.get("edges", [])
        ]

        return AppDefinition(
            api_version=data.get("apiVersion", "remi/v1"),
            kind=data.get("kind", "App"),
            metadata=metadata,
            settings=settings,
            modules=modules,
            edges=edges,
        )
