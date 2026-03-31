"""Programmatic circular-dependency detection for the entire remi package.

Uses AST parsing (no runtime imports) to build the full intra-package import
graph, then runs Tarjan's algorithm to find strongly-connected components.
Any SCC with more than one node is a circular dependency.

Three graph layers are checked:

1. **Runtime top-level** — imports that execute at module load time
   (excludes TYPE_CHECKING blocks and function/method-scoped imports).
   Cycles here cause real ``ImportError`` at startup.

2. **All top-level** — adds TYPE_CHECKING imports to layer 1.
   Cycles here won't crash at runtime but indicate unhealthy coupling and
   will break tools like mypy and pyright.

3. **Full graph** — adds function/method-body imports to layer 2.
   Cycles here are informational; deferred imports are a valid way to
   break runtime cycles, but too many may signal design issues.
"""

from __future__ import annotations

import ast
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import pytest

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
PACKAGE_ROOT = SRC_ROOT / "remi"


# ---------------------------------------------------------------------------
# File / module helpers
# ---------------------------------------------------------------------------


def _iter_python_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
        if path.name.startswith("."):
            continue
        yield path


def _path_to_module(path: Path) -> str:
    rel = path.relative_to(SRC_ROOT)
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve_import(source_module: str, module_name: str | None, level: int) -> str | None:
    if level == 0:
        return module_name
    parts = source_module.split(".")
    if level > len(parts):
        return None
    base = ".".join(parts[:-level])
    if module_name:
        return f"{base}.{module_name}" if base else module_name
    return base or None


# ---------------------------------------------------------------------------
# Import classification
# ---------------------------------------------------------------------------


@dataclass
class ClassifiedImports:
    """Imports of a single file, classified by context."""

    runtime_toplevel: set[str] = field(default_factory=set)
    type_checking: set[str] = field(default_factory=set)
    deferred: set[str] = field(default_factory=set)


def _is_type_checking_guard(node: ast.AST) -> bool:
    """Return True if the node is ``if TYPE_CHECKING:`` or ``if typing.TYPE_CHECKING:``."""
    if not isinstance(node, ast.If):
        return False
    test = node.test
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
        return True
    return False


def _collect_imports(
    node: ast.Import | ast.ImportFrom,
    source_module: str,
) -> set[str]:
    results: set[str] = set()
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name.startswith("remi.") or alias.name == "remi":
                results.add(alias.name)
    elif isinstance(node, ast.ImportFrom):
        resolved = _resolve_import(source_module, node.module, node.level)
        if resolved and (resolved.startswith("remi.") or resolved == "remi"):
            results.add(resolved)
    return results


def _extract_classified_imports(path: Path, source_module: str) -> ClassifiedImports:
    """Parse a file and classify every remi import by execution context."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return ClassifiedImports()

    result = ClassifiedImports()

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            result.runtime_toplevel |= _collect_imports(node, source_module)

        elif _is_type_checking_guard(node):
            for child in ast.walk(node):
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    result.type_checking |= _collect_imports(child, source_module)

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for child in ast.walk(node):
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    result.deferred |= _collect_imports(child, source_module)

    result.type_checking -= result.runtime_toplevel
    result.deferred -= result.runtime_toplevel | result.type_checking
    return result


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def _normalise_to_file_module(target: str, module_map: dict[str, str]) -> str | None:
    candidate = target
    while candidate:
        if candidate in module_map:
            return candidate
        if "." in candidate:
            candidate = candidate.rsplit(".", 1)[0]
        else:
            break
    return None


@dataclass
class ImportGraph:
    runtime_toplevel: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    all_toplevel: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    full: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    module_to_file: dict[str, str] = field(default_factory=dict)

    def _ensure_nodes(self) -> None:
        for mod in list(self.module_to_file):
            self.runtime_toplevel.setdefault(mod, set())
            self.all_toplevel.setdefault(mod, set())
            self.full.setdefault(mod, set())


def _build_import_graph() -> ImportGraph:
    g = ImportGraph()

    for path in _iter_python_files(PACKAGE_ROOT):
        mod = _path_to_module(path)
        g.module_to_file[mod] = str(path.relative_to(SRC_ROOT))

    g._ensure_nodes()

    for path in _iter_python_files(PACKAGE_ROOT):
        source = _path_to_module(path)
        classified = _extract_classified_imports(path, source)

        for imp in classified.runtime_toplevel:
            target = _normalise_to_file_module(imp, g.module_to_file)
            if target and target != source:
                g.runtime_toplevel[source].add(target)
                g.all_toplevel[source].add(target)
                g.full[source].add(target)

        for imp in classified.type_checking:
            target = _normalise_to_file_module(imp, g.module_to_file)
            if target and target != source:
                g.all_toplevel[source].add(target)
                g.full[source].add(target)

        for imp in classified.deferred:
            target = _normalise_to_file_module(imp, g.module_to_file)
            if target and target != source:
                g.full[source].add(target)

    return g


# ---------------------------------------------------------------------------
# Cycle detection (Tarjan's SCC)
# ---------------------------------------------------------------------------


def _tarjan_scc(graph: dict[str, set[str]]) -> list[list[str]]:
    index_counter = [0]
    stack: list[str] = []
    lowlink: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    sccs: list[list[str]] = []

    def strongconnect(v: str) -> None:
        index[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack[v] = True

        for w in sorted(graph.get(v, set())):
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif on_stack.get(w, False):
                lowlink[v] = min(lowlink[v], index[w])

        if lowlink[v] == index[v]:
            scc: list[str] = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                scc.append(w)
                if w == v:
                    break
            sccs.append(scc)

    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old_limit, len(graph) + 500))
    try:
        for v in sorted(graph):
            if v not in index:
                strongconnect(v)
    finally:
        sys.setrecursionlimit(old_limit)

    return sccs


def _find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    return [sorted(scc) for scc in _tarjan_scc(graph) if len(scc) > 1]


def _format_cycle(
    cycle: list[str],
    module_to_file: dict[str, str],
    graph: dict[str, set[str]],
) -> str:
    cycle_set = set(cycle)
    lines = [f"  Cycle with {len(cycle)} modules:"]
    for mod in cycle:
        filepath = module_to_file.get(mod, "?")
        targets = sorted(graph.get(mod, set()) & cycle_set)
        arrow = " → " + ", ".join(targets) if targets else ""
        lines.append(f"    - {mod}  ({filepath}){arrow}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCircularImports:
    """Detect circular imports across the entire remi codebase via AST analysis."""

    def test_no_runtime_circular_dependencies(self) -> None:
        """Runtime top-level imports must be acyclic — cycles here crash at startup."""
        g = _build_import_graph()
        cycles = _find_cycles(g.runtime_toplevel)
        if cycles:
            report = [f"Found {len(cycles)} RUNTIME circular dependency cycle(s):\n"]
            for cycle in sorted(cycles, key=len, reverse=True):
                report.append(_format_cycle(cycle, g.module_to_file, g.runtime_toplevel))
                report.append("")
            pytest.fail("\n".join(report))

    def test_no_type_checking_circular_dependencies(self) -> None:
        """Top-level + TYPE_CHECKING imports should be acyclic for healthy layering."""
        g = _build_import_graph()
        cycles = _find_cycles(g.all_toplevel)
        if cycles:
            report = [
                f"Found {len(cycles)} circular cycle(s) "
                f"(including TYPE_CHECKING imports):\n"
            ]
            for cycle in sorted(cycles, key=len, reverse=True):
                report.append(_format_cycle(cycle, g.module_to_file, g.all_toplevel))
                report.append("")
            pytest.fail("\n".join(report))

    def test_full_graph_circular_dependencies_reported(self) -> None:
        """Full graph (with deferred imports) — warn but don't fail on deferred-only cycles."""
        g = _build_import_graph()
        runtime_cycles = _find_cycles(g.runtime_toplevel)
        all_tl_cycles = _find_cycles(g.all_toplevel)
        full_cycles = _find_cycles(g.full)

        deferred_only = [
            c for c in full_cycles
            if c not in runtime_cycles and c not in all_tl_cycles
        ]
        if deferred_only:
            import warnings

            msg_parts = [
                f"{len(deferred_only)} cycle(s) exist only via deferred (function-body) imports:"
            ]
            for cycle in deferred_only:
                msg_parts.append(_format_cycle(cycle, g.module_to_file, g.full))
            warnings.warn("\n".join(msg_parts), stacklevel=1)

    def test_import_graph_is_nonempty(self) -> None:
        g = _build_import_graph()
        assert len(g.module_to_file) > 50, (
            f"Expected 50+ remi modules but found {len(g.module_to_file)} — "
            f"is the package root correct? ({PACKAGE_ROOT})"
        )

    def test_all_python_files_are_in_graph(self) -> None:
        g = _build_import_graph()
        files_found = set(_iter_python_files(PACKAGE_ROOT))
        modules_from_files = {_path_to_module(p) for p in files_found}
        missing = modules_from_files - set(g.runtime_toplevel.keys())
        assert not missing, f"Modules missing from graph: {missing}"
