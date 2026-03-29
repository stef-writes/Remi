"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { MetricCard } from "@/components/ui/MetricCard";
import { Badge } from "@/components/ui/Badge";
import type {
  ManagerListItem,
  ManagerSnapshot,
  DelinquencyBoard,
  LeaseCalendar,
  VacancyTracker,
  NeedsManagerResponse,
} from "@/lib/types";

function fmt$(n: number) {
  return "$" + n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function pct(n: number) {
  return (n * 100).toFixed(1) + "%";
}

function TrendArrow({ prev, curr, invert }: { prev: number; curr: number; invert?: boolean }) {
  const diff = curr - prev;
  if (Math.abs(diff) < 0.001) return null;
  const positive = invert ? diff < 0 : diff > 0;
  return (
    <span className={`text-[8px] font-bold ml-0.5 ${positive ? "text-emerald-400" : "text-red-400"}`}>
      {positive ? "▲" : "▼"}
    </span>
  );
}

function ManagerCard({ m, prev }: { m: ManagerListItem; prev?: ManagerSnapshot | null }) {
  const issueCount =
    m.vacant + m.open_maintenance + m.expiring_leases_90d + m.expired_leases + m.below_market_units;
  const hasUrgent = m.emergency_maintenance > 0 || m.expired_leases > 0;

  return (
    <Link
      href={`/managers/${m.id}`}
      className={`block rounded-xl border p-4 transition-all hover:border-zinc-600 ${
        hasUrgent
          ? "border-red-500/30 bg-red-500/5"
          : issueCount > 0
          ? "border-amber-500/20 bg-amber-500/5"
          : "border-zinc-800/60 bg-zinc-900/40"
      }`}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-zinc-200 truncate">{m.name}</h3>
          <p className="text-[10px] text-zinc-600 mt-0.5">
            {m.property_count} properties · {m.total_units} units
          </p>
        </div>
        {issueCount > 0 ? (
          <Badge variant={hasUrgent ? "red" : "amber"}>{issueCount}</Badge>
        ) : (
          <Badge variant="emerald">OK</Badge>
        )}
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-4 gap-2 text-center">
        <div className="rounded-lg bg-zinc-800/30 px-2 py-1.5">
          <p className="text-[9px] text-zinc-600 uppercase">Occ</p>
          <p className={`text-xs font-bold ${m.occupancy_rate < 0.9 ? "text-amber-400" : "text-zinc-200"}`}>
            {pct(m.occupancy_rate)}
            {prev && <TrendArrow prev={prev.occupancy_rate} curr={m.occupancy_rate} />}
          </p>
        </div>
        <div className="rounded-lg bg-zinc-800/30 px-2 py-1.5">
          <p className="text-[9px] text-zinc-600 uppercase">Revenue</p>
          <p className="text-xs font-bold text-zinc-200">
            {fmt$(m.total_actual_rent)}
            {prev && <TrendArrow prev={prev.total_rent} curr={m.total_actual_rent} />}
          </p>
        </div>
        <div className="rounded-lg bg-zinc-800/30 px-2 py-1.5">
          <p className="text-[9px] text-zinc-600 uppercase">LTL</p>
          <p className={`text-xs font-bold ${m.total_loss_to_lease > 0 ? "text-amber-400" : "text-zinc-500"}`}>
            {m.total_loss_to_lease > 0 ? fmt$(m.total_loss_to_lease) : "—"}
            {prev && prev.loss_to_lease !== m.total_loss_to_lease && (
              <TrendArrow prev={prev.loss_to_lease} curr={m.total_loss_to_lease} invert />
            )}
          </p>
        </div>
        <div className="rounded-lg bg-zinc-800/30 px-2 py-1.5">
          <p className="text-[9px] text-zinc-600 uppercase">Vacant</p>
          <p className={`text-xs font-bold ${m.vacant > 0 ? "text-red-400" : "text-zinc-500"}`}>
            {m.vacant > 0 ? m.vacant : "—"}
            {prev && <TrendArrow prev={prev.vacant} curr={m.vacant} invert />}
          </p>
        </div>
      </div>

      {/* Issue tags */}
      {issueCount > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2.5 pt-2.5 border-t border-zinc-800/30">
          {m.vacant > 0 && <span className="text-[9px] text-red-400">{m.vacant} vacant</span>}
          {m.expiring_leases_90d > 0 && <span className="text-[9px] text-yellow-400">{m.expiring_leases_90d} expiring</span>}
          {m.expired_leases > 0 && <span className="text-[9px] text-red-400">{m.expired_leases} expired</span>}
          {m.below_market_units > 0 && <span className="text-[9px] text-amber-400">{m.below_market_units} below mkt</span>}
          {m.open_maintenance > 0 && <span className="text-[9px] text-sky-400">{m.open_maintenance} maint</span>}
        </div>
      )}
    </Link>
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
  const [managers, setManagers] = useState<ManagerListItem[]>([]);
  const [delinquency, setDelinquency] = useState<DelinquencyBoard | null>(null);
  const [leases, setLeases] = useState<LeaseCalendar | null>(null);
  const [vacancies, setVacancies] = useState<VacancyTracker | null>(null);
  const [needsMgr, setNeedsMgr] = useState<NeedsManagerResponse | null>(null);
  const [snapshots, setSnapshots] = useState<ManagerSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("issues");

  const load = useCallback(async () => {
    try {
      const [mgrs, del, lse, vac, nm, snaps] = await Promise.all([
        api.listManagers().catch(() => []),
        api.delinquencyBoard().catch(() => null),
        api.leasesExpiring(90).catch(() => null),
        api.vacancyTracker().catch(() => null),
        api.needsManager().catch(() => null),
        api.snapshots().catch(() => ({ total: 0, snapshots: [] })),
      ]);
      setManagers(mgrs);
      setDelinquency(del);
      setLeases(lse);
      setVacancies(vac);
      setNeedsMgr(nm);
      setSnapshots(snaps.snapshots);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

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

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-sm text-zinc-600 animate-pulse">Loading...</div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-7xl mx-auto px-8 py-8 space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-xl font-bold text-zinc-100">Portfolio Overview</h1>
          <p className="text-xs text-zinc-500 mt-1">
            {activeMgrs.length} active managers · {totalUnits.toLocaleString()} units
          </p>
        </div>

        {/* KPI strip */}
        <div className="grid grid-cols-3 md:grid-cols-5 gap-3">
          <MetricCard label="Occupancy" value={pct(avgOcc)} trend={avgOcc >= 0.95 ? "up" : avgOcc >= 0.9 ? "flat" : "down"} />
          <MetricCard label="Monthly Revenue" value={fmt$(totalRevenue)} />
          <MetricCard label="Loss to Lease" value={fmt$(totalLTL)} alert={totalLTL > 0} />
          <MetricCard label="Vacancy Loss" value={fmt$(totalVacLoss)} alert={totalVacLoss > 0} />
          <MetricCard
            label="Units"
            value={totalOccupied.toLocaleString()}
            sub={`of ${totalUnits.toLocaleString()} (${(totalUnits - totalOccupied).toLocaleString()} vacant)`}
          />
        </div>

        {/* Attention strip */}
        <div className="flex gap-3 overflow-x-auto pb-1">
          {delinquency && delinquency.total_delinquent > 0 && (
            <Link href="/delinquency" className="shrink-0 rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-2.5 hover:border-red-500/40 transition-all">
              <span className="text-lg font-bold text-red-400">{delinquency.total_delinquent}</span>
              <span className="text-[10px] text-red-400/70 ml-1.5">delinquent</span>
              <p className="text-[9px] text-red-400/50">{fmt$(delinquency.total_balance)} owed</p>
            </Link>
          )}
          {leases && leases.total_expiring > 0 && (
            <Link href="/leases" className="shrink-0 rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-2.5 hover:border-amber-500/40 transition-all">
              <span className="text-lg font-bold text-amber-400">{leases.total_expiring}</span>
              <span className="text-[10px] text-amber-400/70 ml-1.5">expiring (90d)</span>
              <p className="text-[9px] text-amber-400/50">{leases.month_to_month_count} MTM</p>
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
          <h2 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide shrink-0">
            Property Managers
          </h2>
          <div className="flex-1" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search managers..."
            className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-1.5 text-xs text-zinc-300 placeholder-zinc-700 focus:outline-none focus:border-zinc-600 w-48"
          />
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortKey)}
            className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-zinc-600"
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
            <ManagerCard key={m.id} m={m} prev={prevSnapshotMap.get(m.id)} />
          ))}
        </div>

        {sorted.length === 0 && !loading && (
          <p className="text-sm text-zinc-600 text-center py-12">
            {search ? "No managers match your search" : "No property managers found — upload reports to get started"}
          </p>
        )}
      </div>
    </div>
  );
}
