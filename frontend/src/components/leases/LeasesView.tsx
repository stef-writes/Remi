"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { fmt$ } from "@/lib/format";
import { MetricCard } from "@/components/ui/MetricCard";
import { MetricStrip } from "@/components/ui/MetricStrip";
import { PageContainer } from "@/components/ui/PageContainer";
import { Badge } from "@/components/ui/Badge";
import { ManagerFilter } from "@/components/ui/ManagerFilter";
import { useApiQuery } from "@/hooks/useApiQuery";
import type { LeaseCalendar } from "@/lib/types";

const WINDOWS = [30, 60, 90] as const;

export function LeasesView() {
  const [days, setDays] = useState<number>(90);
  const [managerId, setManagerId] = useState("");
  const { data, loading } = useApiQuery<LeaseCalendar>(
    () => api.leasesExpiring(days, managerId || undefined),
    [days, managerId]
  );

  return (
    <PageContainer>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-fg">Expiring Leases</h1>
            <p className="text-sm text-fg-muted mt-1">
              Leases expiring within {days} days and month-to-month
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex rounded-lg border border-border overflow-hidden">
              {WINDOWS.map((w) => (
                <button
                  key={w}
                  onClick={() => setDays(w)}
                  className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                    days === w
                      ? "bg-accent text-accent-fg"
                      : "text-fg-muted hover:text-fg-secondary hover:bg-surface-sunken"
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
          <MetricStrip className="lg:grid-cols-3">
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
          </MetricStrip>
        )}

        {loading && (
          <div className="py-12 text-center text-sm text-fg-faint animate-pulse">Loading...</div>
        )}

        {!loading && data && data.leases.length > 0 && (
          <div className="rounded-xl border border-border bg-surface overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">Tenant</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">Property</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">Unit</th>
                    <th className="text-right px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">Rent</th>
                    <th className="text-right px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">Market</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">Expires</th>
                    <th className="text-right px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">Days Left</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">Type</th>
                  </tr>
                </thead>
                <tbody>
                  {data.leases.map((l) => {
                    const urgent = l.days_left <= 30 && !l.is_month_to_month;
                    return (
                      <tr key={l.lease_id} className="border-b border-border-subtle hover:bg-surface-raised transition-colors">
                        <td className="px-4 py-2.5 text-fg font-medium">{l.tenant_name}</td>
                        <td className="px-4 py-2.5 text-fg-secondary text-xs">{l.property_name}</td>
                        <td className="px-4 py-2.5 text-fg-secondary font-mono text-xs">{l.unit_number}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-fg-secondary">{fmt$(l.monthly_rent)}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-fg-muted">{fmt$(l.market_rent)}</td>
                        <td className="px-4 py-2.5 text-fg-secondary text-xs">{l.end_date}</td>
                        <td className={`px-4 py-2.5 text-right font-mono ${urgent ? "text-error font-semibold" : "text-fg-secondary"}`}>
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
          <div className="py-12 text-center text-sm text-fg-faint">
            No expiring leases in the next {days} days
          </div>
        )}
    </PageContainer>
  );
}
