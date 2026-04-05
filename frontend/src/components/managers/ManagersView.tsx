"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { fmt$, pct } from "@/lib/format";
import { useApiQuery } from "@/hooks/useApiQuery";
import { PageContainer } from "@/components/ui/PageContainer";
import { Badge } from "@/components/ui/Badge";
import type { ManagerListItem } from "@/lib/types";

function ManagerCard({
  m,
  allManagers,
  onRefresh,
}: {
  m: ManagerListItem;
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

      <Link href={`/managers/${m.id}`} className="block hover:opacity-90">
        <div className="grid grid-cols-3 sm:grid-cols-5 gap-1.5 text-center">
          <div className="rounded-lg bg-surface-sunken px-1.5 py-1.5 min-w-0">
            <p className="text-[9px] text-fg-faint uppercase truncate">Occ</p>
            <p className={`text-[11px] font-bold truncate ${m.occupancy_rate < 0.9 ? "text-warn" : "text-fg"}`}>
              {pct(m.occupancy_rate)}
            </p>
          </div>
          <div className="rounded-lg bg-surface-sunken px-1.5 py-1.5 min-w-0">
            <p className="text-[9px] text-fg-faint uppercase truncate">Revenue</p>
            <p className="text-[11px] font-bold text-fg truncate">
              {fmt$(m.total_actual_rent)}
            </p>
          </div>
          <div className="rounded-lg bg-surface-sunken px-1.5 py-1.5 min-w-0">
            <p className="text-[9px] text-fg-faint uppercase truncate">LTL</p>
            <p className={`text-[11px] font-bold truncate ${m.total_loss_to_lease > 0 ? "text-warn" : "text-fg-muted"}`}>
              {m.total_loss_to_lease > 0 ? fmt$(m.total_loss_to_lease) : "—"}
            </p>
          </div>
          <div className="rounded-lg bg-surface-sunken px-1.5 py-1.5 min-w-0">
            <p className="text-[9px] text-fg-faint uppercase truncate">Delinq</p>
            <p className={`text-[11px] font-bold truncate ${m.delinquent_count > 0 ? "text-error" : "text-fg-muted"}`}>
              {m.delinquent_count > 0 ? m.delinquent_count : "—"}
            </p>
          </div>
          <div className="rounded-lg bg-surface-sunken px-1.5 py-1.5 min-w-0">
            <p className="text-[9px] text-fg-faint uppercase truncate">Vacant</p>
            <p className={`text-[11px] font-bold truncate ${m.vacant > 0 ? "text-error" : "text-fg-muted"}`}>
              {m.vacant > 0 ? m.vacant : "—"}
            </p>
          </div>
        </div>

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

export function ManagersView() {
  const [sortBy, setSortBy] = useState<SortKey>("issues");
  const [search, setSearch] = useState("");

  const { data: managers, loading, refetch } = useApiQuery(
    () => api.listManagers().catch(() => [] as ManagerListItem[]),
    [],
  );

  const activeMgrs = (managers ?? []).filter((m) => m.total_units > 0 || m.property_count > 0);
  const filtered = search
    ? activeMgrs.filter((m) => m.name.toLowerCase().includes(search.toLowerCase()))
    : activeMgrs;
  const sorted = sortManagers(filtered, sortBy);

  return (
    <PageContainer wide>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-fg tracking-tight">Property Managers</h1>
          <p className="text-[11px] text-fg-faint mt-0.5">
            {activeMgrs.length} managers · Select one to review their portfolio
          </p>
        </div>
        <div className="flex items-center gap-2">
          {activeMgrs.length > 3 && (
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter managers..."
              className="bg-surface border border-border rounded-lg px-3 py-1.5 text-xs text-fg-secondary placeholder-fg-ghost focus:outline-none focus:border-fg-ghost w-44"
            />
          )}
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
      </div>

      {loading && (
        <div className="text-sm text-fg-faint animate-pulse py-12 text-center">Loading...</div>
      )}

      {!loading && sorted.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {sorted.map((m) => (
            <ManagerCard key={m.id} m={m} allManagers={activeMgrs} onRefresh={refetch} />
          ))}
        </div>
      )}

      {!loading && sorted.length === 0 && activeMgrs.length > 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <p className="text-sm text-fg-faint">No managers match &quot;{search}&quot;</p>
        </div>
      )}

      {!loading && activeMgrs.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <p className="text-sm text-fg-faint">No managers yet</p>
          <Link
            href="/documents"
            className="mt-3 text-xs text-accent hover:text-accent-hover transition-colors"
          >
            Upload reports to get started →
          </Link>
        </div>
      )}
    </PageContainer>
  );
}
