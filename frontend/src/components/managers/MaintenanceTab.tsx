"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmt$ } from "@/lib/format";
import { MetricCard } from "@/components/ui/MetricCard";
import { MetricStrip } from "@/components/ui/MetricStrip";
import { Badge } from "@/components/ui/Badge";
import type { MaintenanceRequest, ManagerPropertySummary } from "@/lib/types";

type Priority = MaintenanceRequest["priority"];
type Status = MaintenanceRequest["status"];

const PRIORITY_ORDER: Record<Priority, number> = {
  emergency: 0,
  high: 1,
  medium: 2,
  low: 3,
};

const PRIORITY_VARIANT: Record<Priority, "red" | "amber" | "blue" | "default"> = {
  emergency: "red",
  high: "red",
  medium: "amber",
  low: "blue",
};

const STATUS_VARIANT: Record<Status, "cyan" | "amber" | "emerald" | "default"> = {
  open: "cyan",
  in_progress: "amber",
  completed: "emerald",
  cancelled: "default",
};

function daysSince(dateStr: string): number {
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return 0;
  return Math.floor((Date.now() - d.getTime()) / 86_400_000);
}

interface PropertyGroup {
  propertyId: string;
  propertyName: string;
  requests: MaintenanceRequest[];
}

function PriorityHeatmap({ groups }: { groups: PropertyGroup[] }) {
  const priorityCounts = (requests: MaintenanceRequest[]) => {
    const counts: Record<Priority, number> = { emergency: 0, high: 0, medium: 0, low: 0 };
    for (const r of requests) {
      if (r.status === "open" || r.status === "in_progress") {
        counts[r.priority]++;
      }
    }
    return counts;
  };

  return (
    <div className="rounded-xl border border-border bg-surface overflow-hidden">
      <div className="px-5 py-3 border-b border-border-subtle">
        <h2 className="text-xs font-semibold text-fg-secondary uppercase tracking-wide">
          Priority by Property
        </h2>
      </div>
      <div className="p-4 space-y-2">
        {groups.map((g) => {
          const counts = priorityCounts(g.requests);
          const total = counts.emergency + counts.high + counts.medium + counts.low;
          if (total === 0) return null;
          return (
            <div key={g.propertyId} className="flex items-center gap-3">
              <span className="text-xs text-fg-secondary truncate w-40 shrink-0">{g.propertyName}</span>
              <div className="flex-1 flex gap-0.5 h-5 rounded overflow-hidden bg-surface-sunken">
                {counts.emergency > 0 && (
                  <div
                    className="bg-error h-full flex items-center justify-center"
                    style={{ flex: counts.emergency }}
                    title={`${counts.emergency} emergency`}
                  >
                    <span className="text-[9px] text-white font-bold">{counts.emergency}</span>
                  </div>
                )}
                {counts.high > 0 && (
                  <div
                    className="bg-orange-500 h-full flex items-center justify-center"
                    style={{ flex: counts.high }}
                    title={`${counts.high} high`}
                  >
                    <span className="text-[9px] text-white font-bold">{counts.high}</span>
                  </div>
                )}
                {counts.medium > 0 && (
                  <div
                    className="bg-warn h-full flex items-center justify-center"
                    style={{ flex: counts.medium }}
                    title={`${counts.medium} medium`}
                  >
                    <span className="text-[9px] text-white font-bold">{counts.medium}</span>
                  </div>
                )}
                {counts.low > 0 && (
                  <div
                    className="bg-sky-500 h-full flex items-center justify-center"
                    style={{ flex: counts.low }}
                    title={`${counts.low} low`}
                  >
                    <span className="text-[9px] text-white font-bold">{counts.low}</span>
                  </div>
                )}
              </div>
              <span className="text-[10px] text-fg-faint w-6 text-right shrink-0">{total}</span>
            </div>
          );
        })}
        <div className="flex items-center gap-3 pt-2 border-t border-border-subtle">
          <span className="text-[10px] text-fg-ghost">Legend:</span>
          <span className="flex items-center gap-1 text-[10px] text-fg-muted"><span className="w-2.5 h-2.5 rounded-sm bg-error" /> Emergency</span>
          <span className="flex items-center gap-1 text-[10px] text-fg-muted"><span className="w-2.5 h-2.5 rounded-sm bg-orange-500" /> High</span>
          <span className="flex items-center gap-1 text-[10px] text-fg-muted"><span className="w-2.5 h-2.5 rounded-sm bg-warn" /> Medium</span>
          <span className="flex items-center gap-1 text-[10px] text-fg-muted"><span className="w-2.5 h-2.5 rounded-sm bg-sky-500" /> Low</span>
        </div>
      </div>
    </div>
  );
}

function RequestRow({ r, propertyName }: { r: MaintenanceRequest; propertyName: string }) {
  const age = daysSince(r.created);
  const isStale = (r.status === "open" || r.status === "in_progress") && age > 14;

  return (
    <tr className={`border-b border-border-subtle hover:bg-surface-raised transition-colors ${isStale ? "bg-warn-soft/30" : ""}`}>
      <td className="px-4 py-2.5 text-sm text-fg">{r.title}</td>
      <td className="px-4 py-2.5 text-xs text-fg-secondary">{propertyName}</td>
      <td className="px-4 py-2.5 text-xs text-fg-muted">{r.category}</td>
      <td className="px-4 py-2.5">
        <Badge variant={PRIORITY_VARIANT[r.priority]}>{r.priority}</Badge>
      </td>
      <td className="px-4 py-2.5">
        <Badge variant={STATUS_VARIANT[r.status]}>{r.status.replace("_", " ")}</Badge>
      </td>
      <td className="px-4 py-2.5 text-right">
        <span className={`text-xs font-mono ${isStale ? "text-warn font-bold" : "text-fg-muted"}`}>
          {age}d
        </span>
      </td>
      <td className="px-4 py-2.5 text-right text-xs font-mono text-fg-muted">
        {r.cost != null ? fmt$(r.cost) : "—"}
      </td>
    </tr>
  );
}

export function MaintenanceTab({
  properties,
}: {
  properties: ManagerPropertySummary[];
}) {
  const [allRequests, setAllRequests] = useState<MaintenanceRequest[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (properties.length === 0) {
      setLoading(false);
      return;
    }

    const propertyIds = properties.map((p) => p.property_id);

    Promise.all(
      propertyIds.map((pid) =>
        api.listMaintenance({ property_id: pid }).catch(() => ({ count: 0, requests: [] })),
      ),
    )
      .then((results) => {
        const merged = results.flatMap((r) => r.requests);
        setAllRequests(merged);
      })
      .finally(() => setLoading(false));
  }, [properties]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <span className="text-sm text-fg-faint animate-pulse">Loading maintenance data...</span>
      </div>
    );
  }

  const propertyNameMap = new Map(properties.map((p) => [p.property_id, p.property_name]));

  const active = allRequests.filter((r) => r.status === "open" || r.status === "in_progress");
  const openCount = allRequests.filter((r) => r.status === "open").length;
  const inProgressCount = allRequests.filter((r) => r.status === "in_progress").length;
  const emergencyCount = active.filter((r) => r.priority === "emergency").length;
  const estimatedCost = active.reduce((s, r) => s + (r.cost ?? 0), 0);
  const staleCount = active.filter((r) => daysSince(r.created) > 14).length;

  const groups: PropertyGroup[] = properties
    .map((p) => ({
      propertyId: p.property_id,
      propertyName: p.property_name,
      requests: allRequests.filter((r) => r.property_id === p.property_id),
    }))
    .filter((g) => g.requests.length > 0);

  const sortedActive = [...active].sort(
    (a, b) => PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority] || daysSince(b.created) - daysSince(a.created),
  );

  if (allRequests.length === 0) {
    return <p className="text-sm text-fg-faint text-center py-12">No maintenance requests</p>;
  }

  return (
    <div className="space-y-6">
      <MetricStrip className="lg:grid-cols-5">
        <MetricCard label="Open" value={openCount} alert={openCount > 0} />
        <MetricCard label="In Progress" value={inProgressCount} />
        <MetricCard label="Emergency" value={emergencyCount} alert={emergencyCount > 0} />
        <MetricCard label="Est. Cost" value={estimatedCost > 0 ? fmt$(estimatedCost) : "—"} />
        <MetricCard
          label="Stale (14d+)"
          value={staleCount}
          alert={staleCount > 0}
          sub={staleCount > 0 ? "no status change" : undefined}
        />
      </MetricStrip>

      {groups.length > 1 && <PriorityHeatmap groups={groups} />}

      <div className="rounded-xl border border-border bg-surface overflow-hidden">
        <div className="px-5 py-3 border-b border-border-subtle flex items-center justify-between">
          <h2 className="text-xs font-semibold text-fg-secondary uppercase tracking-wide">
            Active Requests ({sortedActive.length})
          </h2>
          {staleCount > 0 && (
            <span className="text-[10px] text-warn font-medium">
              {staleCount} stale — open &gt;14 days
            </span>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                {["Title", "Property", "Category", "Priority", "Status", "Age", "Est. Cost"].map((h) => (
                  <th
                    key={h}
                    className={`text-left px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase tracking-wide ${
                      h === "Age" || h === "Est. Cost" ? "text-right" : ""
                    }`}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedActive.map((r) => (
                <RequestRow
                  key={r.id}
                  r={r}
                  propertyName={propertyNameMap.get(r.property_id) ?? r.property_id}
                />
              ))}
              {sortedActive.length === 0 && (
                <tr>
                  <td colSpan={7} className="text-center py-12 text-sm text-fg-faint">
                    No active maintenance requests
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
