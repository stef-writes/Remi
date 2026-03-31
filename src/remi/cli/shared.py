"""Shared CLI utilities — container bootstrapping and output formatting."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import typer

from remi.config.container import Container
from remi.config.settings import load_settings
from remi.observability.logging import configure_logging


def get_container() -> Container:
    """Create a local Container with logging configured."""
    settings = load_settings()
    configure_logging(level=settings.logging.level, format=settings.logging.format)
    return Container(settings)


async def get_container_async() -> Container:
    """Create a fully bootstrapped Container."""
    container = get_container()
    await container.ensure_bootstrapped()
    return container


def use_json(flag: bool) -> bool:
    return flag or not sys.stdout.isatty()


def json_out(data: Any) -> None:
    """Write structured JSON to stdout (JSONL-friendly)."""
    typer.echo(json.dumps(data, default=str))


def parse_params(raw: list[str]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for item in raw:
        if "=" not in item:
            continue
        key, _, value = item.partition("=")
        try:
            params[key.strip()] = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            params[key.strip()] = value
    return params


def ser(obj: Any) -> Any:
    """Recursively serialize Decimals to floats and dates to ISO strings."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: ser(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [ser(v) for v in obj]
    return obj
