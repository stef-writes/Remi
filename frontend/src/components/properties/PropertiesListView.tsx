"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { fmt$ } from "@/lib/format";
import { useApiQuery } from "@/hooks/useApiQuery";
import { PageContainer } from "@/components/ui/PageContainer";
import { PropertyHealthCard, type PropertyHealth } from "@/components/ui/PropertyHealthCard";
import { ManagerFilter } from "@/components/ui/ManagerFilter";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { HealthRing } from "@/components/ui/HealthRing";
import type { DashboardOverview } from "@/lib/types";

type SortKey = "occupancy" | "revenue" | "name" | "ltl" | "maintenance";

export function PropertiesListView() {
  const [managerId, setManagerId] = useState("");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortKey>("occupancy");

  const { data, loading, error, refetch } = useApiQuery<DashboardOverview>(
    () => api.dashboardOverview(managerId ? { manager_id: managerId } : undefined),
    ["properties_list", managerId],
  );

  const allProperties: PropertyHealth[] = (data?.properties ?? []).map((p) => ({
    id: p.property_id,
    name: p.property_name,
    total_units: p.total_units,
    occupied: p.occupied,
    occupancy_rate: p.occupancy_rate,
    monthly_actual: p.monthly_rent,
    loss_to_lease: p.loss_to_lease,
    open_maintenance: p.open_maintenance,
    manager_name: p.manager_name ?? undefined,
  }));

  const filtered = [...allProperties]
    .filter((p) =>
      !search ||
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      p.manager_name?.toLowerCase().includes(search.toLowerCase()),
    )
    .sort((a, b) => {
      switch (sort) {
        case "occupancy": return b.occupancy_rate - a.occupancy_rate;
        case "revenue": return b.monthly_actual - a.monthly_actual;
        case "name": return a.name.localeCompare(b.name);
        case "ltl": return (b.loss_to_lease ?? 0) - (a.loss_to_lease ?? 0);
        case "maintenance": return (b.open_maintenance ?? 0) - (a.open_maintenance ?? 0);
        default: return 0;
      }
    });

  const SORT_OPTIONS: { key: SortKey; label: string }[] = [
    { key: "occupancy", label: "Occupancy" },
    { key: "ltl", label: "LTL" },
    { key: "maintenance", label: "Maintenance" },
    { key: "revenue", label: "Revenue" },
    { key: "name", label: "Name" },
  ];

  return (
    <PageContainer wide>
      {/* Header */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h1 className="text-lg font-semibold text-fg">Properties</h1>
        <ManagerFilter value={managerId} onChange={setManagerId} />
      </div>

      <ErrorBanner error={error} onRetry={refetch} />

      {/* Portfolio summary — use API-computed values, never recalculate */}
      {!loading && data && allProperties.length > 0 && (
        <div className="flex items-center gap-8 px-1">
          <HealthRing rate={data.occupancy_rate} size={96} label="occupied" />
          <div className="space-y-2">
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold text-fg font-mono">{fmt$(data.total_monthly_rent)}</span>
              <span className="text-xs text-fg-faint">/mo · {allProperties.length} properties</span>
            </div>
            <div className="flex flex-wrap gap-x-5 gap-y-1 text-[11px]">
              <span className="text-fg-muted">
                <span className="text-fg font-semibold">{data.occupied}/{data.total_units}</span> units occupied
              </span>
              <span className="text-fg-muted">
                <span className="text-fg font-semibold">{data.total_managers}</span> managers
              </span>
              {data.total_loss_to_lease > 0 && (
                <span className="text-warn font-mono">{fmt$(data.total_loss_to_lease)} LTL</span>
              )}
              {data.vacant > 0 && (
                <span className="text-error font-semibold">{data.vacant} vacant</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Controls */}
      {!loading && allProperties.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search properties or managers..."
            className="min-w-[180px] max-w-xs bg-surface border border-border rounded-lg px-3 py-1.5 text-xs text-fg placeholder:text-fg-faint focus:outline-none focus:border-accent"
          />
          <div className="flex rounded-lg border border-border overflow-hidden text-[10px]">
            {SORT_OPTIONS.map((o) => (
              <button
                key={o.key}
                onClick={() => setSort(o.key)}
                className={`px-2.5 py-1.5 transition-colors ${sort === o.key ? "bg-accent text-accent-fg" : "text-fg-muted hover:bg-surface-raised"}`}
              >
                {o.label}
              </button>
            ))}
          </div>
          {search && (
            <span className="text-[10px] text-fg-faint">
              {filtered.length} result{filtered.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="rounded-2xl border border-border bg-surface h-36 number-shimmer" />
          ))}
        </div>
      )}

      {/* Empty — show structural skeleton */}
      {!loading && allProperties.length === 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="rounded-2xl border border-dashed border-border bg-surface/50 h-36 flex items-center justify-center">
              <span className="text-xs text-fg-ghost">Property {i + 1}</span>
            </div>
          ))}
        </div>
      )}

      {!loading && filtered.length === 0 && search && (
        <p className="py-12 text-center text-sm text-fg-faint">
          No properties matching &ldquo;{search}&rdquo;
        </p>
      )}

      {/* Properties — sorted, no artificial urgent/healthy split */}
      {!loading && filtered.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((p) => (
            <PropertyHealthCard key={p.id} property={p} />
          ))}
        </div>
      )}
    </PageContainer>
  );
}
