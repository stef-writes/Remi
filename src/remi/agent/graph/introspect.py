"""Derive ObjectTypeDef schemas from Pydantic BaseModel subclasses.

Domain-agnostic: any product can pass its Pydantic entity models and get
back ``ObjectTypeDef`` instances suitable for KG type registration and
LLM prompt serialization.  REMI passes PropertyManager, Unit, Lease, etc.;
a different product would pass its own models.

The introspector walks ``model_fields``, maps Python/Pydantic types to
the ``PropertyDef`` vocabulary (string, number, decimal, date, enum, object,
boolean), and determines required-ness from the field's default.
"""

from __future__ import annotations

import types as _types
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from remi.agent.graph.types import LinkTypeDef, ObjectTypeDef, PropertyDef


def _is_strenum(annotation: Any) -> bool:
    """Return True if *annotation* is a concrete StrEnum subclass."""
    return isinstance(annotation, type) and issubclass(annotation, StrEnum)


def _unwrap_optional(annotation: Any) -> Any:
    """Strip ``Optional[X]`` / ``X | None`` down to ``X``."""
    origin = get_origin(annotation)

    if origin is Union or origin is _types.UnionType:
        args = [a for a in get_args(annotation) if a is not type(None)]
        return args[0] if len(args) == 1 else annotation

    return annotation


_PYTHON_TO_DATA_TYPE: dict[type, str] = {
    str: "string",
    int: "number",
    float: "number",
    bool: "boolean",
    Decimal: "decimal",
    date: "date",
    datetime: "datetime",
}


def _map_data_type(annotation: Any) -> tuple[str, list[str] | None]:
    """Map a Python type annotation to (data_type, enum_values | None)."""
    inner = _unwrap_optional(annotation)

    if _is_strenum(inner):
        return "enum", [e.value for e in inner]

    if isinstance(inner, type) and issubclass(inner, BaseModel):
        return "object", None

    mapped = _PYTHON_TO_DATA_TYPE.get(inner)
    if mapped:
        return mapped, None

    origin = get_origin(inner)
    if origin is list:
        return "list", None

    return "string", None


def _field_required(info: FieldInfo) -> bool:
    """A field is required if it has no default and no default_factory."""
    has_default = info.default is not PydanticUndefined
    has_factory = info.default_factory is not None
    return not has_default and not has_factory


_SKIP_FIELDS: frozenset[str] = frozenset({
    "created_at", "updated_at", "source_document_id",
})


def pydantic_to_type_def(
    model: type[BaseModel],
    *,
    description: str = "",
    plural_name: str | None = None,
    skip_fields: frozenset[str] | None = None,
) -> ObjectTypeDef:
    """Convert a single Pydantic model class to an ``ObjectTypeDef``.

    Parameters
    ----------
    model:
        The Pydantic BaseModel subclass to introspect.
    description:
        Human-readable description for the type.  Falls back to the
        class docstring if not provided.
    plural_name:
        Plural form of the type name for display.
    skip_fields:
        Field names to omit from the schema.  Defaults to internal
        bookkeeping fields (``created_at``, ``updated_at``,
        ``source_document_id``).
    """
    effective_skip = skip_fields if skip_fields is not None else _SKIP_FIELDS
    props: list[PropertyDef] = []

    for name, info in model.model_fields.items():
        if name in effective_skip:
            continue

        annotation = info.annotation
        if annotation is None:
            data_type, enum_values = "string", None
        else:
            data_type, enum_values = _map_data_type(annotation)

        props.append(PropertyDef(
            name=name,
            data_type=data_type,
            required=_field_required(info),
            enum_values=enum_values,
        ))

    desc = description or (model.__doc__ or "").strip()

    return ObjectTypeDef(
        name=model.__name__,
        plural_name=plural_name or model.__name__ + "s",
        description=desc,
        properties=tuple(props),
    )


def pydantic_to_type_defs(
    models: list[tuple[type[BaseModel], str] | tuple[type[BaseModel], str, str]],
    *,
    skip_fields: frozenset[str] | None = None,
) -> list[ObjectTypeDef]:
    """Convert multiple Pydantic models to ``ObjectTypeDef`` instances.

    Each entry is ``(ModelClass, description)`` or
    ``(ModelClass, description, plural_name)``.
    """
    result: list[ObjectTypeDef] = []
    for entry in models:
        if len(entry) == 3:
            model, desc, plural = entry  # type: ignore[misc]
        else:
            model, desc = entry  # type: ignore[misc]
            plural = None
        result.append(pydantic_to_type_def(
            model, description=desc, plural_name=plural,  # type: ignore[arg-type]
            skip_fields=skip_fields,
        ))
    return result


def schemas_for_prompt(
    type_defs: list[ObjectTypeDef],
    *,
    link_defs: list[LinkTypeDef] | None = None,
    filter_names: frozenset[str] | None = None,
) -> str:
    """Render ``ObjectTypeDef`` instances as structured text for LLM prompts.

    Parameters
    ----------
    type_defs:
        The type definitions to render.
    link_defs:
        Optional relationship definitions.  When provided, relationships
        involving each type are appended.
    filter_names:
        If provided, only types whose ``name`` is in this set are included.
    """
    lines: list[str] = []

    for typedef in type_defs:
        if filter_names is not None and typedef.name not in filter_names:
            continue
        lines.append(f"Entity: {typedef.name}")
        if typedef.description:
            lines.append(f"  Description: {typedef.description}")

        field_parts: list[str] = []
        for prop in typedef.properties:
            if prop.name == "id":
                continue
            part = prop.name
            if prop.data_type == "enum" and prop.enum_values:
                part += f" (enum: {'/'.join(prop.enum_values)})"
            else:
                part += f" ({prop.data_type})"
            if prop.required:
                part += " [required]"
            field_parts.append(part)

        if field_parts:
            lines.append(f"  Fields: {', '.join(field_parts)}")

        if link_defs:
            rels = _links_for_type(typedef.name, link_defs)
            if rels:
                lines.append(f"  Relationships: {', '.join(rels)}")

        lines.append("")

    return "\n".join(lines).rstrip()


def _links_for_type(type_name: str, link_defs: list[LinkTypeDef]) -> list[str]:
    results: list[str] = []
    for link in link_defs:
        if link.source_type == type_name:
            results.append(f"{link.name} -> {link.target_type}")
        elif link.target_type == type_name and link.source_type != "*":
            results.append(f"{link.source_type} -[{link.name}]-> {type_name}")
    return results
