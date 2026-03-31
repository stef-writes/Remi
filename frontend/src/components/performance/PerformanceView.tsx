"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { fmt$, fmtDate, pct } from "@/lib/format";
import { useApiQuery } from "@/hooks/useApiQuery";
import { PageContainer } from "@/components/ui/PageContainer";
import { ManagerFilter } from "@/components/ui/ManagerFilter";
import type { ManagerSnapshot, ManagerListItem } from "@/lib/types";

const SNAPSHOT_DATE_FORMAT: Intl.DateTimeFormatOptions = {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
};

function Delta({ prev, curr, fmt, invert }: { prev: number; curr: number; fmt: (n: number) => string; invert?: boolean }) {
  const diff = curr - prev;
  if (Math.abs(diff) < 0.001) return <span className="text-fg-faint">—</span>;
  const positive = invert ? diff < 0 : diff > 0;
  return (
    <span className={positive ? "text-ok" : "text-error"}>
      {diff > 0 ? "+" : ""}{fmt(diff)}
    </span>
  );
}

interface SnapshotRow {
  manager_id: string;
  manager_name: string;
  current: ManagerSnapshot;
  previous: ManagerSnapshot | null;
}

export function PerformanceView() {
  const [managerId, setManagerId] = useState("");
  const { data, loading } = useApiQuery<{
    managers: ManagerListItem[];
    snapshots: ManagerSnapshot[];
  }>(async () => {
    const [managers, snap] = await Promise.all([
      api.listManagers().catch(() => []),
      api.snapshots(managerId || undefined).catch(() => ({ total: 0, snapshots: [] })),
    ]);
    return { managers, snapshots: snap.snapshots };
  }, [managerId]);

  const managers = data?.managers ?? [];
  const snapshots = data?.snapshots ?? [];

  // Group snapshots by manager, pick latest + previous
  const rows: SnapshotRow[] = [];
  const byManager = new Map<string, ManagerSnapshot[]>();
  for (const s of snapshots) {
    const arr = byManager.get(s.manager_id) || [];
    arr.push(s);
    byManager.set(s.manager_id, arr);
  }
  for (const [mid, arr] of byManager) {
    arr.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
    const current = arr[arr.length - 1];
    const previous = arr.length >= 2 ? arr[arr.length - 2] : null;
    if (current.total_units > 0) {
      rows.push({ manager_id: mid, manager_name: current.manager_name, current, previous });
    }
  }
  rows.sort((a, b) => b.current.total_rent - a.current.total_rent);

  // If we have a single manager selected, show timeline instead
  const singleManager = managerId && byManager.has(managerId);
  const timeline = singleManager
    ? (byManager.get(managerId) || []).sort(
        (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      )
    : [];

  return (
    <PageContainer wide>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-fg">PM Performance</h1>
            <p className="text-xs text-fg-muted mt-1">
              {snapshots.length === 0
                ? "No snapshots yet — upload reports to start tracking"
                : `${byManager.size} managers tracked across ${snapshots.length} snapshots`}
            </p>
          </div>
          <ManagerFilter
            managers={managers}
            value={managerId}
            onChange={setManagerId}
          />
        </div>

        {loading && (
          <div className="text-sm text-fg-faint animate-pulse">Loading...</div>
        )}

        {snapshots.length === 0 && (
          <div className="rounded-xl border border-border bg-surface px-8 py-16 text-center">
            <p className="text-fg-muted text-sm">
              Performance snapshots are captured automatically each time reports are uploaded.
            </p>
            <p className="text-fg-faint text-xs mt-2">
              Upload at least one report to create the first snapshot, then upload again later to see trends.
            </p>
          </div>
        )}

        {/* All-manager comparison table */}
        {!singleManager && rows.length > 0 && (
          <div className="rounded-xl border border-border bg-surface overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase tracking-wide">Manager</th>
                    <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase tracking-wide">Units</th>
                    <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase tracking-wide">Occupancy</th>
                    <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase tracking-wide">Revenue</th>
                    <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase tracking-wide">LTL</th>
                    <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase tracking-wide">Delinquent</th>
                    <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase tracking-wide">Vacant</th>
                    <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase tracking-wide">Last Snapshot</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr
                      key={r.manager_id}
                      className="border-b border-border-subtle hover:bg-surface-raised transition-colors cursor-pointer"
                      onClick={() => setManagerId(r.manager_id)}
                    >
                      <td className="px-4 py-2.5 text-fg font-medium">{r.manager_name}</td>
                      <td className="px-4 py-2.5 text-right text-fg-secondary">
                        {r.current.total_units}
                        {r.previous && (
                          <span className="ml-1.5 text-[9px]">
                            <Delta prev={r.previous.total_units} curr={r.current.total_units} fmt={String} />
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <span className={r.current.occupancy_rate < 0.9 ? "text-warn" : "text-fg-secondary"}>
                          {pct(r.current.occupancy_rate)}
                        </span>
                        {r.previous && (
                          <span className="ml-1.5 text-[9px]">
                            <Delta prev={r.previous.occupancy_rate} curr={r.current.occupancy_rate} fmt={pct} />
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-right text-fg-secondary">
                        {fmt$(r.current.total_rent)}
                        {r.previous && (
                          <span className="ml-1.5 text-[9px]">
                            <Delta prev={r.previous.total_rent} curr={r.current.total_rent} fmt={fmt$} />
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <span className={r.current.loss_to_lease > 0 ? "text-warn" : "text-fg-muted"}>
                          {r.current.loss_to_lease > 0 ? fmt$(r.current.loss_to_lease) : "—"}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <span className={r.current.delinquent_count > 0 ? "text-error" : "text-fg-muted"}>
                          {r.current.delinquent_count || "—"}
                        </span>
                        {r.current.delinquent_balance > 0 && (
                          <span className="text-[9px] text-error/60 ml-1">{fmt$(r.current.delinquent_balance)}</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <span className={r.current.vacant > 0 ? "text-error" : "text-fg-muted"}>
                          {r.current.vacant || "—"}
                        </span>
                        {r.previous && (
                          <span className="ml-1.5 text-[9px]">
                            <Delta prev={r.previous.vacant} curr={r.current.vacant} fmt={String} invert />
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-right text-fg-faint text-[10px]">
                        {fmtDate(r.current.timestamp, SNAPSHOT_DATE_FORMAT)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Single-manager timeline */}
        {singleManager && timeline.length > 0 && (
          <>
            <button
              onClick={() => setManagerId("")}
              className="text-xs text-fg-muted hover:text-fg-secondary transition-colors"
            >
              &larr; All Managers
            </button>
            <h2 className="text-sm font-semibold text-fg">
              {timeline[0].manager_name} — Snapshot Timeline
            </h2>
            <div className="rounded-xl border border-border bg-surface overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase tracking-wide">Snapshot</th>
                      <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase tracking-wide">Properties</th>
                      <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase tracking-wide">Units</th>
                      <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase tracking-wide">Occupancy</th>
                      <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase tracking-wide">Revenue</th>
                      <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase tracking-wide">LTL</th>
                      <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase tracking-wide">Delinquent</th>
                      <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase tracking-wide">Vacant</th>
                    </tr>
                  </thead>
                  <tbody>
                    {timeline.map((s, i) => {
                      const prev = i > 0 ? timeline[i - 1] : null;
                      return (
                        <tr key={s.timestamp} className="border-b border-border-subtle hover:bg-surface-raised">
                          <td className="px-4 py-2.5 text-fg-secondary text-[10px]">{fmtDate(s.timestamp, SNAPSHOT_DATE_FORMAT)}</td>
                          <td className="px-4 py-2.5 text-right text-fg-secondary">{s.property_count}</td>
                          <td className="px-4 py-2.5 text-right text-fg-secondary">
                            {s.total_units}
                            {prev && <span className="ml-1.5 text-[9px]"><Delta prev={prev.total_units} curr={s.total_units} fmt={String} /></span>}
                          </td>
                          <td className="px-4 py-2.5 text-right">
                            <span className={s.occupancy_rate < 0.9 ? "text-warn" : "text-fg-secondary"}>{pct(s.occupancy_rate)}</span>
                            {prev && <span className="ml-1.5 text-[9px]"><Delta prev={prev.occupancy_rate} curr={s.occupancy_rate} fmt={pct} /></span>}
                          </td>
                          <td className="px-4 py-2.5 text-right text-fg-secondary">
                            {fmt$(s.total_rent)}
                            {prev && <span className="ml-1.5 text-[9px]"><Delta prev={prev.total_rent} curr={s.total_rent} fmt={fmt$} /></span>}
                          </td>
                          <td className="px-4 py-2.5 text-right">
                            <span className={s.loss_to_lease > 0 ? "text-warn" : "text-fg-muted"}>
                              {s.loss_to_lease > 0 ? fmt$(s.loss_to_lease) : "—"}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 text-right">
                            <span className={s.delinquent_count > 0 ? "text-error" : "text-fg-muted"}>
                              {s.delinquent_count || "—"}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 text-right">
                            <span className={s.vacant > 0 ? "text-error" : "text-fg-muted"}>
                              {s.vacant || "—"}
                            </span>
                            {prev && <span className="ml-1.5 text-[9px]"><Delta prev={prev.vacant} curr={s.vacant} fmt={String} invert /></span>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
    </PageContainer>
  );
}
