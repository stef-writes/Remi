"""Evaluators for lease cliff and policy breach (renewal + make-ready)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from remi.knowledge.entailment.base import MakeSignalFn
    from remi.models.properties import PropertyStore
    from remi.models.signals import DomainOntology, Signal, SignalDefinition


async def eval_manager_lease_cliff(
    defn: SignalDefinition,
    domain: DomainOntology,
    ps: PropertyStore,
    make_signal: MakeSignalFn,
) -> list[Signal]:
    rule = defn.rule
    cliff_pct = domain.threshold(rule.threshold_key or "lease_cliff_pct", 0.30)
    window_days = int(domain.threshold(rule.window_key or "lease_cliff_window_days", 60))
    cutoff = date.today() + timedelta(days=window_days)

    managers = await ps.list_managers()
    signals: list[Signal] = []

    for mgr in managers:
        portfolios = await ps.list_portfolios(manager_id=mgr.id)
        all_leases = []
        for pf in portfolios:
            properties = await ps.list_properties(portfolio_id=pf.id)
            for prop in properties:
                leases = await ps.list_leases(property_id=prop.id)
                all_leases.extend(leases)

        active_leases = [ls for ls in all_leases if ls.status.value == "active"]
        if not active_leases:
            continue

        expiring = [ls for ls in active_leases if ls.end_date <= cutoff]
        expiring_pct = len(expiring) / len(active_leases)

        if expiring_pct >= cliff_pct:
            expiring_details = [
                {
                    "lease_id": ls.id,
                    "unit_id": ls.unit_id,
                    "end_date": ls.end_date.isoformat(),
                    "monthly_rent": float(ls.monthly_rent),
                }
                for ls in sorted(expiring, key=lambda x: x.end_date)[:20]
            ]
            signals.append(
                make_signal(
                    defn=defn,
                    entity_id=mgr.id,
                    entity_name=mgr.name,
                    description=(
                        f"{len(expiring)} of {len(active_leases)} active leases "
                        f"({expiring_pct:.0%}) expire within {window_days} days"
                    ),
                    evidence={
                        "expiring_count": len(expiring),
                        "total_active": len(active_leases),
                        "expiring_pct": round(expiring_pct, 4),
                        "window_days": window_days,
                        "threshold_pct": cliff_pct,
                        "expiring_leases": expiring_details,
                        "manager_id": mgr.id,
                    },
                )
            )
    return signals


async def eval_breach_detected(
    defn: SignalDefinition,
    domain: DomainOntology,
    ps: PropertyStore,
    make_signal: MakeSignalFn,
) -> list[Signal]:
    """Fires when required policy actions haven't happened within deadlines."""
    renewal_window = int(domain.threshold("renewal_outreach_days_before", 90))
    make_ready_days = int(domain.threshold("make_ready_deadline_days", 14))
    cutoff = date.today() + timedelta(days=renewal_window)
    now = datetime.now(UTC)

    managers = await ps.list_managers()
    signals: list[Signal] = []

    for mgr in managers:
        portfolios = await ps.list_portfolios(manager_id=mgr.id)
        breaches: list[dict[str, Any]] = []

        for pf in portfolios:
            properties = await ps.list_properties(portfolio_id=pf.id)
            for prop in properties:
                leases = await ps.list_leases(property_id=prop.id)
                active = [ls for ls in leases if ls.status.value == "active"]
                pending_units = {ls.unit_id for ls in leases if ls.status.value == "pending"}

                for lease in active:
                    if lease.end_date <= cutoff and lease.unit_id not in pending_units:
                        days_until = (lease.end_date - date.today()).days
                        breaches.append(
                            {
                                "type": "renewal_not_sent",
                                "lease_id": lease.id,
                                "unit_id": lease.unit_id,
                                "end_date": lease.end_date.isoformat(),
                                "days_until_expiry": days_until,
                                "monthly_rent": float(lease.monthly_rent),
                                "property_id": prop.id,
                                "property_name": prop.name,
                            }
                        )

                units = await ps.list_units(property_id=prop.id)
                vacant_units = [u for u in units if u.status.value == "vacant"]
                maint = await ps.list_maintenance_requests(property_id=prop.id)
                open_maint_by_unit: dict[str, list[Any]] = {}
                for req in maint:
                    if req.status.value in ("open", "in_progress"):
                        age = (now - req.created_at).days
                        if age > make_ready_days:
                            open_maint_by_unit.setdefault(req.unit_id, []).append(req)

                for vu in vacant_units:
                    overdue = open_maint_by_unit.get(vu.id)
                    if overdue:
                        breaches.append(
                            {
                                "type": "make_ready_overdue",
                                "unit_id": vu.id,
                                "unit_number": vu.unit_number,
                                "property_id": prop.id,
                                "property_name": prop.name,
                                "overdue_orders": len(overdue),
                                "oldest_days": max((now - r.created_at).days for r in overdue),
                            }
                        )

        if breaches:
            breaches.sort(key=lambda b: b.get("days_until_expiry", 999))
            signals.append(
                make_signal(
                    defn=defn,
                    entity_id=mgr.id,
                    entity_name=mgr.name,
                    description=(
                        f"{len(breaches)} policy breach(es) detected: "
                        f"{sum(1 for b in breaches if b['type'] == 'renewal_not_sent')} "
                        f"renewal(s) not sent, "
                        f"{sum(1 for b in breaches if b['type'] == 'make_ready_overdue')} "
                        f"make-ready overdue"
                    ),
                    evidence={
                        "breach_count": len(breaches),
                        "breaches": breaches[:20],
                        "manager_id": mgr.id,
                    },
                )
            )
    return signals
