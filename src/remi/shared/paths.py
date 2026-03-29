"""Canonical paths for the REMI package."""

from __future__ import annotations

from pathlib import Path

REMI_PACKAGE_DIR = Path(__file__).resolve().parent.parent

WORKFLOWS_DIR = REMI_PACKAGE_DIR / "workflows"

DOMAIN_YAML_PATH = WORKFLOWS_DIR / "domain.yaml"
