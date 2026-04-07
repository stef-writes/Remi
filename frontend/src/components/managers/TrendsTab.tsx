"use client";

import { api } from "@/lib/api";
import { fmt$, pct } from "@/lib/format";
import { useApiQuery } from "@/hooks/useApiQuery";
import { SparklineChart } from "@/components/ui/SparklineChart";
import { TimeSeriesChart } from "@/components/ui/TimeSeriesChart";
import type {
  DelinquencyTrend,
  OccupancyTrend,
  RentTrend,
} from "@/lib/types";

function directionLabel(d: string): string {
  if (d === "improving") return "Improving";
  if (d === "worsening") return "Worsening";
  if (d === "stable") return "Stable";
  return "Not enough data";
}

function directionColor(d: string): string {
  if (d === "improving") return "var(--color-ok)";
  if (d === "worsening") return "var(--color-error)";
  return "var(--color-fg-ghost)";
}

function periodLabel(p: string): string {
  const [y, m] = p.split("-");
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[parseInt(m, 10) - 1]} ${y.slice(2)}`;
}

export function TrendsTab({ managerId }: { managerId: string }) {
  const { data, loading } = useApiQuery(async () => {
    const scope = { manager_id: managerId };
    const [delinquency, occupancy, rent] = await Promise.all([
      api.delinquencyTrend(scope).catch(() => null),
      api.occupancyTrend(scope).catch(() => null),
      api.rentTrend(scope).catch(() => null),
    ]);
    return {
      delinquency: delinquency as DelinquencyTrend | null,
      occupancy: occupancy as OccupancyTrend | null,
      rent: rent as RentTrend | null,
    };
  }, [managerId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <p className="text-sm text-fg-faint animate-pulse">Loading trends...</p>
      </div>
    );
  }

  const delinquency = data?.delinquency;
  const occupancy = data?.occupancy;
  const rent = data?.rent;

  const noData = !delinquency?.periods.length && !occupancy?.periods.length && !rent?.periods.length;

  if (noData) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-2">
        <p className="text-sm text-fg-muted">No trend data yet</p>
        <p className="text-xs text-fg-faint">Upload multiple reports over time to see trends appear here.</p>
      </div>
    );
  }

  const deliqData = (delinquency?.periods ?? []).map((p) => ({
    period: periodLabel(p.period),
    total_balance: p.total_balance,
    tenant_count: p.tenant_count,
    avg_balance: p.avg_balance,
  }));

  const occData = (occupancy?.periods ?? []).map((p) => ({
    period: periodLabel(p.period),
    occupancy_rate: p.occupancy_rate * 100,
    occupied: p.occupied,
    vacant: p.vacant,
  }));

  const rentData = (rent?.periods ?? []).map((p) => ({
    period: periodLabel(p.period),
    avg_rent: p.avg_rent,
    total_rent: p.total_rent,
    median_rent: p.median_rent,
  }));

  const latestDeliq = delinquency?.periods.at(-1);
  const latestOcc = occupancy?.periods.at(-1);
  const latestRent = rent?.periods.at(-1);

  return (
    <div className="space-y-6">
      {/* Sparkline overview strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {delinquency && delinquency.periods.length > 0 && (
          <SparklineChart
            data={deliqData}
            dataKey="total_balance"
            color="var(--color-error)"
            label="Delinquency"
            value={latestDeliq ? fmt$(latestDeliq.total_balance) : "$0"}
            valueFormatter={(v) => fmt$(v)}
            invertTrend
          />
        )}
        {occupancy && occupancy.periods.length > 0 && (
          <SparklineChart
            data={occData}
            dataKey="occupancy_rate"
            color="var(--color-ok)"
            label="Occupancy"
            value={latestOcc ? pct(latestOcc.occupancy_rate) : "—"}
            valueFormatter={(v) => `${v.toFixed(1)}%`}
          />
        )}
        {rent && rent.periods.length > 0 && (
          <SparklineChart
            data={rentData}
            dataKey="avg_rent"
            color="var(--color-accent)"
            label="Avg Rent"
            value={latestRent ? fmt$(latestRent.avg_rent) : "—"}
            valueFormatter={(v) => fmt$(v)}
          />
        )}
      </div>

      {/* Detailed delinquency chart */}
      {delinquency && deliqData.length >= 2 && (
        <TimeSeriesChart
          data={deliqData}
          xKey="period"
          title="Delinquency Over Time"
          heroValue={latestDeliq ? fmt$(latestDeliq.total_balance) : undefined}
          heroColor="var(--color-error)"
          summary={`${directionLabel(delinquency.direction)} · ${delinquency.period_count} months of data`}
          summaryColor={directionColor(delinquency.direction)}
          series={[
            { dataKey: "total_balance", color: "var(--color-error)", label: "Total Balance" },
            { dataKey: "avg_balance", color: "var(--color-warn)", label: "Avg per Tenant", type: "line" },
          ]}
          yTickFormatter={(v) => fmt$(v)}
          xTickFormatter={(v) => v}
          height={240}
        />
      )}

      {/* Detailed occupancy chart */}
      {occupancy && occData.length >= 2 && (
        <TimeSeriesChart
          data={occData}
          xKey="period"
          title="Occupancy Over Time"
          heroValue={latestOcc ? pct(latestOcc.occupancy_rate) : undefined}
          heroColor="var(--color-ok)"
          summary={`${directionLabel(occupancy.direction)} · ${occupancy.period_count} months`}
          summaryColor={directionColor(occupancy.direction)}
          series={[
            { dataKey: "occupancy_rate", color: "var(--color-ok)", label: "Occupancy %" },
          ]}
          yDomain={[0, 100]}
          yTickFormatter={(v) => `${v}%`}
          xTickFormatter={(v) => v}
          referenceLines={[{ y: 95, label: "Target 95%", color: "var(--color-fg-ghost)", dashed: true }]}
          height={240}
        />
      )}

      {/* Detailed rent chart */}
      {rent && rentData.length >= 2 && (
        <TimeSeriesChart
          data={rentData}
          xKey="period"
          title="Average Rent Over Time"
          heroValue={latestRent ? fmt$(latestRent.avg_rent) : undefined}
          heroColor="var(--color-accent)"
          summary={`${directionLabel(rent.direction)} · ${rent.period_count} months`}
          summaryColor={directionColor(rent.direction)}
          series={[
            { dataKey: "avg_rent", color: "var(--color-accent)", label: "Avg Rent" },
            { dataKey: "median_rent", color: "var(--color-fg-muted)", label: "Median Rent", type: "line" },
          ]}
          yTickFormatter={(v) => fmt$(v)}
          xTickFormatter={(v) => v}
          height={240}
        />
      )}
    </div>
  );
}
