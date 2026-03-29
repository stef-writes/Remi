"""Incline: Module system — base types, ports, and builtin module implementations."""

from remi.domain.modules.base import BaseModule, ModuleOutput
from remi.domain.modules.ports import ModuleRegistry

__all__ = ["BaseModule", "ModuleOutput", "ModuleRegistry"]
