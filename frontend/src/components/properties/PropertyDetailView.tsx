"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { fmt$, fmtDate } from "@/lib/format";
import { useApiQuery } from "@/hooks/useApiQuery";
import { MetricCard } from "@/components/ui/MetricCard";
import { MetricStrip } from "@/components/ui/MetricStrip";
import { PageContainer } from "@/components/ui/PageContainer";
import { Badge } from "@/components/ui/Badge";
import { SlidePanel } from "@/components/ui/SlidePanel";
import type {
  PropertyDetail,
  RentRollResponse,
  RentRollRow,
  UnitIssue,
  LeaseListItem,
  MaintenanceSummary,
  ChangeSetSummary,
  EntityNoteResponse,
} from "@/lib/types";

type Tab = "rent_roll" | "leases" | "maintenance" | "activity" | "notes";
type ViewMode = "grid" | "table";

const TABS: { key: Tab; label: string; icon: string }[] = [
  { key: "rent_roll", label: "Rent Roll", icon: "M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" },
  { key: "leases", label: "Leases", icon: "M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" },
  { key: "maintenance", label: "Maintenance", icon: "M11.42 15.17l-4.655 5.653a2.548 2.548 0 11-3.586-3.586l5.653-4.655a.685.685 0 00-.17-.896l-2.21-1.59a.676.676 0 01.16-1.18l6.096-2.198a.5.5 0 01.618.618L11.3 13.5a.676.676 0 01-1.18.16l-1.59-2.21a.685.685 0 00-.896-.17z" },
  { key: "activity", label: "Activity", icon: "M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" },
  { key: "notes", label: "Notes", icon: "M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.076-4.076a1.526 1.526 0 011.037-.443 48.282 48.282 0 005.68-.494c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" },
];

const ISSUE_LABELS: Record<UnitIssue, { label: string; color: string; gridColor: string }> = {
  vacant: { label: "Vacant", color: "bg-error-soft text-error-fg border-error/30", gridColor: "border-error/40 bg-error-soft/50" },
  down_for_maintenance: { label: "Down", color: "bg-orange-500/20 text-orange-300 border-orange-500/30", gridColor: "border-orange-500/30 bg-orange-500/10" },
  below_market: { label: "Below Market", color: "bg-warn-soft text-warn-fg border-warn/30", gridColor: "border-warn/30 bg-warn-soft/50" },
  expired_lease: { label: "Expired Lease", color: "bg-error-soft text-error-fg border-error/30", gridColor: "border-error/40 bg-error-soft/50" },
  expiring_soon: { label: "Expiring", color: "bg-warn-soft text-warn-fg border-warn/30", gridColor: "border-warn/30 bg-warn-soft/50" },
  open_maintenance: { label: "Maint.", color: "bg-sky-500/20 text-sky-300 border-sky-500/30", gridColor: "border-sky-500/30 bg-sky-500/5" },
};

type IssueFilter = UnitIssue | "all";

function IssuePill({ issue }: { issue: UnitIssue }) {
  const cfg = ISSUE_LABELS[issue];
  return (
    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${cfg.color}`}>
      {cfg.label}
    </span>
  );
}

/* ---- Unit Grid Card ---- */

function UnitGridCard({ row, propertyId, onPeek }: { row: RentRollRow; propertyId: string; onPeek: (row: RentRollRow) => void }) {
  const hasIssues = row.issues.length > 0;
  const worstIssue = row.issues[0];
  const gridAccent = worstIssue ? ISSUE_LABELS[worstIssue].gridColor : "border-border bg-surface";

  return (
    <div
      onClick={() => onPeek(row)}
      className={`rounded-xl border-2 p-3 cursor-pointer card-hover group transition-all ${gridAccent} ${
        !hasIssues ? "hover:border-accent/30" : ""
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="font-mono text-sm font-bold text-fg">{row.unit_number}</span>
        <Badge
          variant={
            row.status === "occupied" ? "emerald" :
            row.status === "vacant" ? "red" :
            row.status === "maintenance" ? "amber" : "default"
          }
        >
          {row.status}
        </Badge>
      </div>

      {row.tenant ? (
        <p className="text-xs text-fg-secondary truncate">{row.tenant.name}</p>
      ) : (
        <p className="text-xs text-fg-ghost italic">Vacant</p>
      )}

      <div className="flex items-baseline justify-between mt-2">
        <span className="font-mono text-xs text-fg-secondary">{fmt$(row.current_rent)}</span>
        {row.pct_below_market > 0 && (
          <span className="text-[10px] text-warn font-medium">-{row.pct_below_market}%</span>
        )}
      </div>

      {hasIssues && (
        <div className="flex flex-wrap gap-1 mt-2">
          {row.issues.slice(0, 2).map((issue) => (
            <IssuePill key={issue} issue={issue} />
          ))}
          {row.issues.length > 2 && (
            <span className="text-[10px] text-fg-muted">+{row.issues.length - 2}</span>
          )}
        </div>
      )}

      <Link
        href={`/properties/${propertyId}/units/${row.unit_id}`}
        onClick={(e) => e.stopPropagation()}
        className="block mt-2 text-[10px] text-fg-ghost group-hover:text-accent transition-colors"
      >
        Open →
      </Link>
    </div>
  );
}

/* ---- Unit Peek Drawer Content ---- */

function UnitPeek({ row, propertyId }: { row: RentRollRow; propertyId: string }) {
  return (
    <div className="space-y-5 anim-fade-up">
      {/* Unit identity */}
      <div className="flex items-center gap-3">
        <div className="w-11 h-11 rounded-xl bg-surface-sunken border border-border flex items-center justify-center">
          <span className="text-base font-bold text-fg font-mono">{row.unit_number}</span>
        </div>
        <div>
          <Badge
            variant={row.status === "occupied" ? "emerald" : row.status === "vacant" ? "red" : row.status === "maintenance" ? "amber" : "default"}
          >
            {row.status}
          </Badge>
        </div>
      </div>

      {/* Financials */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-lg bg-surface-sunken p-3">
          <p className="text-[10px] text-fg-muted uppercase tracking-wide">Rent</p>
          <p className="text-sm font-bold font-mono text-fg mt-0.5">{fmt$(row.current_rent)}</p>
        </div>
        <div className="rounded-lg bg-surface-sunken p-3">
          <p className="text-[10px] text-fg-muted uppercase tracking-wide">Market</p>
          <p className="text-sm font-bold font-mono text-fg mt-0.5">{fmt$(row.market_rent)}</p>
        </div>
        <div className={`rounded-lg p-3 ${row.rent_gap < 0 ? "bg-warn-soft" : "bg-ok-soft"}`}>
          <p className="text-[10px] text-fg-muted uppercase tracking-wide">Gap</p>
          <p className={`text-sm font-bold font-mono mt-0.5 ${row.rent_gap < 0 ? "text-warn-fg" : "text-ok-fg"}`}>
            {fmt$(row.rent_gap)}
          </p>
        </div>
      </div>

      {/* Physical */}
      <div className="flex gap-4 text-xs text-fg-muted">
        {row.bedrooms != null && <span>{row.bedrooms} bed / {row.bathrooms ?? "—"} bath</span>}
        {row.sqft != null && <span>{row.sqft.toLocaleString()} sq ft</span>}
        {row.floor != null && <span>Floor {row.floor}</span>}
      </div>

      {/* Issues */}
      {row.issues.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {row.issues.map((issue) => <IssuePill key={issue} issue={issue} />)}
        </div>
      )}

      {/* Tenant + Lease */}
      <div className="rounded-xl border border-border p-4">
        <h4 className="text-[10px] font-semibold text-fg-muted uppercase tracking-wide mb-2">Lease &amp; Tenant</h4>
        {row.lease && row.tenant ? (
          <div className="space-y-2 text-sm">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-full bg-accent/20 flex items-center justify-center">
                <span className="text-accent font-bold text-[10px]">{row.tenant.name.charAt(0)}</span>
              </div>
              <div>
                <p className="text-fg font-medium text-xs">{row.tenant.name}</p>
                <p className="text-[10px] text-fg-muted">{row.tenant.email}</p>
              </div>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <Badge variant={row.lease.status === "active" ? "emerald" : "red"}>{row.lease.status}</Badge>
              <span className="text-fg-muted">{row.lease.start_date} → {row.lease.end_date}</span>
            </div>
            {row.lease.days_to_expiry != null && (
              <p className={`text-xs ${row.lease.days_to_expiry <= 30 ? "text-error font-medium" : row.lease.days_to_expiry <= 90 ? "text-warn" : "text-fg-muted"}`}>
                {row.lease.days_to_expiry > 0 ? `${row.lease.days_to_expiry} days until expiry` : `Expired ${Math.abs(row.lease.days_to_expiry)} days ago`}
              </p>
            )}
          </div>
        ) : (
          <p className="text-xs text-fg-faint">No active lease</p>
        )}
      </div>

      {/* Maintenance */}
      {row.maintenance_items.length > 0 && (
        <div className="rounded-xl border border-border p-4">
          <h4 className="text-[10px] font-semibold text-fg-muted uppercase tracking-wide mb-2">
            Open Maintenance ({row.maintenance_items.length})
          </h4>
          <div className="space-y-2">
            {row.maintenance_items.map((mr) => (
              <div key={mr.id} className="flex items-center gap-2">
                <Badge variant={mr.priority === "emergency" ? "red" : mr.priority === "high" ? "amber" : "default"}>
                  {mr.priority}
                </Badge>
                <span className="text-xs text-fg-secondary truncate">{mr.title}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <Link
        href={`/properties/${propertyId}/units/${row.unit_id}`}
        className="block w-full text-center rounded-xl bg-accent text-accent-fg py-2.5 text-sm font-medium hover:bg-accent-hover transition-colors"
      >
        Open Full Unit Detail
      </Link>
    </div>
  );
}

/* ---- View Mode Toggle ---- */

function ViewToggle({ mode, onChange }: { mode: ViewMode; onChange: (m: ViewMode) => void }) {
  return (
    <div className="flex rounded-lg border border-border overflow-hidden">
      <button
        onClick={() => onChange("grid")}
        className={`px-2.5 py-1.5 transition-colors ${mode === "grid" ? "bg-accent text-accent-fg" : "text-fg-muted hover:text-fg-secondary"}`}
        title="Grid view"
      >
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
        </svg>
      </button>
      <button
        onClick={() => onChange("table")}
        className={`px-2.5 py-1.5 transition-colors ${mode === "table" ? "bg-accent text-accent-fg" : "text-fg-muted hover:text-fg-secondary"}`}
        title="Table view"
      >
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 12h16.5m-16.5 3.75h16.5M3.75 19.5h16.5M5.625 4.5h12.75a1.875 1.875 0 010 3.75H5.625a1.875 1.875 0 010-3.75z" />
        </svg>
      </button>
    </div>
  );
}

/* ---- Rent Roll (grid + table) ---- */

function RentRollTab({ rentRoll, propertyId }: { rentRoll: RentRollResponse; propertyId: string }) {
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [issueFilter, setIssueFilter] = useState<IssueFilter>("all");
  const [peekRow, setPeekRow] = useState<RentRollRow | null>(null);
  const [expandedUnit, setExpandedUnit] = useState<string | null>(null);

  const filteredRows = issueFilter === "all"
    ? rentRoll.rows
    : rentRoll.rows.filter((r) => r.issues.includes(issueFilter));

  const issueCounts: Record<UnitIssue, number> = {
    vacant: 0, down_for_maintenance: 0, below_market: 0,
    expired_lease: 0, expiring_soon: 0, open_maintenance: 0,
  };
  for (const row of rentRoll.rows) {
    for (const issue of row.issues) issueCounts[issue]++;
  }
  const unitsWithIssues = rentRoll.rows.filter((r) => r.issues.length > 0).length;

  return (
    <>
      <section className="rounded-2xl border border-border bg-surface overflow-hidden anim-fade-up">
        <div className="px-4 sm:px-5 py-3.5 border-b border-border-subtle space-y-2">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold text-fg-secondary uppercase tracking-wide">
              Rent Roll{" "}
              <span className="text-fg-faint font-normal">
                · {filteredRows.length} of {rentRoll.rows.length} units
                {unitsWithIssues > 0 && ` · ${unitsWithIssues} with issues`}
              </span>
            </h2>
            <ViewToggle mode={viewMode} onChange={setViewMode} />
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            <button
              onClick={() => setIssueFilter("all")}
              className={`text-[10px] px-2 py-1 rounded-md border transition-colors ${
                issueFilter === "all" ? "bg-accent border-accent text-accent-fg" : "border-border text-fg-muted hover:text-fg-secondary"
              }`}
            >
              All
            </button>
            {(Object.entries(issueCounts) as [UnitIssue, number][])
              .filter(([, count]) => count > 0)
              .map(([issue, count]) => (
                <button
                  key={issue}
                  onClick={() => setIssueFilter(issue === issueFilter ? "all" : issue)}
                  className={`text-[10px] px-2 py-1 rounded-md border transition-colors ${
                    issueFilter === issue ? ISSUE_LABELS[issue].color : "border-border text-fg-muted hover:text-fg-secondary"
                  }`}
                >
                  {ISSUE_LABELS[issue].label} ({count})
                </button>
              ))}
          </div>
        </div>

        {viewMode === "grid" ? (
          <div className="p-4">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-3 stagger">
              {filteredRows.map((row) => (
                <UnitGridCard key={row.unit_id} row={row} propertyId={propertyId} onPeek={setPeekRow} />
              ))}
            </div>
            {filteredRows.length === 0 && (
              <p className="text-center py-12 text-sm text-fg-faint">No units match the selected filter</p>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  {["Unit", "Status", "Tenant", "Rent", "Market", "Gap", "Lease End", "Maint", "Issues"].map((h) => (
                    <th key={h} className="text-left px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => (
                  <UnitTableRow key={row.unit_id} row={row} propertyId={propertyId} expanded={expandedUnit === row.unit_id} onToggle={() => setExpandedUnit(expandedUnit === row.unit_id ? null : row.unit_id)} />
                ))}
                {filteredRows.length === 0 && (
                  <tr><td colSpan={9} className="text-center py-12 text-sm text-fg-faint">No units match the selected filter</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <SlidePanel open={!!peekRow} onClose={() => setPeekRow(null)} title={peekRow ? `Unit ${peekRow.unit_number}` : ""} width="md">
        {peekRow && <UnitPeek row={peekRow} propertyId={propertyId} />}
      </SlidePanel>
    </>
  );
}

function UnitTableRow({ row, propertyId, expanded, onToggle }: { row: RentRollRow; propertyId: string; expanded: boolean; onToggle: () => void }) {
  const hasIssues = row.issues.length > 0;
  return (
    <>
      <tr onClick={onToggle} className={`border-b border-border-subtle cursor-pointer transition-colors ${hasIssues ? "bg-surface-raised hover:bg-surface-raised" : "hover:bg-surface-raised"}`}>
        <td className="px-4 py-2.5">
          <Link href={`/properties/${propertyId}/units/${row.unit_id}`} onClick={(e) => e.stopPropagation()} className="font-mono text-fg text-sm hover:text-accent transition-colors">{row.unit_number}</Link>
        </td>
        <td className="px-4 py-2.5"><Badge variant={row.status === "occupied" ? "emerald" : row.status === "vacant" ? "red" : row.status === "maintenance" ? "amber" : "default"}>{row.status}</Badge></td>
        <td className="px-4 py-2.5 text-sm text-fg-secondary">{row.tenant?.name ?? <span className="text-fg-faint">—</span>}</td>
        <td className="px-4 py-2.5 font-mono text-sm text-fg-secondary">{fmt$(row.current_rent)}</td>
        <td className="px-4 py-2.5 font-mono text-sm text-fg-muted">{fmt$(row.market_rent)}</td>
        <td className="px-4 py-2.5 text-sm">{row.pct_below_market > 0 ? <span className="text-warn font-medium">-{row.pct_below_market}%</span> : <span className="text-fg-faint">—</span>}</td>
        <td className="px-4 py-2.5 text-sm">{row.lease ? <span className={(row.lease.days_to_expiry ?? 999) <= 0 ? "text-error" : (row.lease.days_to_expiry ?? 999) <= 90 ? "text-warn" : "text-fg-secondary"}>{row.lease.end_date}</span> : <span className="text-fg-faint">—</span>}</td>
        <td className="px-4 py-2.5 text-sm text-center">{row.open_maintenance > 0 ? <span className="text-sky-400 font-medium">{row.open_maintenance}</span> : <span className="text-fg-ghost">0</span>}</td>
        <td className="px-4 py-2.5"><div className="flex flex-wrap gap-1">{row.issues.map((issue) => <IssuePill key={issue} issue={issue} />)}</div></td>
      </tr>
      {expanded && (
        <tr className="border-b border-border-subtle">
          <td colSpan={9} className="px-6 py-4 bg-surface-raised anim-expand">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-sm">
              <div className="space-y-2">
                <h4 className="text-xs font-semibold text-fg-muted uppercase tracking-wide">Unit</h4>
                <div className="space-y-1 text-fg-secondary">
                  {row.bedrooms != null && <p>{row.bedrooms} bed / {row.bathrooms ?? "—"} bath</p>}
                  {row.sqft != null && <p>{row.sqft.toLocaleString()} sq ft</p>}
                  {row.floor != null && <p>Floor {row.floor}</p>}
                  <p>Rent gap: <span className={row.rent_gap < 0 ? "text-warn font-medium" : "text-ok"}>{fmt$(row.rent_gap)}/mo</span></p>
                </div>
              </div>
              <div className="space-y-2">
                <h4 className="text-xs font-semibold text-fg-muted uppercase tracking-wide">Lease &amp; Tenant</h4>
                {row.lease && row.tenant ? (
                  <div className="space-y-1 text-fg-secondary">
                    <p className="text-fg font-medium">{row.tenant.name}</p>
                    <p className="text-fg-muted">{row.tenant.email}</p>
                    <p>Lease {row.lease.start_date} → {row.lease.end_date} <Badge variant={row.lease.status === "active" ? "emerald" : "red"} className="ml-2">{row.lease.status}</Badge></p>
                    <p>Deposit: {fmt$(row.lease.deposit)}</p>
                    {row.lease.days_to_expiry != null && (
                      <p className={row.lease.days_to_expiry <= 30 ? "text-error font-medium" : ""}>{row.lease.days_to_expiry > 0 ? `${row.lease.days_to_expiry} days until expiry` : `Expired ${Math.abs(row.lease.days_to_expiry)} days ago`}</p>
                    )}
                  </div>
                ) : <p className="text-fg-faint">No active lease</p>}
              </div>
              <div className="space-y-2">
                <h4 className="text-xs font-semibold text-fg-muted uppercase tracking-wide">Open Maintenance ({row.maintenance_items.length})</h4>
                {row.maintenance_items.length > 0 ? (
                  <div className="space-y-2">
                    {row.maintenance_items.map((mr) => (
                      <div key={mr.id} className="rounded-lg bg-surface border border-border-subtle px-3 py-2">
                        <div className="flex items-center gap-2">
                          <Badge variant={mr.priority === "emergency" ? "red" : mr.priority === "high" ? "amber" : "default"}>{mr.priority}</Badge>
                          <span className="text-fg-secondary text-sm">{mr.title}</span>
                        </div>
                        <p className="text-xs text-fg-muted mt-1">{mr.category} · {mr.status}{mr.cost != null && ` · est. ${fmt$(mr.cost)}`}</p>
                      </div>
                    ))}
                  </div>
                ) : <p className="text-fg-faint">None</p>}
              </div>
            </div>
            <div className="mt-3 pt-3 border-t border-border-subtle">
              <Link href={`/properties/${propertyId}/units/${row.unit_id}`} className="text-xs text-accent hover:underline">View full unit detail →</Link>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

/* ---- Other Tabs (leases, maintenance, activity, notes) ---- */

function LeasesTab({ propertyId }: { propertyId: string }) {
  const { data, loading } = useApiQuery(() => api.listLeases({ property_id: propertyId }), [propertyId]);
  if (loading) return <div className="py-12 text-center text-sm text-fg-faint animate-pulse">Loading leases...</div>;
  if (!data || data.leases.length === 0) return <div className="py-12 text-center text-sm text-fg-faint">No leases found</div>;
  const active = data.leases.filter((l) => l.status === "active");
  const other = data.leases.filter((l) => l.status !== "active");
  return (
    <section className="rounded-2xl border border-border bg-surface overflow-hidden anim-fade-up">
      <div className="px-5 py-3.5 border-b border-border-subtle">
        <h2 className="text-xs font-semibold text-fg-secondary uppercase tracking-wide">All Leases <span className="text-fg-faint font-normal">· {data.count} total · {active.length} active</span></h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-border">{["Tenant", "Unit", "Status", "Rent", "Start", "End"].map((h) => <th key={h} className="text-left px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">{h}</th>)}</tr></thead>
          <tbody>{[...active, ...other].map((l) => <LeaseRow key={l.id} lease={l} propertyId={propertyId} />)}</tbody>
        </table>
      </div>
    </section>
  );
}

function LeaseRow({ lease, propertyId }: { lease: LeaseListItem; propertyId: string }) {
  return (
    <tr className="border-b border-border-subtle hover:bg-surface-raised transition-colors">
      <td className="px-4 py-2.5 text-sm text-fg">{lease.tenant}</td>
      <td className="px-4 py-2.5"><Link href={`/properties/${propertyId}/units/${lease.unit_id}`} className="font-mono text-sm text-fg-secondary hover:text-accent transition-colors">{lease.unit_id.slice(-6)}</Link></td>
      <td className="px-4 py-2.5"><Badge variant={lease.status === "active" ? "emerald" : lease.status === "expired" ? "red" : "default"}>{lease.status}</Badge></td>
      <td className="px-4 py-2.5 font-mono text-sm text-fg-secondary">{fmt$(lease.rent)}</td>
      <td className="px-4 py-2.5 text-sm text-fg-muted">{fmtDate(lease.start)}</td>
      <td className="px-4 py-2.5 text-sm text-fg-muted">{fmtDate(lease.end)}</td>
    </tr>
  );
}

function MaintenanceTab({ propertyId }: { propertyId: string }) {
  const { data: list, loading: listLoading } = useApiQuery(() => api.listMaintenance({ property_id: propertyId }), [propertyId]);
  const { data: summary, loading: sumLoading } = useApiQuery(() => api.maintenanceSummary(propertyId), [propertyId]);
  if (listLoading || sumLoading) return <div className="py-12 text-center text-sm text-fg-faint animate-pulse">Loading maintenance...</div>;

  const openCount = (summary?.by_status["open"] ?? 0) + (summary?.by_status["in_progress"] ?? 0);
  const completedCount = summary?.by_status["completed"] ?? 0;

  return (
    <div className="space-y-4 anim-fade-up">
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 stagger">
          <MetricCard label="Total" value={summary.total} />
          <MetricCard label="Open" value={openCount} alert={openCount > 0} />
          <MetricCard label="Completed" value={completedCount} />
          <MetricCard label="Total Cost" value={fmt$(summary.total_cost)} />
        </div>
      )}
      <section className="rounded-2xl border border-border bg-surface overflow-hidden">
        <div className="px-5 py-3.5 border-b border-border-subtle">
          <h2 className="text-xs font-semibold text-fg-secondary uppercase tracking-wide">Work Orders <span className="text-fg-faint font-normal">· {list?.count ?? 0}</span></h2>
        </div>
        {list && list.requests.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-border">{["Title", "Unit", "Category", "Priority", "Status", "Cost", "Created"].map((h) => <th key={h} className="text-left px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">{h}</th>)}</tr></thead>
              <tbody>
                {list.requests.map((mr) => (
                  <tr key={mr.id} className="border-b border-border-subtle hover:bg-surface-raised transition-colors">
                    <td className="px-4 py-2.5 text-sm text-fg">{mr.title}</td>
                    <td className="px-4 py-2.5"><Link href={`/properties/${propertyId}/units/${mr.unit_id}`} className="font-mono text-sm text-fg-secondary hover:text-accent transition-colors">{mr.unit_id.slice(-6)}</Link></td>
                    <td className="px-4 py-2.5 text-sm text-fg-muted">{mr.category}</td>
                    <td className="px-4 py-2.5"><Badge variant={mr.priority === "emergency" ? "red" : mr.priority === "high" ? "amber" : "default"}>{mr.priority}</Badge></td>
                    <td className="px-4 py-2.5"><Badge variant={mr.status === "open" ? "amber" : mr.status === "completed" ? "emerald" : "default"}>{mr.status}</Badge></td>
                    <td className="px-4 py-2.5 font-mono text-sm text-fg-muted">{mr.cost != null ? fmt$(mr.cost) : "—"}</td>
                    <td className="px-4 py-2.5 text-sm text-fg-muted">{fmtDate(mr.created)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div className="py-12 text-center text-sm text-fg-faint">No maintenance requests</div>}
      </section>
    </div>
  );
}

function ActivityTab({ propertyId }: { propertyId: string }) {
  const { data, loading } = useApiQuery(() => api.entityEvents(propertyId, 50), [propertyId]);
  if (loading) return <div className="py-12 text-center text-sm text-fg-faint animate-pulse">Loading activity...</div>;
  if (!data || data.changesets.length === 0) return <div className="py-12 text-center text-sm text-fg-faint">No activity recorded yet</div>;
  return (
    <section className="rounded-2xl border border-border bg-surface overflow-hidden anim-fade-up">
      <div className="px-5 py-3.5 border-b border-border-subtle">
        <h2 className="text-xs font-semibold text-fg-secondary uppercase tracking-wide">Activity Timeline <span className="text-fg-faint font-normal">· {data.changesets.length} events</span></h2>
      </div>
      <div className="divide-y divide-border-subtle">
        {data.changesets.map((cs) => (
          <div key={cs.changeset_id} className="px-5 py-3.5 flex items-start gap-4 group hover:bg-surface-raised/50 transition-colors">
            <div className="shrink-0 w-2 h-2 rounded-full bg-accent mt-1.5 group-hover:scale-150 transition-transform" />
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline gap-2">
                <span className="text-sm text-fg font-medium">{cs.source}</span>
                {cs.report_type && <Badge variant="default">{cs.report_type}</Badge>}
                <span className="text-xs text-fg-faint ml-auto shrink-0">{fmtDate(cs.timestamp)}</span>
              </div>
              <div className="flex gap-3 mt-1 text-xs text-fg-muted">
                {cs.created > 0 && <span className="text-ok">+{cs.created} created</span>}
                {cs.updated > 0 && <span className="text-warn">{cs.updated} updated</span>}
                {cs.removed > 0 && <span className="text-error">{cs.removed} removed</span>}
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function NotesTab({ entityType, entityId }: { entityType: string; entityId: string }) {
  const { data, loading, refetch } = useApiQuery(() => api.listEntityNotes(entityType, entityId), [entityType, entityId]);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleAdd() {
    if (!draft.trim()) return;
    setSaving(true);
    try { await api.createEntityNote(entityType, entityId, draft.trim()); setDraft(""); refetch(); } finally { setSaving(false); }
  }
  async function handleDelete(noteId: string) { await api.deleteEntityNote(noteId); refetch(); }

  if (loading) return <div className="py-12 text-center text-sm text-fg-faint animate-pulse">Loading notes...</div>;
  const notes = data?.notes ?? [];

  return (
    <section className="rounded-2xl border border-border bg-surface overflow-hidden anim-fade-up">
      <div className="px-5 py-3.5 border-b border-border-subtle">
        <h2 className="text-xs font-semibold text-fg-secondary uppercase tracking-wide">Notes <span className="text-fg-faint font-normal">· {notes.length}</span></h2>
      </div>
      <div className="p-4 border-b border-border-subtle">
        <div className="flex gap-2">
          <input value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleAdd()} placeholder="Add a note..." className="flex-1 bg-surface-sunken border border-border rounded-xl px-3.5 py-2.5 text-sm text-fg placeholder:text-fg-ghost focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent transition-all" />
          <button onClick={handleAdd} disabled={saving || !draft.trim()} className="px-5 py-2.5 rounded-xl bg-accent text-accent-fg text-sm font-medium disabled:opacity-40 hover:bg-accent-hover transition-colors">Add</button>
        </div>
      </div>
      {notes.length > 0 ? (
        <div className="divide-y divide-border-subtle">
          {notes.map((note) => (
            <div key={note.id} className="px-5 py-3.5 group flex items-start gap-3 hover:bg-surface-raised/50 transition-colors">
              <div className="flex-1 min-w-0">
                <p className="text-sm text-fg">{note.content}</p>
                <div className="flex items-center gap-2 mt-1">
                  <Badge variant={note.provenance === "user_stated" ? "blue" : note.provenance === "data_derived" ? "emerald" : "violet"}>{note.provenance}</Badge>
                  {note.created_at && <span className="text-xs text-fg-faint">{fmtDate(note.created_at)}</span>}
                </div>
              </div>
              {note.provenance === "user_stated" && (
                <button onClick={() => handleDelete(note.id)} className="shrink-0 text-xs text-fg-ghost hover:text-error opacity-0 group-hover:opacity-100 transition-all">Delete</button>
              )}
            </div>
          ))}
        </div>
      ) : <div className="py-12 text-center text-sm text-fg-faint">No notes yet</div>}
    </section>
  );
}

/* ---- Main PropertyDetailView ---- */

export function PropertyDetailView({ propertyId }: { propertyId: string }) {
  const [activeTab, setActiveTab] = useState<Tab>("rent_roll");

  const { data, loading } = useApiQuery<{ property: PropertyDetail; rentRoll: RentRollResponse }>(async () => {
    const [property, rentRoll] = await Promise.all([api.getProperty(propertyId), api.getRentRoll(propertyId)]);
    return { property, rentRoll };
  }, [propertyId]);

  const property = data?.property ?? null;
  const rentRoll = data?.rentRoll ?? null;

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-sm text-fg-faint animate-pulse">Loading property...</div>
      </div>
    );
  }

  if (!property || !rentRoll) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-sm text-fg-muted">Property not found</div>
      </div>
    );
  }

  return (
    <PageContainer wide>
      {/* Breadcrumb + header */}
      <div className="anim-fade-up">
        <div className="flex items-center gap-1.5 text-xs text-fg-faint">
          <Link href="/" className="hover:text-fg-secondary transition-colors">&larr; Home</Link>
          {property.manager_id && property.manager_name && (
            <>
              <span>/</span>
              <Link href={`/managers/${property.manager_id}`} className="hover:text-fg-secondary transition-colors">{property.manager_name}</Link>
            </>
          )}
        </div>
        <h1 className="text-2xl font-bold text-fg mt-3">{property.name}</h1>
        <div className="flex items-center gap-3 mt-1.5">
          <Badge variant={property.property_type === "commercial" ? "cyan" : "blue"}>{property.property_type}</Badge>
          {property.address && (
            <span className="text-sm text-fg-muted">{property.address.street}, {property.address.city}{property.address.state ? `, ${property.address.state}` : ""}</span>
          )}
          {property.year_built > 0 && <span className="text-xs text-fg-ghost">Built {property.year_built}</span>}
          {property.portfolio_name && <span className="text-xs text-fg-ghost">{property.portfolio_name}</span>}
        </div>
      </div>

      {/* KPI strip — staggered */}
      <MetricStrip className="stagger">
        <MetricCard
          label="Occupancy"
          value={`${rentRoll.total_units > 0 ? Math.round((rentRoll.occupied / rentRoll.total_units) * 100) : 0}%`}
          sub={`${rentRoll.occupied}/${rentRoll.total_units} units`}
          trend={rentRoll.vacant === 0 ? "up" : "down"}
        />
        <MetricCard label="Actual Rent" value={fmt$(rentRoll.total_actual_rent)} />
        <MetricCard label="Market Rent" value={fmt$(rentRoll.total_market_rent)} />
        <MetricCard label="Loss to Lease" value={fmt$(rentRoll.total_loss_to_lease)} alert={rentRoll.total_loss_to_lease > 0} sub={rentRoll.total_market_rent > 0 ? `${((rentRoll.total_loss_to_lease / rentRoll.total_market_rent) * 100).toFixed(1)}% of market` : undefined} />
        <MetricCard label="Vacancy Loss" value={fmt$(rentRoll.total_vacancy_loss)} alert={rentRoll.total_vacancy_loss > 0} sub={`${rentRoll.vacant} vacant units`} />
      </MetricStrip>

      {/* Tabs — icon + label, horizontally scrollable on mobile */}
      <div className="border-b border-border-subtle flex gap-0 overflow-x-auto anim-fade-in scrollbar-none" style={{ animationDelay: "200ms" }}>
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex items-center gap-1.5 px-3 sm:px-4 py-3 text-sm font-medium border-b-2 transition-all whitespace-nowrap shrink-0 ${
              activeTab === tab.key ? "border-accent text-fg" : "border-transparent text-fg-muted hover:text-fg-secondary"
            }`}
          >
            <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6}>
              <path strokeLinecap="round" strokeLinejoin="round" d={tab.icon} />
            </svg>
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "rent_roll" && <RentRollTab rentRoll={rentRoll} propertyId={propertyId} />}
      {activeTab === "leases" && <LeasesTab propertyId={propertyId} />}
      {activeTab === "maintenance" && <MaintenanceTab propertyId={propertyId} />}
      {activeTab === "activity" && <ActivityTab propertyId={propertyId} />}
      {activeTab === "notes" && <NotesTab entityType="Property" entityId={propertyId} />}
    </PageContainer>
  );
}
