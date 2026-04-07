"""Ingestion workflow tools — registered on the shared ToolRegistry.

The document_ingestion YAML workflow calls these tools as transform/for_each
steps. They are registered by ``register_ingestion_tools`` immediately before
each ``WorkflowRunner.run`` call, closed over per-upload state.

Tool inventory (DAG order):
  initialize      — creates IngestionCtx, resolves manager, stamps report_type
  merge_maps      — merges extract.column_map + inspect.column_map (inspect wins)
  apply_column_map — rename columns, normalize addresses, section context
  validate_rows   — required-field checks, emits RowWarnings
  persist_row     — per-row entity persistence via ROW_PERSISTERS

The ``upload_manager_hint`` is passed from the API/tool layer as a fallback
for when the LLM cannot extract a manager name from the document itself.
Entity-level manager assignment is always decided inside this layer, never
by the caller.
"""

from __future__ import annotations

from typing import Any

import structlog

from remi.agent.llm.types import ToolDefinition
from remi.agent.types import ToolRegistry
from remi.application.core.models.enums import ReportType
from remi.application.core.protocols import PropertyStore
from remi.application.services.ingestion.base import IngestionResult, RowWarning
from remi.application.services.ingestion.mapper import apply_column_map
from remi.application.services.ingestion.managers import ManagerResolver
from remi.application.services.ingestion.persisters import ROW_PERSISTERS
from remi.application.services.ingestion.validation import validate_rows

_log = structlog.get_logger(__name__)

# Scopes that map to a single managing person.
_MANAGER_SCOPES = frozenset({"manager_portfolio", "single_property", "single_unit"})


def _make_ctx(
    ps: PropertyStore,
    doc_id: str,
    platform: str,
    report_type: ReportType,
    result: IngestionResult,
) -> Any:
    """Create a fresh IngestionCtx. Imported lazily to avoid circular imports."""
    from remi.application.services.ingestion.context import IngestionCtx
    return IngestionCtx(
        platform=platform,
        report_type=report_type,
        doc_id=doc_id,
        namespace="ingestion",
        ps=ps,
        manager_resolver=ManagerResolver(ps),
        result=result,
    )


def register_ingestion_tools(
    registry: ToolRegistry,
    # These are the only pre-upload facts the host knows:
    ps: PropertyStore,
    doc_id: str,
    platform: str,
    result: IngestionResult,
    all_rows: list[dict[str, Any]],
    upload_manager_hint: str | None = None,
) -> None:
    """Register ingestion transform tools, closed over this upload's state.

    Note: IngestionCtx is created by the ``initialize`` tool (first transform
    step in the YAML) so the workflow owns ctx creation, not the host.
    """
    # ctx is None until the initialize tool runs — all other tools check it.
    # Using a list as a mutable cell so inner functions can rebind it.
    _ctx_cell: list[Any] = [None]

    def _ctx() -> Any:
        c = _ctx_cell[0]
        if c is None:
            raise RuntimeError("initialize tool must run before other ingestion tools")
        return c

    # -------------------------------------------------------------------------
    # initialize
    # Receives (via wires): report_type, scope, manager_name
    # Creates IngestionCtx, resolves manager, stamps report_type on result.
    # Returns: { manager_id, manager_name, report_type, created_new }
    # -------------------------------------------------------------------------
    async def _initialize_tool(args: dict[str, Any]) -> dict[str, Any]:
        raw_rt: str = str(args.get("report_type") or "unknown").strip()
        scope: str = str(args.get("scope") or "unknown").strip()
        manager_name: str | None = args.get("manager_name") or None

        try:
            rt = ReportType(raw_rt)
        except ValueError:
            rt = ReportType.UNKNOWN

        ctx = _make_ctx(ps, doc_id, platform, rt, result)
        _ctx_cell[0] = ctx
        result.report_type = rt

        # Resolve manager: LLM-extracted name takes priority, hint is fallback
        candidate = manager_name or upload_manager_hint
        resolved_manager_id: str | None = None
        resolved_manager_name: str | None = None
        created_new = False

        if candidate and scope in _MANAGER_SCOPES:
            resolver = ManagerResolver(ps)
            resolution = await resolver.ensure_manager(candidate)
            resolved_manager_id = resolution.manager_id
            resolved_manager_name = resolution.manager_name
            created_new = resolution.created_new
            ctx.upload_manager_id = resolution.manager_id

            _log.info(
                "ingestion_manager_resolved",
                manager_id=resolution.manager_id,
                manager_name=resolution.manager_name,
                source="llm_extract" if manager_name else "upload_hint",
                created_new=resolution.created_new,
                scope=scope,
                report_type=rt.value,
            )
        else:
            _log.info(
                "ingestion_manager_skipped",
                scope=scope,
                candidate=candidate,
                report_type=rt.value,
            )

        return {
            "manager_id": resolved_manager_id,
            "manager_name": resolved_manager_name,
            "report_type": rt.value,
            "created_new": created_new,
        }

    # -------------------------------------------------------------------------
    # merge_maps
    # Receives (via wires): base_map (from extract), override_map (from inspect,
    #   may be absent/null when the inspect gate was skipped)
    # Returns: { column_map } — inspect entries override extract entries
    # -------------------------------------------------------------------------
    async def _merge_maps_tool(args: dict[str, Any]) -> dict[str, Any]:
        base: dict[str, str] = args.get("base_map") or {}
        override: dict[str, str] = args.get("override_map") or {}
        merged = {**base, **override}
        _log.info(
            "merge_maps",
            base_keys=len(base),
            override_keys=len(override),
            merged_keys=len(merged),
            overridden=[k for k in override if k in base and base[k] != override[k]],
        )
        return {"column_map": merged}

    # -------------------------------------------------------------------------
    # apply_column_map
    # Receives (via wires): column_map, entity_type, section_header_column
    # Returns: { rows, total, mapped }
    # -------------------------------------------------------------------------
    async def _apply_column_map_tool(args: dict[str, Any]) -> dict[str, Any]:
        column_map: dict[str, str] = args.get("column_map", {})
        entity_type: str = args.get("entity_type", "")
        section_header: str | None = args.get("section_header_column")

        if not column_map or not entity_type:
            _log.warning(
                "apply_column_map_empty",
                has_map=bool(column_map),
                entity_type=entity_type,
            )
            return {"rows": [], "skipped": 0}

        mapped = apply_column_map(
            all_rows, column_map, entity_type,
            section_header_column=section_header,
        )
        return {"rows": mapped, "total": len(all_rows), "mapped": len(mapped)}

    # -------------------------------------------------------------------------
    # validate_rows
    # Receives (via wire): rows from map_rows
    # Returns: { accepted, total, accepted_count, rejected_count }
    # -------------------------------------------------------------------------
    async def _validate_rows_tool(args: dict[str, Any]) -> dict[str, Any]:
        rows = args.get("rows", [])
        if not isinstance(rows, list):
            rows = []
        accepted = validate_rows(rows, result)
        return {
            "accepted": accepted,
            "total": len(rows),
            "accepted_count": len(accepted),
            "rejected_count": result.rows_rejected,
        }

    # -------------------------------------------------------------------------
    # persist_row
    # Receives: a single validated row dict (for_each over validate_rows.accepted)
    # Returns: { status, type }
    # -------------------------------------------------------------------------
    async def _persist_row_tool(args: dict[str, Any]) -> dict[str, str]:
        ctx = _ctx()
        entity_type = args.get("type", "")
        persister = ROW_PERSISTERS.get(entity_type)

        if persister is None:
            result.observation_rows.append(args)
            result.rows_skipped += 1
            return {"status": "skipped", "type": entity_type}

        try:
            await persister(args, ctx)
            return {"status": "ok", "type": entity_type}
        except Exception as exc:
            _log.warning(
                "row_persist_error",
                entity_type=entity_type,
                error=str(exc),
                exc_info=True,
            )
            result.persist_errors.append(
                RowWarning(
                    row_index=0,
                    row_type=entity_type,
                    field="",
                    issue="persistence failed",
                    raw_value=str(args)[:200],
                )
            )
            result.rows_rejected += 1
            raise

    registry.register(
        "initialize",
        _initialize_tool,
        ToolDefinition(
            name="initialize",
            description="Create ingestion context, resolve manager, stamp report type",
        ),
    )
    registry.register(
        "merge_maps",
        _merge_maps_tool,
        ToolDefinition(
            name="merge_maps",
            description="Merge extract and inspect column maps; inspect entries win",
        ),
    )
    registry.register(
        "apply_column_map",
        _apply_column_map_tool,
        ToolDefinition(
            name="apply_column_map",
            description="Map document columns to entity fields",
        ),
    )
    registry.register(
        "validate_rows",
        _validate_rows_tool,
        ToolDefinition(
            name="validate_rows",
            description="Validate mapped rows for ingestion",
        ),
    )
    registry.register(
        "persist_row",
        _persist_row_tool,
        ToolDefinition(
            name="persist_row",
            description="Persist a single validated row",
        ),
    )
