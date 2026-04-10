"""Portfolio — manager aggregation, summaries, and rankings."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal

from remi.application.core.models import (
    BalanceObservation,
    Lease,
    LeaseStatus,
    MaintenanceRequest,
    OccupancyStatus,
    Unit,
)
from remi.application.core.protocols import PropertyStore
from remi.application.core.rules import (
    active_lease,
    is_below_market,
    is_maintenance_open,
    is_occupied,
    loss_to_lease,
)

from .views import (
    DataCoverage,
    ManagerMetrics,
    ManagerRanking,
    ManagerSummary,
    PropertySummary,
    UnitIssue,
)


def _group_by_unit(leases: list[Lease]) -> dict[str, list[Lease]]:
    result: dict[str, list[Lease]] = {}
    for le in leases:
        result.setdefault(le.unit_id, []).append(le)
    return result


def _is_unit_occupied(u: Unit, unit_leases: list[Lease]) -> bool:
    """True when the unit has an active lease OR the rent roll flagged it occupied.

    Lease evidence is primary. Unit.occupancy_status from the rent roll is the
    fallback for units where we have physical data but no matching lease record
    (e.g. the rent roll has lease dates but no tenant name or rent figure).
    """
    if is_occupied(unit_leases):
        return True
    occ = u.occupancy_status
    return occ in (
        OccupancyStatus.OCCUPIED,
        OccupancyStatus.NOTICE_RENTED,
        OccupancyStatus.NOTICE_UNRENTED,
    )


def _compute_coverage(
    all_units: list[Unit],
    all_leases: list[Lease],
    all_maint: list[MaintenanceRequest],
    obs_list: list,
    declared_units: int,
) -> DataCoverage:
    """Infer data completeness from what's actually in the graph.

    No document-store query needed — we check for the presence of physical
    data fields (beds/baths, market_rent, occupancy_status) that only appear
    after a rent roll has been ingested.
    """
    n_rec = len(all_units)
    n_dec = max(declared_units, 1)

    has_beds   = sum(1 for u in all_units if u.bedrooms is not None)
    has_market = sum(1 for u in all_units if u.market_rent and u.market_rent > 0)
    has_occ_s  = sum(1 for u in all_units if u.occupancy_status is not None)

    has_rent_roll    = n_rec > 0 and (
        # Rent roll creates unit records for ALL units in the portfolio.
        # Proxy: record coverage >= 90%, OR any unit has physical data.
        (n_rec / n_dec >= 0.90)
        or has_beds > 0
        or has_occ_s > 0
    )
    has_lease_data        = len(all_leases) > 0
    has_delinquency_data  = len(obs_list) > 0
    has_maintenance_data  = len(all_maint) > 0

    missing: list[str] = []
    if not has_rent_roll:
        missing.append("rent_roll")
    if not has_lease_data:
        missing.append("lease_expiration")
    if not has_delinquency_data:
        missing.append("delinquency")
    if not has_maintenance_data:
        missing.append("work_orders")

    rec_pct   = round(n_rec / n_dec, 3)
    phys_pct  = round(has_beds   / max(n_rec, 1), 3)
    mrkt_pct  = round(has_market / max(n_rec, 1), 3)

    if has_rent_roll and has_lease_data:
        confidence = "full"
        caveat = (
            "Data from rent roll and lease reports. "
            "Metrics are reliable; upload work orders for maintenance accuracy."
        ) if has_maintenance_data else (
            "Data from rent roll and lease reports. "
            "Occupancy and rent figures are reliable; no maintenance data loaded yet."
        )
    elif has_lease_data or has_delinquency_data:
        confidence = "partial"
        gap_pct = round((1 - rec_pct) * 100)
        caveat = (
            f"Partial data — rent roll not yet loaded. "
            f"{gap_pct}% of declared units have no individual records. "
            "Occupancy rate may be understated; unit-level physical data (beds/baths, "
            "market rent) is sparse. Upload a rent roll to improve accuracy."
        )
    else:
        confidence = "sparse"
        caveat = (
            "Only property directory loaded — no leases, rent roll, or delinquency data. "
            "All metrics (occupancy, revenue, delinquency) are zero or estimates. "
            "Do not cite specific figures without qualifying this caveat."
        )

    return DataCoverage(
        has_rent_roll=has_rent_roll,
        has_lease_data=has_lease_data,
        has_delinquency_data=has_delinquency_data,
        has_maintenance_data=has_maintenance_data,
        unit_record_coverage=rec_pct,
        units_with_physical_data=phys_pct,
        units_with_market_rent=mrkt_pct,
        confidence=confidence,
        missing_report_types=missing,
        caveat=caveat,
    )


def _latest_obs_by_tenant(obs_list: list) -> dict[str, object]:
    latest: dict[str, object] = {}
    for obs in obs_list:
        existing = latest.get(obs.tenant_id)
        if existing is None or obs.observed_at > existing.observed_at:  # type: ignore[union-attr]
            latest[obs.tenant_id] = obs
    return latest


class ManagerResolver:
    """Director-level portfolio roll-up over PropertyStore."""

    def __init__(self, property_store: PropertyStore) -> None:
        self._ps = property_store

    async def aggregate_manager(self, manager_id: str) -> ManagerSummary | None:
        manager = await self._ps.get_manager(manager_id)
        if not manager:
            return None

        all_properties = await self._ps.list_properties(manager_id=manager_id)
        today = date.today()

        total_units = 0
        occupied = 0
        vacant = 0
        total_market = Decimal("0")
        total_actual = Decimal("0")
        total_loss_to_lease_val = Decimal("0")
        total_vacancy_loss = Decimal("0")
        open_maintenance = 0
        emergency_maintenance = 0
        expiring_leases_90d = 0
        expired_leases = 0
        below_market_units = 0
        property_count = 0

        property_summaries: list[PropertySummary] = []
        top_issues: list[UnitIssue] = []

        async def _load_prop(
            prop_id: str,
        ) -> tuple[list[Unit], list[Lease], list[MaintenanceRequest], list[BalanceObservation]]:
            u, le, m, obs = await asyncio.gather(
                self._ps.list_units(property_id=prop_id),
                self._ps.list_leases(property_id=prop_id),
                self._ps.list_maintenance_requests(property_id=prop_id),
                self._ps.list_balance_observations(property_id=prop_id),
            )
            return u, le, m, obs

        prop_data = await asyncio.gather(*[_load_prop(prop.id) for prop in all_properties])

        for prop, (units, leases, maint, obs_list) in zip(all_properties, prop_data, strict=True):
            property_count += 1
            leases_by_unit = _group_by_unit(leases)

            # Confirmed occupants from delinquency and lease records.
            # Each distinct tenant with a BalanceObservation or active lease is
            # a known occupant. Union the two sets to avoid double-counting.
            lease_tenant_ids: set[str] = {
                le.tenant_id
                for le in leases
                if le.tenant_id and active_lease([le]) is not None
            }
            balance_tenant_ids: set[str] = {obs.tenant_id for obs in obs_list}
            confirmed_tenant_ids = lease_tenant_ids | balance_tenant_ids
            confirmed_count = len(confirmed_tenant_ids)

            # Unit denominator: declared count beats known records beats confirmed
            # occupants. When we have no unit records and no declared count but we
            # DO have confirmed tenants (delinquency-only data), the tenant count
            # is the best available lower bound for total units at this property.
            known_units = len(units)
            p_units = max(known_units, prop.unit_count or 0, confirmed_count)

            # Unit-level occupancy from lease records and rent-roll status.
            p_occ_from_units = sum(
                1 for u in units
                if _is_unit_occupied(u, leases_by_unit.get(u.id, []))
            )

            # Use whichever signal gives the higher confirmed-occupied count,
            # capped at p_units so occupied never exceeds total.
            p_occ = min(max(p_occ_from_units, confirmed_count), p_units)

            # Vacant = declared total minus what we know is occupied.
            # Includes both known-vacant Unit records AND declared-but-unseen
            # units (directory count > record count = real vacancy gap).
            p_vac = p_units - p_occ
            p_market = sum((u.market_rent for u in units), Decimal("0"))
            p_actual = sum(
                (
                    act.monthly_rent
                    for u in units
                    if (act := active_lease(leases_by_unit.get(u.id, []))) is not None
                ),
                Decimal("0"),
            )
            p_ltl = sum(
                (
                    loss_to_lease(
                        u.market_rent,
                        active_lease(leases_by_unit.get(u.id, [])).monthly_rent
                        if active_lease(leases_by_unit.get(u.id, []))
                        else Decimal("0"),
                    )
                    for u in units
                ),
                Decimal("0"),
            )
            p_vloss = sum(
                (
                    u.market_rent
                    for u in units
                    if not _is_unit_occupied(u, leases_by_unit.get(u.id, []))
                ),
                Decimal("0"),
            )
            p_open_maint = sum(1 for m in maint if is_maintenance_open(m))
            p_emergency = sum(
                1 for m in maint if is_maintenance_open(m) and m.priority.value == "emergency"
            )

            p_expiring = 0
            p_expired = 0
            for le in leases:
                if le.status == LeaseStatus.ACTIVE:
                    days_left = (le.end_date - today).days
                    if 0 < days_left <= 90:
                        p_expiring += 1
                elif le.status == LeaseStatus.EXPIRED:
                    p_expired += 1

            p_below = sum(
                1
                for u in units
                if is_below_market(
                    u.market_rent,
                    active_lease(leases_by_unit.get(u.id, [])).monthly_rent
                    if active_lease(leases_by_unit.get(u.id, []))
                    else Decimal("0"),
                )
            )

            total_units += p_units
            occupied += p_occ
            vacant += p_vac
            total_market += p_market
            total_actual += p_actual
            total_loss_to_lease_val += p_ltl
            total_vacancy_loss += p_vloss
            open_maintenance += p_open_maint
            emergency_maintenance += p_emergency
            expiring_leases_90d += p_expiring
            expired_leases += p_expired
            below_market_units += p_below

            issue_count = p_vac + p_open_maint + p_expiring + p_expired + p_below
            property_summaries.append(
                PropertySummary(
                    property_id=prop.id,
                    property_name=prop.name,
                    total_units=p_units,
                    occupied=p_occ,
                    vacant=p_vac,
                    occupancy_rate=round(p_occ / p_units, 3) if p_units else 0,
                    monthly_actual=float(p_actual),
                    monthly_market=float(p_market),
                    loss_to_lease=float(p_ltl),
                    vacancy_loss=float(p_vloss),
                    open_maintenance=p_open_maint,
                    emergency_maintenance=p_emergency,
                    expiring_leases=p_expiring,
                    expired_leases=p_expired,
                    below_market_units=p_below,
                    issue_count=issue_count,
                )
            )

            for u in units:
                unit_leases = leases_by_unit.get(u.id, [])
                act = active_lease(unit_leases)
                lease_rent = act.monthly_rent if act else Decimal("0")
                unit_issues: list[str] = []
                if not _is_unit_occupied(u, unit_leases):
                    unit_issues.append("vacant")
                if is_below_market(u.market_rent, lease_rent):
                    unit_issues.append("below_market")
                unit_active = next(
                    (le for le in unit_leases if le.status == LeaseStatus.ACTIVE), None
                )
                if unit_active and 0 < (unit_active.end_date - today).days <= 90:
                    unit_issues.append("expiring_soon")
                if any(le.status == LeaseStatus.EXPIRED for le in unit_leases):
                    unit_issues.append("expired_lease")
                unit_maint = [m for m in maint if m.unit_id == u.id and is_maintenance_open(m)]
                if unit_maint:
                    unit_issues.append("open_maintenance")
                if unit_issues:
                    top_issues.append(
                        UnitIssue(
                            property_id=prop.id,
                            property_name=prop.name,
                            unit_id=u.id,
                            unit_number=u.unit_number,
                            issues=unit_issues,
                            monthly_impact=float(u.market_rent - lease_rent)
                            if lease_rent < u.market_rent
                            else 0,
                        )
                    )

        property_summaries.sort(key=lambda p: p.issue_count, reverse=True)
        top_issues.sort(key=lambda i: len(i.issues), reverse=True)

        # Flatten per-property data already in memory — no extra I/O needed.
        pairs = zip(all_properties, prop_data, strict=True)
        all_mgr_units: list[Unit] = []
        all_mgr_leases: list[Lease] = []
        all_mgr_maint: list[MaintenanceRequest] = []
        all_mgr_obs: list[BalanceObservation] = []
        for _, (units, leases, maint, obs_list) in pairs:
            all_mgr_units.extend(units)
            all_mgr_leases.extend(leases)
            all_mgr_maint.extend(maint)
            all_mgr_obs.extend(obs_list)

        latest_obs = _latest_obs_by_tenant(all_mgr_obs)
        delinquent_count = 0
        delinquent_balance = Decimal("0")
        mgr_obs: list[object] = []
        for obs in latest_obs.values():
            mgr_obs.append(obs)
            if obs.balance_total > 0:  # type: ignore[union-attr]
                delinquent_count += 1
                delinquent_balance += obs.balance_total  # type: ignore[union-attr]

        coverage = _compute_coverage(
            all_units=all_mgr_units,
            all_leases=all_mgr_leases,
            all_maint=all_mgr_maint,
            obs_list=mgr_obs,
            declared_units=total_units,
        )

        metrics = ManagerMetrics(
            total_units=total_units,
            occupied=occupied,
            vacant=vacant,
            occupancy_rate=round(occupied / total_units, 3) if total_units else 0,
            total_actual_rent=float(total_actual),
            total_market_rent=float(total_market),
            loss_to_lease=float(total_loss_to_lease_val),
            vacancy_loss=float(total_vacancy_loss),
            open_maintenance=open_maintenance,
            expiring_leases_90d=expiring_leases_90d,
        )

        return ManagerSummary(
            manager_id=manager.id,
            name=manager.name,
            email=manager.email,
            company=manager.company,
            property_count=property_count,
            metrics=metrics,
            data_coverage=coverage,
            delinquent_count=delinquent_count,
            total_delinquent_balance=float(delinquent_balance),
            expired_leases=expired_leases,
            below_market_units=below_market_units,
            emergency_maintenance=emergency_maintenance,
            properties=property_summaries,
            top_issues=top_issues[:20],
        )

    async def list_manager_summaries(self) -> list[ManagerSummary]:
        managers = await self._ps.list_managers()
        summaries = await asyncio.gather(*[self.aggregate_manager(m.id) for m in managers])
        return [s for s in summaries if s is not None]

    async def rank_managers(
        self,
        sort_by: str = "delinquency_rate",
        ascending: bool = False,
        limit: int | None = None,
    ) -> list[ManagerRanking]:
        summaries = await self.list_manager_summaries()
        rows: list[ManagerRanking] = []
        for s in summaries:
            delinquency_rate = (
                round(s.delinquent_count / s.metrics.total_units, 4)
                if s.metrics.total_units
                else 0.0
            )
            rows.append(
                ManagerRanking(
                    manager_id=s.manager_id,
                    name=s.name,
                    property_count=s.property_count,
                    metrics=s.metrics,
                    delinquent_count=s.delinquent_count,
                    total_delinquent_balance=s.total_delinquent_balance,
                    delinquency_rate=delinquency_rate,
                )
            )

        ranking_keys = set(ManagerRanking.model_fields.keys())
        metrics_keys = set(ManagerMetrics.model_fields.keys())
        if sort_by in ranking_keys:
            rows.sort(key=lambda r: getattr(r, sort_by, 0), reverse=not ascending)
        elif sort_by in metrics_keys:
            rows.sort(key=lambda r: getattr(r.metrics, sort_by, 0), reverse=not ascending)
        else:
            rows.sort(key=lambda r: r.delinquency_rate, reverse=not ascending)

        if limit and limit > 0:
            rows = rows[:limit]
        return rows
