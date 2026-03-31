"""SandboxSeeder — export store data into a sandbox session for agent analysis.

Seeds two categories of files into the sandbox working directory:

1. **CSV/JSON snapshots** — static exports of PropertyStore + SignalStore data
   for pandas-based analysis. These are point-in-time snapshots.

2. **remi_client.py** — a stdlib-only Python module that sandbox scripts can
   import to query the live ontology API. This gives agent scripts access to
   current data, codification, and the full OntologyStore interface.

Uses stdlib csv and json — no extra dependencies.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from remi.domain.ontology.ports import OntologyStore
    from remi.domain.properties.ports import PropertyStore
    from remi.domain.sandbox.ports import Sandbox
    from remi.domain.signals.ports import SignalStore

_log = structlog.get_logger(__name__)

_ENTITY_EXPORTS: list[tuple[str, str]] = [
    ("managers", "list_managers"),
    ("portfolios", "list_portfolios"),
    ("properties", "list_properties"),
    ("units", "list_units"),
    ("leases", "list_leases"),
    ("tenants", "list_tenants"),
    ("maintenance", "list_maintenance_requests"),
]

_CLIENT_TEMPLATE_PATH = Path(__file__).parent / "client_template.py"


class SandboxSeeder:
    """Seeds a sandbox session with CSV/JSON exports and a live API client."""

    def __init__(
        self,
        property_store: PropertyStore,
        signal_store: SignalStore,
        *,
        ontology_store: OntologyStore | None = None,
        api_base_url: str = "http://127.0.0.1:8000",
    ) -> None:
        self._property_store = property_store
        self._signal_store = signal_store
        self._ontology_store = ontology_store
        self._api_base_url = api_base_url

    async def seed(self, sandbox: Sandbox, session_id: str) -> list[str]:
        """Write data files into the sandbox session. Returns list of filenames."""
        files_written: list[str] = []

        for filename_stem, method_name in _ENTITY_EXPORTS:
            rows = await getattr(self._property_store, method_name)()
            dicts = [_model_to_dict(r) for r in rows]
            csv_content = _dicts_to_csv(dicts)
            fname = f"{filename_stem}.csv"
            await sandbox.write_file(session_id, fname, csv_content)
            files_written.append(fname)
            _log.debug("sandbox_seeded_csv", file=fname, rows=len(dicts))

        signals = await self._signal_store.list_signals()
        signals_data = [_model_to_dict(s) for s in signals]
        signals_json = json.dumps(signals_data, indent=2, default=str)
        await sandbox.write_file(session_id, "signals.json", signals_json)
        files_written.append("signals.json")
        _log.debug("sandbox_seeded_signals", count=len(signals_data))

        client_file = await self._seed_client(sandbox, session_id)
        if client_file:
            files_written.append(client_file)

        readme = _build_readme(files_written, api_url=self._api_base_url)
        await sandbox.write_file(session_id, "README.txt", readme)
        files_written.append("README.txt")

        _log.info("sandbox_seed_complete", session_id=session_id, files=len(files_written))
        return files_written

    async def _seed_client(self, sandbox: Sandbox, session_id: str) -> str | None:
        """Write the remi_client.py SDK module into the sandbox."""
        try:
            if _CLIENT_TEMPLATE_PATH.exists():
                content = _CLIENT_TEMPLATE_PATH.read_text(encoding="utf-8")
            else:
                return None

            content = content.replace(
                '_BASE_URL = os.environ.get("REMI_API_URL", "http://127.0.0.1:8000")',
                f'_BASE_URL = os.environ.get("REMI_API_URL", "{self._api_base_url}")',
            )

            await sandbox.write_file(session_id, "remi_client.py", content)
            _log.debug("sandbox_seeded_client", api_url=self._api_base_url)
            return "remi_client.py"
        except Exception:
            _log.warning("sandbox_client_seed_failed", exc_info=True)
            return None


def _model_to_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    return dict(obj) if hasattr(obj, "__iter__") else {"value": str(obj)}


def _dicts_to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    buf = io.StringIO()
    fieldnames = list(rows[0].keys())
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _serialize_value(v) for k, v in row.items()})
    return buf.getvalue()


def _serialize_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, dict)):
        return json.dumps(v, default=str)
    return str(v)


def _build_readme(files: list[str], *, api_url: str = "http://127.0.0.1:8000") -> str:
    lines = [
        "REMI Sandbox Data Files",
        "=" * 40,
        "",
        "These files are auto-generated exports of the current REMI data.",
        "",
        "## Static snapshots (CSV/JSON)",
        "",
        "Use in your Python scripts: pd.read_csv('properties.csv')",
        "",
    ]
    for f in files:
        if f in ("README.txt", "remi_client.py"):
            continue
        lines.append(f"  - {f}")

    lines.append("")
    lines.append("CSV files use comma delimiters with headers in the first row.")
    lines.append("signals.json contains the currently active entailed signals.")
    lines.append("")
    lines.append("## Live API client")
    lines.append("")
    lines.append("For live data (not snapshots), use the remi_client module:")
    lines.append("")
    lines.append("    from remi_client import remi")
    lines.append("")
    lines.append("    managers = remi.search('PropertyManager')")
    lines.append("    signals = remi.signals()")
    lines.append("    count = remi.aggregate('Lease', 'count')")
    lines.append("    remi.codify('observation', {'description': 'finding...'})")
    lines.append("")
    lines.append(f"API: {api_url}")
    lines.append("")
    return "\n".join(lines)
