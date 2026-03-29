"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { MetricCard } from "@/components/ui/MetricCard";
import { Badge } from "@/components/ui/Badge";
import { ManagerFilter } from "@/components/ui/ManagerFilter";
import type { LeaseCalendar } from "@/lib/types";

function fmt$(n: number) {
  return "$" + n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

const WINDOWS = [30, 60, 90] as const;

export function LeasesView() {
  const [data, setData] = useState<LeaseCalendar | null>(null);
  const [days, setDays] = useState<number>(90);
  const [managerId, setManagerId] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.leasesExpiring(days, managerId || undefined));
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [days, managerId]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-6xl mx-auto px-8 py-8 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-zinc-100">Expiring Leases</h1>
            <p className="text-sm text-zinc-500 mt-1">
              Leases expiring within {days} days and month-to-month
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex rounded-lg border border-zinc-700 overflow-hidden">
              {WINDOWS.map((w) => (
                <button
                  key={w}
                  onClick={() => setDays(w)}
                  className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                    days === w
                      ? "bg-zinc-700 text-zinc-100"
                      : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800"
                  }`}
                >
                  {w}d
                </button>
              ))}
            </div>
            <ManagerFilter value={managerId} onChange={setManagerId} />
          </div>
        </div>

        {data && (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <MetricCard
              label="Expiring Leases"
              value={data.total_expiring}
              alert={data.total_expiring > 10}
            />
            <MetricCard
              label="Month-to-Month"
              value={data.month_to_month_count}
              alert={data.month_to_month_count > 0}
            />
            <MetricCard
              label="Total Monthly Rent"
              value={fmt$(data.leases.reduce((s, l) => s + l.monthly_rent, 0))}
              sub="at risk of turnover"
            />
          </div>
        )}

        {loading && (
          <div className="py-12 text-center text-sm text-zinc-600 animate-pulse">Loading...</div>
        )}

        {!loading && data && data.leases.length > 0 && (
          <div className="rounded-xl border border-zinc-800/60 bg-zinc-900/40 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-800/60">
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Tenant</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Property</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Unit</th>
                    <th className="text-right px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Rent</th>
                    <th className="text-right px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Market</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Expires</th>
                    <th className="text-right px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Days Left</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Type</th>
                  </tr>
                </thead>
                <tbody>
                  {data.leases.map((l) => {
                    const urgent = l.days_left <= 30 && !l.is_month_to_month;
                    return (
                      <tr key={l.lease_id} className="border-b border-zinc-800/30 hover:bg-zinc-800/20 transition-colors">
                        <td className="px-4 py-2.5 text-zinc-200 font-medium">{l.tenant_name}</td>
                        <td className="px-4 py-2.5 text-zinc-400 text-xs">{l.property_name}</td>
                        <td className="px-4 py-2.5 text-zinc-400 font-mono text-xs">{l.unit_number}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-zinc-300">{fmt$(l.monthly_rent)}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-zinc-500">{fmt$(l.market_rent)}</td>
                        <td className="px-4 py-2.5 text-zinc-400 text-xs">{l.end_date}</td>
                        <td className={`px-4 py-2.5 text-right font-mono ${urgent ? "text-red-400 font-semibold" : "text-zinc-400"}`}>
                          {l.days_left}
                        </td>
                        <td className="px-4 py-2.5">
                          {l.is_month_to_month ? (
                            <Badge variant="amber">MTM</Badge>
                          ) : l.days_left <= 30 ? (
                            <Badge variant="red">Urgent</Badge>
                          ) : (
                            <Badge variant="default">Fixed</Badge>
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

        {!loading && data && data.leases.length === 0 && (
          <div className="py-12 text-center text-sm text-zinc-600">
            No expiring leases in the next {days} days
          </div>
        )}
      </div>
    </div>
  );
}
