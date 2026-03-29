"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ManagerFilter } from "@/components/ui/ManagerFilter";
import type { ManagerSnapshot, ManagerListItem } from "@/lib/types";

function fmt$(n: number) {
  return "$" + n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}
function pct(n: number) {
  return (n * 100).toFixed(1) + "%";
}
function fmtDate(s: string) {
  return new Date(s).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function Delta({ prev, curr, fmt, invert }: { prev: number; curr: number; fmt: (n: number) => string; invert?: boolean }) {
  const diff = curr - prev;
  if (Math.abs(diff) < 0.001) return <span className="text-zinc-600">—</span>;
  const positive = invert ? diff < 0 : diff > 0;
  return (
    <span className={positive ? "text-emerald-400" : "text-red-400"}>
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
  const [snapshots, setSnapshots] = useState<ManagerSnapshot[]>([]);
  const [managerId, setManagerId] = useState("");
  const [managers, setManagers] = useState<ManagerListItem[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [mgrs, snap] = await Promise.all([
        api.listManagers().catch(() => []),
        api.snapshots(managerId || undefined).catch(() => ({ total: 0, snapshots: [] })),
      ]);
      setManagers(mgrs);
      setSnapshots(snap.snapshots);
    } finally {
      setLoading(false);
    }
  }, [managerId]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

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
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-zinc-100">PM Performance</h1>
            <p className="text-xs text-zinc-500 mt-1">
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

        {snapshots.length === 0 && (
          <div className="rounded-xl border border-zinc-800/60 bg-zinc-900/40 px-8 py-16 text-center">
            <p className="text-zinc-500 text-sm">
              Performance snapshots are captured automatically each time reports are uploaded.
            </p>
            <p className="text-zinc-600 text-xs mt-2">
              Upload at least one report to create the first snapshot, then upload again later to see trends.
            </p>
          </div>
        )}

        {/* All-manager comparison table */}
        {!singleManager && rows.length > 0 && (
          <div className="rounded-xl border border-zinc-800/60 bg-zinc-900/40 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-zinc-800/60">
                    <th className="text-left px-4 py-2.5 text-[10px] font-semibold text-zinc-500 uppercase tracking-wide">Manager</th>
                    <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-zinc-500 uppercase tracking-wide">Units</th>
                    <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-zinc-500 uppercase tracking-wide">Occupancy</th>
                    <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-zinc-500 uppercase tracking-wide">Revenue</th>
                    <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-zinc-500 uppercase tracking-wide">LTL</th>
                    <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-zinc-500 uppercase tracking-wide">Delinquent</th>
                    <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-zinc-500 uppercase tracking-wide">Vacant</th>
                    <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-zinc-500 uppercase tracking-wide">Last Snapshot</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr
                      key={r.manager_id}
                      className="border-b border-zinc-800/30 hover:bg-zinc-800/20 transition-colors cursor-pointer"
                      onClick={() => setManagerId(r.manager_id)}
                    >
                      <td className="px-4 py-2.5 text-zinc-200 font-medium">{r.manager_name}</td>
                      <td className="px-4 py-2.5 text-right text-zinc-300">
                        {r.current.total_units}
                        {r.previous && (
                          <span className="ml-1.5 text-[9px]">
                            <Delta prev={r.previous.total_units} curr={r.current.total_units} fmt={String} />
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <span className={r.current.occupancy_rate < 0.9 ? "text-amber-400" : "text-zinc-300"}>
                          {pct(r.current.occupancy_rate)}
                        </span>
                        {r.previous && (
                          <span className="ml-1.5 text-[9px]">
                            <Delta prev={r.previous.occupancy_rate} curr={r.current.occupancy_rate} fmt={pct} />
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-right text-zinc-300">
                        {fmt$(r.current.total_rent)}
                        {r.previous && (
                          <span className="ml-1.5 text-[9px]">
                            <Delta prev={r.previous.total_rent} curr={r.current.total_rent} fmt={fmt$} />
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <span className={r.current.loss_to_lease > 0 ? "text-amber-400" : "text-zinc-500"}>
                          {r.current.loss_to_lease > 0 ? fmt$(r.current.loss_to_lease) : "—"}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <span className={r.current.delinquent_count > 0 ? "text-red-400" : "text-zinc-500"}>
                          {r.current.delinquent_count || "—"}
                        </span>
                        {r.current.delinquent_balance > 0 && (
                          <span className="text-[9px] text-red-400/60 ml-1">{fmt$(r.current.delinquent_balance)}</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <span className={r.current.vacant > 0 ? "text-red-400" : "text-zinc-500"}>
                          {r.current.vacant || "—"}
                        </span>
                        {r.previous && (
                          <span className="ml-1.5 text-[9px]">
                            <Delta prev={r.previous.vacant} curr={r.current.vacant} fmt={String} invert />
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-right text-zinc-600 text-[10px]">
                        {fmtDate(r.current.timestamp)}
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
              className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              &larr; All Managers
            </button>
            <h2 className="text-sm font-semibold text-zinc-200">
              {timeline[0].manager_name} — Snapshot Timeline
            </h2>
            <div className="rounded-xl border border-zinc-800/60 bg-zinc-900/40 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-zinc-800/60">
                      <th className="text-left px-4 py-2.5 text-[10px] font-semibold text-zinc-500 uppercase tracking-wide">Snapshot</th>
                      <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-zinc-500 uppercase tracking-wide">Properties</th>
                      <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-zinc-500 uppercase tracking-wide">Units</th>
                      <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-zinc-500 uppercase tracking-wide">Occupancy</th>
                      <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-zinc-500 uppercase tracking-wide">Revenue</th>
                      <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-zinc-500 uppercase tracking-wide">LTL</th>
                      <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-zinc-500 uppercase tracking-wide">Delinquent</th>
                      <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-zinc-500 uppercase tracking-wide">Vacant</th>
                    </tr>
                  </thead>
                  <tbody>
                    {timeline.map((s, i) => {
                      const prev = i > 0 ? timeline[i - 1] : null;
                      return (
                        <tr key={s.timestamp} className="border-b border-zinc-800/30 hover:bg-zinc-800/20">
                          <td className="px-4 py-2.5 text-zinc-400 text-[10px]">{fmtDate(s.timestamp)}</td>
                          <td className="px-4 py-2.5 text-right text-zinc-300">{s.property_count}</td>
                          <td className="px-4 py-2.5 text-right text-zinc-300">
                            {s.total_units}
                            {prev && <span className="ml-1.5 text-[9px]"><Delta prev={prev.total_units} curr={s.total_units} fmt={String} /></span>}
                          </td>
                          <td className="px-4 py-2.5 text-right">
                            <span className={s.occupancy_rate < 0.9 ? "text-amber-400" : "text-zinc-300"}>{pct(s.occupancy_rate)}</span>
                            {prev && <span className="ml-1.5 text-[9px]"><Delta prev={prev.occupancy_rate} curr={s.occupancy_rate} fmt={pct} /></span>}
                          </td>
                          <td className="px-4 py-2.5 text-right text-zinc-300">
                            {fmt$(s.total_rent)}
                            {prev && <span className="ml-1.5 text-[9px]"><Delta prev={prev.total_rent} curr={s.total_rent} fmt={fmt$} /></span>}
                          </td>
                          <td className="px-4 py-2.5 text-right">
                            <span className={s.loss_to_lease > 0 ? "text-amber-400" : "text-zinc-500"}>
                              {s.loss_to_lease > 0 ? fmt$(s.loss_to_lease) : "—"}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 text-right">
                            <span className={s.delinquent_count > 0 ? "text-red-400" : "text-zinc-500"}>
                              {s.delinquent_count || "—"}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 text-right">
                            <span className={s.vacant > 0 ? "text-red-400" : "text-zinc-500"}>
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
      </div>
    </div>
  );
}
