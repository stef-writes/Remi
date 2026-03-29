"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { MetricCard } from "@/components/ui/MetricCard";
import { Badge } from "@/components/ui/Badge";
import { ManagerFilter } from "@/components/ui/ManagerFilter";
import type { VacancyTracker } from "@/lib/types";

function fmt$(n: number) {
  return "$" + n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

export function VacanciesView() {
  const [data, setData] = useState<VacancyTracker | null>(null);
  const [managerId, setManagerId] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.vacancyTracker(managerId || undefined));
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [managerId]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-6xl mx-auto px-8 py-8 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-zinc-100">Vacancies</h1>
            <p className="text-sm text-zinc-500 mt-1">
              Vacant and notice units across the portfolio
            </p>
          </div>
          <ManagerFilter value={managerId} onChange={setManagerId} />
        </div>

        {data && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricCard
              label="Vacant Units"
              value={data.total_vacant}
              alert={data.total_vacant > 0}
            />
            <MetricCard
              label="Notice Units"
              value={data.total_notice}
              alert={data.total_notice > 0}
            />
            <MetricCard
              label="Revenue at Risk"
              value={fmt$(data.total_market_rent_at_risk)}
              sub="monthly market rent"
              alert={data.total_market_rent_at_risk > 0}
            />
            <MetricCard
              label="Avg Days Vacant"
              value={data.avg_days_vacant != null ? String(data.avg_days_vacant) : "—"}
            />
          </div>
        )}

        {loading && (
          <div className="py-12 text-center text-sm text-zinc-600 animate-pulse">Loading...</div>
        )}

        {!loading && data && data.units.length > 0 && (
          <div className="rounded-xl border border-zinc-800/60 bg-zinc-900/40 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-800/60">
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Property</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Unit</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Status</th>
                    <th className="text-right px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Days Vacant</th>
                    <th className="text-right px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Market Rent</th>
                    <th className="text-center px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Website</th>
                    <th className="text-center px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Internet</th>
                  </tr>
                </thead>
                <tbody>
                  {data.units.map((u) => {
                    const isNotice = u.occupancy_status?.includes("notice");
                    return (
                      <tr key={u.unit_id} className="border-b border-zinc-800/30 hover:bg-zinc-800/20 transition-colors">
                        <td className="px-4 py-2.5 text-zinc-200">{u.property_name}</td>
                        <td className="px-4 py-2.5 text-zinc-400 font-mono text-xs">{u.unit_number}</td>
                        <td className="px-4 py-2.5">
                          <Badge variant={isNotice ? "amber" : "red"}>
                            {u.occupancy_status?.replace(/_/g, " ") ?? "vacant"}
                          </Badge>
                        </td>
                        <td className={`px-4 py-2.5 text-right font-mono ${(u.days_vacant ?? 0) > 30 ? "text-red-400" : "text-zinc-400"}`}>
                          {u.days_vacant ?? "—"}
                        </td>
                        <td className="px-4 py-2.5 text-right font-mono text-zinc-300">{fmt$(u.market_rent)}</td>
                        <td className="px-4 py-2.5 text-center">
                          {u.listed_on_website ? (
                            <span className="text-emerald-400 text-xs">Yes</span>
                          ) : (
                            <span className="text-red-400 text-xs">No</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-center">
                          {u.listed_on_internet ? (
                            <span className="text-emerald-400 text-xs">Yes</span>
                          ) : (
                            <span className="text-red-400 text-xs">No</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {!loading && data && data.units.length === 0 && (
          <div className="py-12 text-center text-sm text-zinc-600">
            No vacant units found
          </div>
        )}
      </div>
    </div>
  );
}
