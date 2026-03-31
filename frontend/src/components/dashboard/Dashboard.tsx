"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { fmt$, pct } from "@/lib/format";
import { useApiQuery } from "@/hooks/useApiQuery";
import { MetricCard } from "@/components/ui/MetricCard";
import { MetricStrip } from "@/components/ui/MetricStrip";
import { PageContainer } from "@/components/ui/PageContainer";
import { Badge } from "@/components/ui/Badge";
import type {
  ManagerListItem,
  ManagerSnapshot,
  DelinquencyBoard,
  LeaseCalendar,
  VacancyTracker,
  NeedsManagerResponse,
} from "@/lib/types";

function TrendArrow({ prev, curr, invert }: { prev: number; curr: number; invert?: boolean }) {
  const diff = curr - prev;
  if (Math.abs(diff) < 0.001) return null;
  const positive = invert ? diff < 0 : diff > 0;
  return (
    <span className={`text-[8px] font-bold ml-0.5 ${positive ? "text-ok" : "text-error"}`}>
      {positive ? "▲" : "▼"}
    </span>
  );
}

function ManagerCard({
  m,
  prev,
  allManagers,
  onRefresh,
}: {
  m: ManagerListItem;
  prev?: ManagerSnapshot | null;
  allManagers: ManagerListItem[];
  onRefresh: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [mergeTarget, setMergeTarget] = useState("");
  const [busy, setBusy] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  const issueCount =
    m.vacant + m.open_maintenance + m.expiring_leases_90d + m.expired_leases + m.below_market_units + m.delinquent_count;
  const hasUrgent = m.emergency_maintenance > 0 || m.expired_leases > 0 || m.delinquent_count > 5;

  const handleDelete = async () => {
    if (!confirm(`Delete manager "${m.name}" and unlink their properties?`)) return;
    setBusy(true);
    try {
      await api.deleteManager(m.id);
      onRefresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setBusy(false);
      setMenuOpen(false);
    }
  };

  const handleMerge = async () => {
    if (!mergeTarget) return;
    setBusy(true);
    try {
      await api.mergeManagers(m.id, mergeTarget);
      onRefresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Merge failed");
    } finally {
      setBusy(false);
      setMergeOpen(false);
      setMenuOpen(false);
    }
  };

  return (
    <div
      className={`relative rounded-xl border p-4 transition-all ${
        hasUrgent
          ? "border-error/30 bg-error-soft"
          : issueCount > 0
          ? "border-warn/20 bg-warn-soft"
          : "border-border bg-surface"
      }`}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <Link href={`/managers/${m.id}`} className="min-w-0 flex-1 hover:opacity-80">
          <h3 className="text-sm font-semibold text-fg truncate">{m.name}</h3>
          <p className="text-[10px] text-fg-faint mt-0.5">
            {m.property_count} properties · {m.total_units} units
          </p>
        </Link>
        <div className="flex items-center gap-1.5">
          {issueCount > 0 ? (
            <Badge variant={hasUrgent ? "red" : "amber"}>{issueCount}</Badge>
          ) : (
            <Badge variant="emerald">OK</Badge>
          )}
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setMenuOpen((x) => !x)}
              className="text-fg-ghost hover:text-fg-muted px-1 py-0.5 rounded text-sm leading-none"
              title="Actions"
            >
              ···
            </button>
            {menuOpen && (
              <div className="absolute right-0 top-6 z-20 w-40 rounded-lg border border-border bg-surface-raised shadow-lg py-1 text-xs">
                <Link
                  href={`/managers/${m.id}`}
                  className="block px-3 py-1.5 text-fg-secondary hover:bg-surface-sunken"
                >
                  View / Edit
                </Link>
                <button
                  onClick={() => { setMergeOpen(true); setMenuOpen(false); }}
                  className="w-full text-left px-3 py-1.5 text-fg-secondary hover:bg-surface-sunken"
                >
                  Merge into...
                </button>
                <button
                  onClick={handleDelete}
                  disabled={busy}
                  className="w-full text-left px-3 py-1.5 text-error hover:bg-surface-sunken"
                >
                  {busy ? "Deleting..." : "Delete"}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Merge dialog */}
      {mergeOpen && (
        <div className="mb-3 rounded-lg border border-border bg-surface-raised p-3">
          <p className="text-xs text-fg-secondary mb-2">
            Merge &quot;{m.name}&quot; into another manager (properties will move, this PM will be deleted):
          </p>
          <select
            value={mergeTarget}
            onChange={(e) => setMergeTarget(e.target.value)}
            className="w-full bg-surface border border-border rounded px-2 py-1 text-xs text-fg mb-2"
          >
            <option value="">Select target manager...</option>
            {allManagers
              .filter((o) => o.id !== m.id)
              .map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name} ({o.property_count} props)
                </option>
              ))}
          </select>
          <div className="flex gap-2">
            <button
              onClick={handleMerge}
              disabled={!mergeTarget || busy}
              className="px-3 py-1 rounded bg-accent text-white text-xs font-medium disabled:opacity-50"
            >
              {busy ? "Merging..." : "Merge"}
            </button>
            <button
              onClick={() => setMergeOpen(false)}
              className="px-3 py-1 rounded border border-border text-xs text-fg-muted"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Metrics grid */}
      <Link href={`/managers/${m.id}`} className="block hover:opacity-90">
        <div className="grid grid-cols-3 sm:grid-cols-5 gap-1.5 text-center">
          <div className="rounded-lg bg-surface-sunken px-1.5 py-1.5 min-w-0">
            <p className="text-[9px] text-fg-faint uppercase truncate">Occ</p>
            <p className={`text-[11px] font-bold truncate ${m.occupancy_rate < 0.9 ? "text-warn" : "text-fg"}`}>
              {pct(m.occupancy_rate)}
              {prev && <TrendArrow prev={prev.occupancy_rate} curr={m.occupancy_rate} />}
            </p>
          </div>
          <div className="rounded-lg bg-surface-sunken px-1.5 py-1.5 min-w-0">
            <p className="text-[9px] text-fg-faint uppercase truncate">Revenue</p>
            <p className="text-[11px] font-bold text-fg truncate">
              {fmt$(m.total_actual_rent)}
              {prev && <TrendArrow prev={prev.total_rent} curr={m.total_actual_rent} />}
            </p>
          </div>
          <div className="rounded-lg bg-surface-sunken px-1.5 py-1.5 min-w-0">
            <p className="text-[9px] text-fg-faint uppercase truncate">LTL</p>
            <p className={`text-[11px] font-bold truncate ${m.total_loss_to_lease > 0 ? "text-warn" : "text-fg-muted"}`}>
              {m.total_loss_to_lease > 0 ? fmt$(m.total_loss_to_lease) : "—"}
              {prev && prev.loss_to_lease !== m.total_loss_to_lease && (
                <TrendArrow prev={prev.loss_to_lease} curr={m.total_loss_to_lease} invert />
              )}
            </p>
          </div>
          <div className="rounded-lg bg-surface-sunken px-1.5 py-1.5 min-w-0">
            <p className="text-[9px] text-fg-faint uppercase truncate">Delinq</p>
            <p className={`text-[11px] font-bold truncate ${m.delinquent_count > 0 ? "text-error" : "text-fg-muted"}`}>
              {m.delinquent_count > 0 ? m.delinquent_count : "—"}
              {prev && <TrendArrow prev={prev.delinquent_count} curr={m.delinquent_count} invert />}
            </p>
          </div>
          <div className="rounded-lg bg-surface-sunken px-1.5 py-1.5 min-w-0">
            <p className="text-[9px] text-fg-faint uppercase truncate">Vacant</p>
            <p className={`text-[11px] font-bold truncate ${m.vacant > 0 ? "text-error" : "text-fg-muted"}`}>
              {m.vacant > 0 ? m.vacant : "—"}
              {prev && <TrendArrow prev={prev.vacant} curr={m.vacant} invert />}
            </p>
          </div>
        </div>

        {/* Issue tags */}
        {issueCount > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2.5 pt-2.5 border-t border-border-subtle">
            {m.delinquent_count > 0 && <span className="text-[9px] text-error">{m.delinquent_count} delinquent ({fmt$(m.total_delinquent_balance)})</span>}
            {m.vacant > 0 && <span className="text-[9px] text-error">{m.vacant} vacant</span>}
            {m.expiring_leases_90d > 0 && <span className="text-[9px] text-warn">{m.expiring_leases_90d} expiring</span>}
            {m.expired_leases > 0 && <span className="text-[9px] text-error">{m.expired_leases} expired</span>}
            {m.below_market_units > 0 && <span className="text-[9px] text-warn">{m.below_market_units} below mkt</span>}
            {m.open_maintenance > 0 && <span className="text-[9px] text-sky-400">{m.open_maintenance} maint</span>}
          </div>
        )}
      </Link>
    </div>
  );
}

type SortKey = "issues" | "revenue" | "occupancy" | "units" | "name";

function sortManagers(mgrs: ManagerListItem[], key: SortKey): ManagerListItem[] {
  const copy = [...mgrs];
  switch (key) {
    case "issues":
      return copy.sort((a, b) => {
        const aI = a.vacant + a.open_maintenance + a.expiring_leases_90d + a.expired_leases + a.below_market_units;
        const bI = b.vacant + b.open_maintenance + b.expiring_leases_90d + b.expired_leases + b.below_market_units;
        return bI - aI;
      });
    case "revenue":
      return copy.sort((a, b) => b.total_actual_rent - a.total_actual_rent);
    case "occupancy":
      return copy.sort((a, b) => a.occupancy_rate - b.occupancy_rate);
    case "units":
      return copy.sort((a, b) => b.total_units - a.total_units);
    case "name":
      return copy.sort((a, b) => a.name.localeCompare(b.name));
  }
}

export function Dashboard() {
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("issues");

  const { data: dashboardData, loading, refetch } = useApiQuery(async () => {
    const [mgrs, del, lse, vac, nm, snaps] = await Promise.all([
      api.listManagers().catch(() => []),
      api.delinquencyBoard().catch(() => null),
      api.leasesExpiring(90).catch(() => null),
      api.vacancyTracker().catch(() => null),
      api.needsManager().catch(() => null),
      api.snapshots().catch(() => ({ total: 0, snapshots: [] })),
    ]);
    return {
      managers: mgrs as ManagerListItem[],
      delinquency: del as DelinquencyBoard | null,
      leases: lse as LeaseCalendar | null,
      vacancies: vac as VacancyTracker | null,
      needsMgr: nm as NeedsManagerResponse | null,
      snapshots: snaps.snapshots as ManagerSnapshot[],
    };
  }, []);

  const managers = dashboardData?.managers ?? [];
  const delinquency = dashboardData?.delinquency ?? null;
  const leases = dashboardData?.leases ?? null;
  const vacancies = dashboardData?.vacancies ?? null;
  const needsMgr = dashboardData?.needsMgr ?? null;
  const snapshots = dashboardData?.snapshots ?? [];

  // Filter out PMs with zero properties and apply search
  const activeMgrs = managers.filter((m) => m.total_units > 0 || m.property_count > 0);
  const filtered = search
    ? activeMgrs.filter((m) => m.name.toLowerCase().includes(search.toLowerCase()))
    : activeMgrs;
  const sorted = sortManagers(filtered, sortBy);

  // Build a map from manager_id → second-to-last snapshot (for trend arrows)
  const prevSnapshotMap = new Map<string, ManagerSnapshot>();
  const byMgr = new Map<string, ManagerSnapshot[]>();
  for (const s of snapshots) {
    const arr = byMgr.get(s.manager_id) || [];
    arr.push(s);
    byMgr.set(s.manager_id, arr);
  }
  for (const [mid, arr] of byMgr) {
    arr.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
    if (arr.length >= 2) {
      prevSnapshotMap.set(mid, arr[arr.length - 2]);
    }
  }

  const totalUnits = activeMgrs.reduce((s, m) => s + m.total_units, 0);
  const totalOccupied = activeMgrs.reduce((s, m) => s + m.occupied, 0);
  const totalRevenue = activeMgrs.reduce((s, m) => s + m.total_actual_rent, 0);
  const totalLTL = activeMgrs.reduce((s, m) => s + m.total_loss_to_lease, 0);
  const totalVacLoss = activeMgrs.reduce((s, m) => s + m.total_vacancy_loss, 0);
  const avgOcc = totalUnits > 0 ? totalOccupied / totalUnits : 0;

  return (
    <PageContainer wide>
        {/* Header */}
        <div>
          <h1 className="text-xl font-bold text-fg">Portfolio Overview</h1>
          <p className="text-xs text-fg-muted mt-1">
            {activeMgrs.length} active managers · {totalUnits.toLocaleString()} units
          </p>
        </div>

        {loading && (
          <div className="text-sm text-fg-faint animate-pulse">Loading...</div>
        )}

        {/* KPI strip */}
        <MetricStrip>
          <MetricCard label="Occupancy" value={pct(avgOcc)} trend={avgOcc >= 0.95 ? "up" : avgOcc >= 0.9 ? "flat" : "down"} />
          <MetricCard label="Monthly Revenue" value={fmt$(totalRevenue)} />
          <MetricCard label="Loss to Lease" value={fmt$(totalLTL)} alert={totalLTL > 0} />
          <MetricCard label="Vacancy Loss" value={fmt$(totalVacLoss)} alert={totalVacLoss > 0} />
          <MetricCard
            label="Units"
            value={totalOccupied.toLocaleString()}
            sub={`of ${totalUnits.toLocaleString()} (${(totalUnits - totalOccupied).toLocaleString()} vacant)`}
          />
        </MetricStrip>

        {/* Attention strip */}
        <div className="flex gap-3 overflow-x-auto pb-1">
          {delinquency && delinquency.total_delinquent > 0 && (
            <Link href="/delinquency" className="shrink-0 rounded-lg border border-error/20 bg-error-soft px-4 py-2.5 hover:border-error/40 transition-all">
              <span className="text-lg font-bold text-error">{delinquency.total_delinquent}</span>
              <span className="text-[10px] text-error/70 ml-1.5">delinquent</span>
              <p className="text-[9px] text-error/50">{fmt$(delinquency.total_balance)} owed</p>
            </Link>
          )}
          {leases && leases.total_expiring > 0 && (
            <Link href="/leases" className="shrink-0 rounded-lg border border-warn/20 bg-warn-soft px-4 py-2.5 hover:border-warn/40 transition-all">
              <span className="text-lg font-bold text-warn">{leases.total_expiring}</span>
              <span className="text-[10px] text-warn/70 ml-1.5">expiring (90d)</span>
              <p className="text-[9px] text-warn/50">{leases.month_to_month_count} MTM</p>
            </Link>
          )}
          {vacancies && vacancies.total_vacant > 0 && (
            <Link href="/vacancies" className="shrink-0 rounded-lg border border-orange-500/20 bg-orange-500/5 px-4 py-2.5 hover:border-orange-500/40 transition-all">
              <span className="text-lg font-bold text-orange-400">{vacancies.total_vacant}</span>
              <span className="text-[10px] text-orange-400/70 ml-1.5">vacant units</span>
              <p className="text-[9px] text-orange-400/50">{fmt$(vacancies.total_market_rent_at_risk)}/mo at risk</p>
            </Link>
          )}
          {needsMgr && needsMgr.total > 0 && (
            <Link href="/documents" className="shrink-0 rounded-lg border border-violet-500/20 bg-violet-500/5 px-4 py-2.5 hover:border-violet-500/40 transition-all">
              <span className="text-lg font-bold text-violet-400">{needsMgr.total}</span>
              <span className="text-[10px] text-violet-400/70 ml-1.5">need manager</span>
              <p className="text-[9px] text-violet-400/50">Upload with PM to assign</p>
            </Link>
          )}
        </div>

        {/* Manager section header with search + sort */}
        <div className="flex items-center gap-3">
          <h2 className="text-xs font-semibold text-fg-secondary uppercase tracking-wide shrink-0">
            Property Managers
          </h2>
          <div className="flex-1" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search managers..."
            className="bg-surface border border-border rounded-lg px-3 py-1.5 text-xs text-fg-secondary placeholder-fg-ghost focus:outline-none focus:border-fg-ghost w-48"
          />
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortKey)}
            className="bg-surface border border-border rounded-lg px-3 py-1.5 text-xs text-fg-secondary focus:outline-none focus:border-fg-ghost"
          >
            <option value="issues">Sort: Issues</option>
            <option value="revenue">Sort: Revenue</option>
            <option value="occupancy">Sort: Lowest Occ.</option>
            <option value="units">Sort: Most Units</option>
            <option value="name">Sort: Name</option>
          </select>
        </div>

        {/* Manager cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {sorted.map((m) => (
            <ManagerCard key={m.id} m={m} prev={prevSnapshotMap.get(m.id)} allManagers={activeMgrs} onRefresh={refetch} />
          ))}
        </div>

        {sorted.length === 0 && !loading && (
          <p className="text-sm text-fg-faint text-center py-12">
            {search ? "No managers match your search" : "No property managers found — upload reports to get started"}
          </p>
        )}
    </PageContainer>
  );
}
