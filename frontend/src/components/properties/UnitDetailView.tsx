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
import { SparklineChart } from "@/components/ui/SparklineChart";
import { EntityFormPanel, type FieldDef } from "@/components/ui/EntityFormPanel";
import type {
  PropertyDetail,
  RentRollResponse,
  RentRollRow,
  LeaseListItem,
  EntityNoteResponse,
  ChangeSetSummary,
} from "@/lib/types";

type Tab = "overview" | "leases" | "maintenance" | "notes" | "activity";

const TABS: { key: Tab; label: string; icon: string }[] = [
  { key: "overview", label: "Overview", icon: "M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" },
  { key: "leases", label: "Lease History", icon: "M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" },
  { key: "maintenance", label: "Maintenance", icon: "M11.42 15.17l-4.655 5.653a2.548 2.548 0 11-3.586-3.586l5.653-4.655a.685.685 0 00-.17-.896l-2.21-1.59a.676.676 0 01.16-1.18l6.096-2.198a.5.5 0 01.618.618L11.3 13.5a.676.676 0 01-1.18.16l-1.59-2.21a.685.685 0 00-.896-.17z" },
  { key: "notes", label: "Notes", icon: "M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.076-4.076a1.526 1.526 0 011.037-.443 48.282 48.282 0 005.68-.494c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" },
  { key: "activity", label: "Activity", icon: "M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" },
];

/* ---- Card-based Overview ---- */

function CurrentLeaseCard({ row }: { row: RentRollRow }) {
  if (!row.lease || !row.tenant) {
    return (
      <div className="rounded-2xl border border-border bg-surface p-5 card-hover">
        <h3 className="text-[10px] font-semibold text-fg-muted uppercase tracking-wide mb-3">Current Lease</h3>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-surface-sunken flex items-center justify-center">
            <svg className="w-5 h-5 text-fg-ghost" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
            </svg>
          </div>
          <div>
            <p className="text-sm text-fg-muted">No active lease</p>
            {row.status === "vacant" && <p className="text-xs text-fg-ghost mt-0.5">Unit is vacant</p>}
          </div>
        </div>
      </div>
    );
  }

  const { lease, tenant } = row;
  const isExpired = (lease.days_to_expiry ?? 999) <= 0;
  const isExpiringSoon = !isExpired && (lease.days_to_expiry ?? 999) <= 90;

  return (
    <div className="rounded-2xl border border-border bg-surface p-5 card-hover">
      <h3 className="text-[10px] font-semibold text-fg-muted uppercase tracking-wide mb-4">Current Lease &amp; Tenant</h3>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="flex items-start gap-3">
          <div className="w-11 h-11 rounded-full bg-accent/15 flex items-center justify-center shrink-0 ring-2 ring-accent/10">
            <span className="text-accent font-bold text-sm">{tenant.name.charAt(0).toUpperCase()}</span>
          </div>
          <div className="min-w-0">
            <p className="text-fg font-medium text-sm">{tenant.name}</p>
            <p className="text-xs text-fg-muted mt-0.5">{tenant.email}</p>
            {tenant.phone && <p className="text-xs text-fg-muted">{tenant.phone}</p>}
          </div>
        </div>

        <div className="space-y-2.5 text-sm">
          <div className="flex items-center gap-2">
            <Badge variant={lease.status === "active" ? "emerald" : "red"}>{lease.status}</Badge>
            {isExpired && <span className="text-xs text-error font-medium">Expired {Math.abs(lease.days_to_expiry!)} days ago</span>}
            {isExpiringSoon && <span className="text-xs text-warn font-medium">{lease.days_to_expiry} days left</span>}
          </div>
          <p className="text-fg-secondary">{lease.start_date} → {lease.end_date}</p>
          <div className="flex gap-4 text-xs text-fg-muted">
            <span>Rent: <span className="text-fg font-mono font-medium">{fmt$(lease.monthly_rent)}</span></span>
            <span>Deposit: <span className="text-fg font-mono font-medium">{fmt$(lease.deposit)}</span></span>
          </div>
        </div>
      </div>
    </div>
  );
}

function UnitPhysical({ row }: { row: RentRollRow }) {
  return (
    <div className="rounded-2xl border border-border bg-surface p-5 card-hover">
      <h3 className="text-[10px] font-semibold text-fg-muted uppercase tracking-wide mb-4">Unit Details</h3>
      <div className="grid grid-cols-2 gap-4 text-sm">
        {row.bedrooms != null && (
          <div className="rounded-lg bg-surface-sunken p-3">
            <span className="text-fg-muted text-[10px] uppercase tracking-wide">Bedrooms</span>
            <p className="text-fg font-bold text-lg mt-0.5">{row.bedrooms}</p>
          </div>
        )}
        {row.bathrooms != null && (
          <div className="rounded-lg bg-surface-sunken p-3">
            <span className="text-fg-muted text-[10px] uppercase tracking-wide">Bathrooms</span>
            <p className="text-fg font-bold text-lg mt-0.5">{row.bathrooms}</p>
          </div>
        )}
        {row.sqft != null && (
          <div className="rounded-lg bg-surface-sunken p-3">
            <span className="text-fg-muted text-[10px] uppercase tracking-wide">Size</span>
            <p className="text-fg font-bold text-lg mt-0.5">{row.sqft.toLocaleString()} <span className="text-xs font-normal text-fg-muted">sq ft</span></p>
          </div>
        )}
        {row.floor != null && (
          <div className="rounded-lg bg-surface-sunken p-3">
            <span className="text-fg-muted text-[10px] uppercase tracking-wide">Floor</span>
            <p className="text-fg font-bold text-lg mt-0.5">{row.floor}</p>
          </div>
        )}
      </div>

      {row.issues.length > 0 && (
        <div className="mt-4 pt-4 border-t border-border-subtle">
          <span className="text-[10px] text-fg-muted uppercase tracking-wide">Active Issues</span>
          <div className="flex flex-wrap gap-1.5 mt-2">
            {row.issues.map((issue) => (
              <span
                key={issue}
                className={`text-[10px] font-medium px-2 py-0.5 rounded-md border ${
                  issue === "vacant" || issue === "expired_lease"
                    ? "bg-error-soft text-error-fg border-error/30"
                    : issue === "below_market" || issue === "expiring_soon"
                    ? "bg-warn-soft text-warn-fg border-warn/30"
                    : issue === "open_maintenance"
                    ? "bg-sky-500/20 text-sky-300 border-sky-500/30"
                    : "bg-orange-500/20 text-orange-300 border-orange-500/30"
                }`}
              >
                {issue.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function OpenMaintenanceCards({ items }: { items: RentRollRow["maintenance_items"] }) {
  return (
    <div className="rounded-2xl border border-border bg-surface p-5 card-hover">
      <h3 className="text-[10px] font-semibold text-fg-muted uppercase tracking-wide mb-3">
        Open Maintenance {items.length > 0 && <span className="text-fg-faint font-normal">· {items.length}</span>}
      </h3>
      {items.length > 0 ? (
        <div className="space-y-2">
          {items.map((mr) => (
            <div key={mr.id} className="rounded-xl bg-surface-sunken border border-border-subtle px-4 py-3 hover:border-border transition-colors">
              <div className="flex items-center gap-2">
                <Badge variant={mr.priority === "emergency" ? "red" : mr.priority === "high" ? "amber" : "default"}>{mr.priority}</Badge>
                <span className="text-fg text-sm font-medium">{mr.title}</span>
              </div>
              <p className="text-xs text-fg-muted mt-1">{mr.category} · {mr.status}{mr.cost != null && ` · est. ${fmt$(mr.cost)}`}</p>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-fg-faint">No open work orders</p>
      )}
    </div>
  );
}

function OverviewTab({ row }: { row: RentRollRow }) {
  return (
    <div className="space-y-4 stagger">
      <CurrentLeaseCard row={row} />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <UnitPhysical row={row} />
        <OpenMaintenanceCards items={row.maintenance_items} />
      </div>
    </div>
  );
}

/* ---- Lease History ---- */

function LeaseHistoryTab({ unitId, propertyId }: { unitId: string; propertyId: string }) {
  const { data, loading } = useApiQuery(() => api.listLeases({ property_id: propertyId }), [propertyId]);
  if (loading) return <div className="py-12 text-center text-sm text-fg-faint animate-pulse">Loading lease history...</div>;

  const unitLeases = (data?.leases ?? []).filter((l) => l.unit_id === unitId);
  if (unitLeases.length === 0) return <div className="py-12 text-center text-sm text-fg-faint">No lease history for this unit</div>;

  const active = unitLeases.filter((l) => l.status === "active");
  const past = unitLeases.filter((l) => l.status !== "active");

  return (
    <section className="rounded-2xl border border-border bg-surface overflow-hidden anim-fade-up">
      <div className="px-5 py-3.5 border-b border-border-subtle">
        <h2 className="text-xs font-semibold text-fg-secondary uppercase tracking-wide">Lease History <span className="text-fg-faint font-normal">· {unitLeases.length} lease{unitLeases.length !== 1 ? "s" : ""}</span></h2>
      </div>
      <div className="divide-y divide-border-subtle">
        {[...active, ...past].map((lease) => (
          <div key={lease.id} className="px-5 py-4 flex items-center gap-4 group hover:bg-surface-raised/50 transition-colors">
            <div className="w-9 h-9 rounded-xl bg-surface-sunken border border-border-subtle flex items-center justify-center shrink-0 group-hover:border-accent/30 transition-colors">
              <svg className="w-4 h-4 text-fg-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
              </svg>
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm text-fg font-medium">{lease.tenant}</span>
                <Badge variant={lease.status === "active" ? "emerald" : lease.status === "expired" ? "red" : "default"}>{lease.status}</Badge>
              </div>
              <div className="flex items-center gap-3 mt-1 text-xs text-fg-muted">
                <span>{fmtDate(lease.start)} → {fmtDate(lease.end)}</span>
                <span className="font-mono">{fmt$(lease.rent)}/mo</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ---- Maintenance ---- */

function UnitMaintenanceTab({ unitId }: { unitId: string }) {
  const { data, loading } = useApiQuery(() => api.listMaintenance({ unit_id: unitId }), [unitId]);
  const { data: trend } = useApiQuery(() => api.maintenanceTrend({ unit_id: unitId }), [unitId]);
  if (loading) return <div className="py-12 text-center text-sm text-fg-faint animate-pulse">Loading maintenance...</div>;

  const unitRequests = data?.requests ?? [];
  if (unitRequests.length === 0 && (!trend || trend.periods.length === 0)) {
    return <div className="py-12 text-center text-sm text-fg-faint">No maintenance requests for this unit</div>;
  }

  const open = unitRequests.filter((r) => r.status === "open" || r.status === "in_progress");
  const closed = unitRequests.filter((r) => r.status !== "open" && r.status !== "in_progress");

  const trendPeriods = trend?.periods ?? [];
  const latestCost = trendPeriods.length > 0 ? trendPeriods[trendPeriods.length - 1].total_cost : 0;
  const latestRes = trendPeriods.length > 0 ? trendPeriods[trendPeriods.length - 1].avg_resolution_days : null;

  return (
    <div className="space-y-4 anim-fade-up">
      {trendPeriods.length >= 2 && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <SparklineChart
            data={trendPeriods}
            dataKey="opened"
            color="var(--color-warn)"
            label="Opened / Month"
            value={String(trendPeriods[trendPeriods.length - 1]?.opened ?? 0)}
            invertTrend
          />
          <SparklineChart
            data={trendPeriods}
            dataKey="total_cost"
            color="var(--color-error)"
            label="Cost / Month"
            value={fmt$(latestCost)}
            valueFormatter={(v) => fmt$(v)}
            invertTrend
          />
          <SparklineChart
            data={trendPeriods}
            dataKey="avg_resolution_days"
            color="var(--color-accent)"
            label="Avg Resolution (days)"
            value={latestRes != null ? `${latestRes}d` : "—"}
            valueFormatter={(v) => `${v.toFixed(1)}d`}
            invertTrend
          />
        </div>
      )}

      <section className="rounded-2xl border border-border bg-surface overflow-hidden">
        <div className="px-5 py-3.5 border-b border-border-subtle">
          <h2 className="text-xs font-semibold text-fg-secondary uppercase tracking-wide">Maintenance <span className="text-fg-faint font-normal">· {unitRequests.length} total · {open.length} open</span></h2>
        </div>
        {unitRequests.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-border">{["Title", "Category", "Priority", "Status", "Cost", "Created", "Resolved"].map((h) => <th key={h} className="text-left px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">{h}</th>)}</tr></thead>
              <tbody>
                {[...open, ...closed].map((mr) => (
                  <tr key={mr.id} className="border-b border-border-subtle hover:bg-surface-raised transition-colors">
                    <td className="px-4 py-2.5 text-sm text-fg">{mr.title}</td>
                    <td className="px-4 py-2.5 text-sm text-fg-muted">{mr.category}</td>
                    <td className="px-4 py-2.5"><Badge variant={mr.priority === "emergency" ? "red" : mr.priority === "high" ? "amber" : "default"}>{mr.priority}</Badge></td>
                    <td className="px-4 py-2.5"><Badge variant={mr.status === "open" ? "amber" : mr.status === "completed" ? "emerald" : "default"}>{mr.status}</Badge></td>
                    <td className="px-4 py-2.5 font-mono text-sm text-fg-muted">{mr.cost != null ? fmt$(mr.cost) : "—"}</td>
                    <td className="px-4 py-2.5 text-sm text-fg-muted">{fmtDate(mr.created)}</td>
                    <td className="px-4 py-2.5 text-sm text-fg-muted">{mr.resolved ? fmtDate(mr.resolved) : "—"}</td>
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

/* ---- Notes ---- */

function UnitNotesTab({ unitId }: { unitId: string }) {
  const { data, loading, refetch } = useApiQuery(() => api.listEntityNotes("Unit", unitId), [unitId]);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleAdd() {
    if (!draft.trim()) return;
    setSaving(true);
    try { await api.createEntityNote("Unit", unitId, draft.trim()); setDraft(""); refetch(); } finally { setSaving(false); }
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
          <input value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleAdd()} placeholder="Add a note about this unit..." className="flex-1 bg-surface-sunken border border-border rounded-xl px-3.5 py-2.5 text-sm text-fg placeholder:text-fg-ghost focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent transition-all" />
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

/* ---- Activity ---- */

function UnitActivityTab({ unitId }: { unitId: string }) {
  const { data, loading } = useApiQuery(() => api.entityEvents(unitId, 50), [unitId]);
  if (loading) return <div className="py-12 text-center text-sm text-fg-faint animate-pulse">Loading activity...</div>;
  if (!data || data.changesets.length === 0) return <div className="py-12 text-center text-sm text-fg-faint">No activity recorded yet</div>;

  return (
    <section className="rounded-2xl border border-border bg-surface overflow-hidden anim-fade-up">
      <div className="px-5 py-3.5 border-b border-border-subtle">
        <h2 className="text-xs font-semibold text-fg-secondary uppercase tracking-wide">Activity <span className="text-fg-faint font-normal">· {data.changesets.length} events</span></h2>
      </div>
      <div className="divide-y divide-border-subtle">
        {data.changesets.map((cs) => (
          <div key={cs.id} className="px-5 py-3.5 flex items-start gap-4 group hover:bg-surface-raised/50 transition-colors">
            <div className="shrink-0 w-2 h-2 rounded-full bg-accent mt-1.5 group-hover:scale-150 transition-transform" />
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline gap-2">
                <span className="text-sm text-fg font-medium">{cs.source}</span>
                {cs.report_type && <Badge variant="default">{cs.report_type}</Badge>}
                <span className="text-xs text-fg-faint ml-auto shrink-0">{fmtDate(cs.timestamp)}</span>
              </div>
              <div className="flex gap-3 mt-1 text-xs text-fg-muted">
                {cs.summary.created > 0 && <span className="text-ok">+{cs.summary.created} created</span>}
                {cs.summary.updated > 0 && <span className="text-warn">{cs.summary.updated} updated</span>}
                {cs.summary.removed > 0 && <span className="text-error">{cs.summary.removed} removed</span>}
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ---- Main UnitDetailView ---- */

const MAINT_FIELDS: FieldDef[] = [
  { name: "title", label: "Title", required: true, placeholder: "Leaky faucet in kitchen" },
  { name: "description", label: "Description", type: "textarea", placeholder: "Details..." },
  { name: "category", label: "Category", type: "select", defaultValue: "general", options: [
    { value: "plumbing", label: "Plumbing" }, { value: "electrical", label: "Electrical" },
    { value: "hvac", label: "HVAC" }, { value: "appliance", label: "Appliance" },
    { value: "structural", label: "Structural" }, { value: "general", label: "General" },
    { value: "other", label: "Other" },
  ]},
  { name: "priority", label: "Priority", type: "select", defaultValue: "medium", options: [
    { value: "low", label: "Low" }, { value: "medium", label: "Medium" },
    { value: "high", label: "High" }, { value: "emergency", label: "Emergency" },
  ]},
];

export function UnitDetailView({ propertyId, unitId }: { propertyId: string; unitId: string }) {
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [showAddMaint, setShowAddMaint] = useState(false);

  const { data, loading, refetch } = useApiQuery<{ property: PropertyDetail; rentRoll: RentRollResponse }>(async () => {
    const [property, rentRoll] = await Promise.all([api.getProperty(propertyId), api.getRentRoll(propertyId)]);
    return { property, rentRoll };
  }, [propertyId]);

  const property = data?.property ?? null;
  const rentRoll = data?.rentRoll ?? null;
  const unitRow = rentRoll?.rows.find((r) => r.unit_id === unitId) ?? null;

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-sm text-fg-faint animate-pulse">Loading unit...</div>
      </div>
    );
  }

  if (!property || !rentRoll || !unitRow) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-sm text-fg-muted">Unit not found</div>
      </div>
    );
  }

  return (
    <PageContainer>
      {/* Breadcrumb + hero */}
      <div className="anim-fade-up">
        <div className="flex items-center gap-1.5 text-xs text-fg-faint">
          <Link href="/" className="hover:text-fg-secondary transition-colors">&larr; Home</Link>
          {property.manager_id && property.manager_name && (
            <>
              <span>/</span>
              <Link href={`/managers/${property.manager_id}`} className="hover:text-fg-secondary transition-colors">{property.manager_name}</Link>
            </>
          )}
          <span>/</span>
          <Link href={`/properties/${propertyId}`} className="hover:text-fg-secondary transition-colors">{property.name}</Link>
          <span>/</span>
          <span className="text-fg-muted">Unit {unitRow.unit_number}</span>
        </div>

        <div className="flex items-start justify-between mt-3">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-2xl bg-surface-sunken border-2 border-border flex items-center justify-center shadow-sm">
              <span className="text-xl font-bold text-fg font-mono">{unitRow.unit_number}</span>
            </div>
            <div>
              <h1 className="text-2xl font-bold text-fg tracking-tight">Unit {unitRow.unit_number}</h1>
              <div className="flex items-center gap-3 mt-0.5">
                <Badge variant={unitRow.status === "occupied" ? "emerald" : unitRow.status === "vacant" ? "red" : unitRow.status === "maintenance" ? "amber" : "default"}>{unitRow.status}</Badge>
                <span className="text-sm text-fg-muted">{property.name}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* KPI strip — staggered */}
      <MetricStrip className="grid-cols-2 sm:grid-cols-4 lg:grid-cols-4 stagger">
        <MetricCard label="Current Rent" value={fmt$(unitRow.current_rent)} sub={unitRow.tenant ? `Tenant: ${unitRow.tenant.name}` : "Vacant"} />
        <MetricCard label="Market Rent" value={fmt$(unitRow.market_rent)} />
        <MetricCard label="Rent Gap" value={fmt$(unitRow.rent_gap)} alert={unitRow.rent_gap < 0} sub={unitRow.pct_below_market > 0 ? `${unitRow.pct_below_market}% below market` : "At or above market"} />
        <MetricCard label="Open Issues" value={unitRow.issues.length} alert={unitRow.issues.length > 0} sub={unitRow.open_maintenance > 0 ? `${unitRow.open_maintenance} maintenance` : "No open items"} />
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

      {/* Quick-add bar */}
      <div className="flex gap-2.5 flex-wrap">
        <button onClick={() => setShowAddMaint(true)} className="h-9 flex items-center gap-2 px-4 rounded-xl border border-dashed border-border bg-surface hover:border-accent/40 hover:text-accent hover:shadow-md hover:shadow-accent/5 text-xs font-medium text-fg-muted transition-all btn-glow">
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>
          Add Maintenance
        </button>
      </div>

      {activeTab === "overview" && <OverviewTab row={unitRow} />}
      {activeTab === "leases" && <LeaseHistoryTab unitId={unitId} propertyId={propertyId} />}
      {activeTab === "maintenance" && <UnitMaintenanceTab unitId={unitId} />}
      {activeTab === "notes" && <UnitNotesTab unitId={unitId} />}
      {activeTab === "activity" && <UnitActivityTab unitId={unitId} />}

      <EntityFormPanel
        open={showAddMaint}
        onClose={() => setShowAddMaint(false)}
        title="Add Maintenance Request"
        fields={MAINT_FIELDS}
        submitLabel="Create Request"
        onSubmit={async (values) => {
          await api.createMaintenance({ property_id: propertyId, unit_id: unitId, ...values } as Parameters<typeof api.createMaintenance>[0]);
          refetch();
        }}
      />

    </PageContainer>
  );
}
