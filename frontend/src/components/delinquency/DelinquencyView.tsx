"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { MetricCard } from "@/components/ui/MetricCard";
import { Badge } from "@/components/ui/Badge";
import { ManagerFilter } from "@/components/ui/ManagerFilter";
import type { DelinquencyBoard } from "@/lib/types";

function fmt$(n: number) {
  return "$" + n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

export function DelinquencyView() {
  const [data, setData] = useState<DelinquencyBoard | null>(null);
  const [managerId, setManagerId] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.delinquencyBoard(managerId || undefined));
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
            <h1 className="text-2xl font-bold text-zinc-100">Delinquency</h1>
            <p className="text-sm text-zinc-500 mt-1">
              Tenants with outstanding balances
            </p>
          </div>
          <ManagerFilter value={managerId} onChange={setManagerId} />
        </div>

        {data && (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <MetricCard
              label="Delinquent Tenants"
              value={data.total_delinquent}
              alert={data.total_delinquent > 0}
            />
            <MetricCard
              label="Total Owed"
              value={fmt$(data.total_balance)}
              alert={data.total_balance > 0}
            />
            <MetricCard
              label="Avg Balance"
              value={data.total_delinquent > 0 ? fmt$(data.total_balance / data.total_delinquent) : "$0"}
            />
          </div>
        )}

        {loading && (
          <div className="py-12 text-center text-sm text-zinc-600 animate-pulse">Loading...</div>
        )}

        {!loading && data && data.tenants.length > 0 && (
          <div className="rounded-xl border border-zinc-800/60 bg-zinc-900/40 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-800/60">
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Tenant</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Property</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Unit</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Status</th>
                    <th className="text-right px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Balance</th>
                    <th className="text-right px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">0-30</th>
                    <th className="text-right px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">30+</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Last Payment</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Tags</th>
                  </tr>
                </thead>
                <tbody>
                  {data.tenants.map((t) => (
                    <tr key={t.tenant_id} className="border-b border-zinc-800/30 hover:bg-zinc-800/20 transition-colors">
                      <td className="px-4 py-2.5 text-zinc-200 font-medium">{t.tenant_name}</td>
                      <td className="px-4 py-2.5 text-zinc-400 text-xs">{t.property_name || "—"}</td>
                      <td className="px-4 py-2.5 text-zinc-400 font-mono text-xs">{t.unit_number || "—"}</td>
                      <td className="px-4 py-2.5">
                        <Badge variant={t.status === "evict" ? "red" : t.status === "notice" ? "amber" : "default"}>
                          {t.status}
                        </Badge>
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-red-400">{fmt$(t.balance_owed)}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-zinc-400">{fmt$(t.balance_0_30)}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-amber-400">{fmt$(t.balance_30_plus)}</td>
                      <td className="px-4 py-2.5 text-zinc-500 text-xs">{t.last_payment_date ?? "—"}</td>
                      <td className="px-4 py-2.5">
                        <div className="flex flex-wrap gap-1">
                          {t.tags.map((tag) => (
                            <Badge key={tag} variant="blue">{tag}</Badge>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {!loading && data && data.tenants.length === 0 && (
          <div className="py-12 text-center text-sm text-zinc-600">
            No delinquent tenants found
          </div>
        )}
      </div>
    </div>
  );
}
