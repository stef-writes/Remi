"""Canonical paths for the REMI package."""

from __future__ import annotations

from pathlib import Path

REMI_PACKAGE_DIR = Path(__file__).resolve().parent.parent

AGENTS_DIR = REMI_PACKAGE_DIR / "domain" / "agents"

DOMAIN_YAML_PATH = REMI_PACKAGE_DIR / "shell" / "config" / "domain.yaml"
