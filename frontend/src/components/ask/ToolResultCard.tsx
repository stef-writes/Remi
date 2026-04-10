"use client";

import Link from "next/link";
import { fmt$, pct, fmtDate } from "@/lib/format";
import type { ToolCall } from "@/lib/types";
import { TimeSeriesChart } from "@/components/ui/TimeSeriesChart";

function MiniBar({ value, max, color }: { value: number; max: number; color: string }) {
  const w = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div className="flex-1 h-1 rounded-full bg-border overflow-hidden">
      <div className={`h-full rounded-full transition-all duration-700 ${color}`} style={{ width: `${w}%` }} />
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "active" || status === "occupied" ? "bg-ok"
    : status === "vacant" ? "bg-error"
    : status === "expiring" ? "bg-warn"
    : "bg-fg-faint";
  return <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${color}`} />;
}

// ---------------------------------------------------------------------------
// Schema-specific card components
// ---------------------------------------------------------------------------

function ManagersListCard({ data }: { data: unknown }) {
  const items = Array.isArray(data) ? data : (data as Record<string, unknown>)?.managers ?? (data as Record<string, unknown>)?.data ?? [];
  const rows = Array.isArray(items) ? items.slice(0, 6) : [];
  if (!rows.length) return null;

  return (
    <div className="mt-2 rounded-xl border border-border bg-surface-raised overflow-hidden">
      <div className="px-3 py-2 border-b border-border-subtle">
        <p className="text-[10px] font-semibold text-fg-muted uppercase tracking-widest">
          {rows.length} managers
        </p>
      </div>
      <div className="divide-y divide-border-subtle">
        {rows.map((m: Record<string, unknown>, i: number) => {
          const metrics = (m.metrics as Record<string, number>) ?? {};
          const occ = metrics.occupancy_rate ?? 0;
          return (
            <Link
              key={String(m.id ?? i)}
              href={`/managers/${m.id}`}
              className="flex items-center gap-3 px-3 py-2 hover:bg-surface-sunken transition-colors group"
            >
              <span className="text-[10px] text-fg-faint w-4 shrink-0">{i + 1}</span>
              <span className="text-xs text-fg font-medium truncate flex-1 group-hover:text-accent transition-colors">
                {String(m.name ?? "—")}
              </span>
              <div className="flex items-center gap-2 shrink-0">
                <MiniBar
                  value={occ}
                  max={1}
                  color={occ >= 0.95 ? "bg-ok" : occ >= 0.9 ? "bg-warn" : "bg-error"}
                />
                <span className={`text-[10px] font-mono w-9 text-right ${occ < 0.9 ? "text-warn" : "text-fg-muted"}`}>
                  {pct(occ)}
                </span>
              </div>
              <span className="text-[10px] font-mono text-fg-muted w-16 text-right shrink-0">
                {fmt$(metrics.total_actual_rent ?? 0)}
              </span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

function ManagerReviewCard({ data }: { data: unknown }) {
  const d = data as Record<string, unknown> ?? {};
  const summary = (d.summary as Record<string, unknown>) ?? d;
  const metrics = (summary.metrics as Record<string, number>) ?? {};
  const name = String(summary.name ?? "Manager");
  const occ = metrics.occupancy_rate ?? 0;
  const revenue = metrics.total_actual_rent ?? 0;
  const delBal = Number(summary.total_delinquent_balance ?? 0);
  const propCount = Number(summary.property_count ?? metrics.properties ?? 0);
  const unitCount = Number(summary.total_units ?? metrics.total_units ?? 0);

  const delData = d.delinquency as Record<string, unknown> | undefined;
  const vacData = d.vacancies as Record<string, unknown> | undefined;
  const leaseData = d.lease_expirations as Record<string, unknown> | undefined;

  return (
    <div className="mt-2 rounded-xl border border-border bg-surface-raised overflow-hidden">
      <div className="px-3 py-2.5 border-b border-border-subtle flex items-center justify-between">
        <div>
          <p className="text-[10px] font-semibold text-fg-muted uppercase tracking-widest">Manager Review</p>
          <p className="text-sm font-medium text-fg mt-0.5">{name}</p>
        </div>
        <span className="text-[10px] text-fg-faint">{propCount} properties, {unitCount} units</span>
      </div>

      <div className="grid grid-cols-3 divide-x divide-border-subtle border-b border-border-subtle">
        <div className="px-3 py-2.5 text-center">
          <p className="text-[9px] text-fg-faint uppercase tracking-wider mb-0.5">Occupancy</p>
          <p className={`text-sm font-bold font-mono ${occ < 0.9 ? "text-warn-fg" : "text-fg"}`}>{pct(occ)}</p>
        </div>
        <div className="px-3 py-2.5 text-center">
          <p className="text-[9px] text-fg-faint uppercase tracking-wider mb-0.5">Revenue</p>
          <p className="text-sm font-bold font-mono text-fg">{fmt$(revenue)}</p>
        </div>
        <div className="px-3 py-2.5 text-center">
          <p className="text-[9px] text-fg-faint uppercase tracking-wider mb-0.5">Delinquent</p>
          <p className={`text-sm font-bold font-mono ${delBal > 0 ? "text-error-fg" : "text-fg"}`}>{fmt$(delBal)}</p>
        </div>
      </div>

      {(delData || vacData || leaseData) && (
        <div className="px-3 py-2 space-y-1">
          {delData && Number((delData as Record<string, unknown>).total_delinquent ?? 0) > 0 && (
            <p className="text-[11px] text-fg-secondary">
              <span className="text-error-fg font-medium">{String((delData as Record<string, unknown>).total_delinquent)}</span> delinquent tenants
            </p>
          )}
          {vacData && Number((vacData as Record<string, unknown>).total_vacant ?? 0) > 0 && (
            <p className="text-[11px] text-fg-secondary">
              <span className="text-warn-fg font-medium">{String((vacData as Record<string, unknown>).total_vacant)}</span> vacant units
            </p>
          )}
          {leaseData && Number((leaseData as Record<string, unknown>).total_expiring ?? 0) > 0 && (
            <p className="text-[11px] text-fg-secondary">
              <span className="text-fg font-medium">{String((leaseData as Record<string, unknown>).total_expiring)}</span> leases expiring
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function PropertiesCard({ data }: { data: unknown }) {
  const d = data as Record<string, unknown> ?? {};
  const items = Array.isArray(d.properties) ? d.properties : Array.isArray(data) ? data : [];
  const rows = items.slice(0, 6) as Record<string, unknown>[];
  if (!rows.length) return null;

  return (
    <div className="mt-2 rounded-xl border border-border bg-surface-raised overflow-hidden">
      <div className="px-3 py-2 border-b border-border-subtle">
        <p className="text-[10px] font-semibold text-fg-muted uppercase tracking-widest">
          {items.length} properties
        </p>
      </div>
      <div className="divide-y divide-border-subtle">
        {rows.map((p, i) => {
          const units = Number(p.total_units ?? p.unit_count ?? 0);
          const addr = p.address as Record<string, unknown> | undefined;
          const city = addr ? `${addr.city ?? ""}, ${addr.state ?? ""}` : "";
          return (
            <Link
              key={String(p.id ?? i)}
              href={`/properties/${p.id}`}
              className="flex items-center gap-3 px-3 py-2 hover:bg-surface-sunken transition-colors group"
            >
              <span className="text-xs text-fg font-medium truncate flex-1 group-hover:text-accent transition-colors">
                {String(p.name ?? "—")}
              </span>
              {city && <span className="text-[10px] text-fg-faint truncate max-w-[120px]">{city}</span>}
              <span className="text-[10px] font-mono text-fg-muted shrink-0">{units} units</span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

function RentRollCard({ data }: { data: unknown }) {
  const d = data as Record<string, unknown> ?? {};
  const propertyName = String(d.property_name ?? d.name ?? "Property");
  const units = Array.isArray(d.units) ? d.units : [];
  const totals = (d.totals as Record<string, number>) ?? {};
  const rows = units.slice(0, 8) as Record<string, unknown>[];

  return (
    <div className="mt-2 rounded-xl border border-border bg-surface-raised overflow-hidden">
      <div className="px-3 py-2.5 border-b border-border-subtle flex items-center justify-between">
        <div>
          <p className="text-[10px] font-semibold text-fg-muted uppercase tracking-widest">Rent Roll</p>
          <p className="text-sm font-medium text-fg mt-0.5">{propertyName}</p>
        </div>
        <span className="text-[10px] text-fg-faint">{units.length} units</span>
      </div>

      {(totals.total_rent || totals.total_actual) && (
        <div className="grid grid-cols-3 divide-x divide-border-subtle border-b border-border-subtle">
          <div className="px-3 py-2 text-center">
            <p className="text-[9px] text-fg-faint uppercase tracking-wider mb-0.5">Scheduled</p>
            <p className="text-xs font-bold font-mono text-fg">{fmt$(totals.total_rent ?? 0)}</p>
          </div>
          <div className="px-3 py-2 text-center">
            <p className="text-[9px] text-fg-faint uppercase tracking-wider mb-0.5">Actual</p>
            <p className="text-xs font-bold font-mono text-fg">{fmt$(totals.total_actual ?? 0)}</p>
          </div>
          <div className="px-3 py-2 text-center">
            <p className="text-[9px] text-fg-faint uppercase tracking-wider mb-0.5">Occupancy</p>
            <p className="text-xs font-bold font-mono text-fg">{pct(totals.occupancy_rate ?? 0)}</p>
          </div>
        </div>
      )}

      {rows.length > 0 && (
        <div className="divide-y divide-border-subtle">
          {rows.map((u, i) => (
            <div key={i} className="flex items-center gap-2 px-3 py-1.5">
              <StatusDot status={String(u.status ?? "")} />
              <span className="text-[11px] text-fg font-medium w-12 shrink-0 truncate">
                {String(u.unit_number ?? u.unit ?? "—")}
              </span>
              <span className="text-[11px] text-fg-secondary truncate flex-1">
                {String(u.tenant_name ?? u.tenant ?? "Vacant")}
              </span>
              <span className="text-[10px] font-mono text-fg-muted shrink-0">
                {fmt$(Number(u.rent ?? u.monthly_rent ?? 0))}
              </span>
            </div>
          ))}
          {units.length > rows.length && (
            <div className="px-3 py-1.5 text-center">
              <span className="text-[10px] text-fg-faint">+{units.length - rows.length} more units</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ExpiringLeasesCard({ data }: { data: unknown }) {
  const d = data as Record<string, unknown> ?? {};
  const leases = Array.isArray(d.leases) ? d.leases : Array.isArray(d.items) ? d.items : [];
  const total = Number(d.total_expiring ?? d.total ?? leases.length);
  const rows = leases.slice(0, 5) as Record<string, unknown>[];
  if (!rows.length && !total) return null;

  return (
    <div className="mt-2 rounded-xl border border-warn/20 bg-warn-soft overflow-hidden">
      <div className="px-3 py-2 flex items-center justify-between border-b border-warn/10">
        <p className="text-[10px] font-semibold text-fg-muted uppercase tracking-widest">Expiring Leases</p>
        <span className="text-[10px] text-fg-faint">{total} total</span>
      </div>
      <div className="divide-y divide-warn/10">
        {rows.map((l, i) => (
          <div key={i} className="flex items-center gap-2 px-3 py-1.5">
            <span className="text-[11px] text-fg-secondary truncate flex-1">
              {String(l.tenant_name ?? l.tenant ?? "—")}
            </span>
            <span className="text-[10px] text-fg-faint truncate max-w-[120px]">
              {String(l.property_name ?? l.property ?? "")}
            </span>
            {l.end_date ? (
              <span className="text-[10px] font-mono text-warn-fg shrink-0">{fmtDate(String(l.end_date))}</span>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function VacanciesCard({ data }: { data: unknown }) {
  const d = data as Record<string, unknown> ?? {};
  const units = Array.isArray(d.units) ? d.units : Array.isArray(d.vacancies) ? d.vacancies : [];
  const total = Number(d.total_vacant ?? d.total ?? units.length);
  const rows = units.slice(0, 5) as Record<string, unknown>[];
  if (!rows.length && !total) return null;

  return (
    <div className="mt-2 rounded-xl border border-error/20 bg-error-soft overflow-hidden">
      <div className="px-3 py-2 flex items-center justify-between border-b border-error/10">
        <p className="text-[10px] font-semibold text-fg-muted uppercase tracking-widest">Vacant Units</p>
        <span className="text-[10px] text-fg-faint">{total} vacant</span>
      </div>
      <div className="divide-y divide-error/10">
        {rows.map((u, i) => {
          const days = Number(u.days_vacant ?? 0);
          return (
            <div key={i} className="flex items-center gap-2 px-3 py-1.5">
              <span className="text-[11px] text-fg font-medium w-12 shrink-0 truncate">
                {String(u.unit_number ?? u.unit ?? "—")}
              </span>
              <span className="text-[11px] text-fg-secondary truncate flex-1">
                {String(u.property_name ?? u.property ?? "")}
              </span>
              {days > 0 && (
                <span className={`text-[10px] font-mono shrink-0 ${days > 30 ? "text-error-fg" : "text-fg-muted"}`}>
                  {days}d vacant
                </span>
              )}
              <span className="text-[10px] font-mono text-fg-muted shrink-0">
                {fmt$(Number(u.market_rent ?? u.rent ?? 0))}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function MaintenanceCard({ data }: { data: unknown }) {
  const d = data as Record<string, unknown> ?? {};
  const items = Array.isArray(d.items) ? d.items : Array.isArray(d.requests) ? d.requests : [];
  const total = Number(d.total ?? items.length);
  const rows = items.slice(0, 5) as Record<string, unknown>[];
  if (!rows.length && !total) return null;

  const priorityColor = (p: string) =>
    p === "emergency" ? "text-error-fg" : p === "urgent" ? "text-warn-fg" : "text-fg-faint";

  return (
    <div className="mt-2 rounded-xl border border-border bg-surface-raised overflow-hidden">
      <div className="px-3 py-2 flex items-center justify-between border-b border-border-subtle">
        <p className="text-[10px] font-semibold text-fg-muted uppercase tracking-widest">Maintenance</p>
        <span className="text-[10px] text-fg-faint">{total} requests</span>
      </div>
      <div className="divide-y divide-border-subtle">
        {rows.map((r, i) => (
          <div key={i} className="flex items-center gap-2 px-3 py-1.5">
            <span className={`text-[9px] font-semibold uppercase tracking-wider w-14 shrink-0 ${priorityColor(String(r.priority ?? ""))}`}>
              {String(r.priority ?? r.status ?? "—")}
            </span>
            <span className="text-[11px] text-fg-secondary truncate flex-1">
              {String(r.description ?? r.title ?? "—")}
            </span>
            <span className="text-[10px] text-fg-faint truncate max-w-[100px]">
              {String(r.property_name ?? r.property ?? "")}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function DelinquencyCard({ data }: { data: unknown }) {
  const d = data as Record<string, unknown> ?? {};
  const inner = (d.data as Record<string, unknown>) ?? d;
  const total = Number(inner.total_delinquent ?? inner.total ?? 0);
  const balance = Number(inner.total_balance ?? inner.total_delinquent_balance ?? 0);
  const tenants = Array.isArray(inner.tenants) ? inner.tenants : [];
  if (!total && !balance) return null;

  return (
    <div className="mt-2 rounded-xl border border-error/20 bg-error-soft overflow-hidden">
      <div className="px-3 py-2 flex items-center justify-between border-b border-error/10">
        <p className="text-[10px] font-semibold text-fg-muted uppercase tracking-widest">Delinquency</p>
        <span className="text-[10px] text-fg-faint">{total} tenants</span>
      </div>
      <div className="px-3 py-2 flex items-baseline gap-2">
        <span className="text-xl font-bold font-mono text-error-fg">{fmt$(balance)}</span>
        <span className="text-[11px] text-fg-faint">outstanding</span>
      </div>
      {tenants.slice(0, 3).map((t: Record<string, unknown>, i: number) => (
        <div key={i} className="px-3 py-1.5 border-t border-error/10 flex items-center justify-between">
          <span className="text-[11px] text-fg-secondary truncate max-w-[55%]">
            {String(t.tenant_name ?? t.name ?? "—")}
          </span>
          <span className="text-[11px] font-mono text-error-fg">
            {fmt$(Number(t.total_balance ?? t.balance ?? 0))}
          </span>
        </div>
      ))}
    </div>
  );
}

function DashboardCard({ data }: { data: unknown }) {
  const d = data as Record<string, unknown> ?? {};
  const inner = (d.data as Record<string, unknown>) ?? d;
  const totalUnits = Number(inner.total_units ?? 0);
  const occupancy = Number(inner.occupancy_rate ?? 0);
  const revenue = Number(inner.total_monthly_rent ?? 0);
  const props = Number(inner.total_properties ?? 0);
  if (!totalUnits && !revenue) return null;

  const stats = [
    { label: "Properties", value: String(props) },
    { label: "Units", value: String(totalUnits) },
    { label: "Occupancy", value: pct(occupancy), alert: occupancy < 0.9 },
    { label: "Revenue", value: fmt$(revenue) },
  ];

  return (
    <div className="mt-2 rounded-xl border border-border bg-surface-raised overflow-hidden">
      <div className="px-3 py-2 border-b border-border-subtle">
        <p className="text-[10px] font-semibold text-fg-muted uppercase tracking-widest">Dashboard</p>
      </div>
      <div className="grid grid-cols-4 divide-x divide-border-subtle">
        {stats.map((s) => (
          <div key={s.label} className="px-3 py-2.5 text-center">
            <p className="text-[9px] text-fg-faint uppercase tracking-wider mb-0.5">{s.label}</p>
            <p className={`text-sm font-bold font-mono ${s.alert ? "text-warn-fg" : "text-fg"}`}>{s.value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function TrendsCard({ data }: { data: unknown }) {
  const d = data as Record<string, unknown>;
  const direction = String(d.direction ?? "stable");
  const periods = Array.isArray(d.periods) ? (d.periods as Record<string, unknown>[]) : [];
  if (!periods.length) return null;

  const sample = periods[0];

  type SeriesCfg = { dataKey: string; color: string; label: string; type?: "area" | "line" };
  let chartData: Record<string, unknown>[];
  let series: SeriesCfg[];
  let title: string;
  let yTickFormatter: ((v: number) => string) | undefined;

  if ("total_balance" in sample) {
    title = "Delinquency Trend";
    chartData = periods.map((p) => ({ period: String(p.period), balance: Number(p.total_balance) }));
    series = [{ dataKey: "balance", color: "var(--color-error)", label: "Balance" }];
    yTickFormatter = (v) => `$${(v / 1000).toFixed(0)}k`;
  } else if ("occupancy_rate" in sample) {
    title = "Occupancy Trend";
    chartData = periods.map((p) => ({ period: String(p.period), rate: Number(p.occupancy_rate) * 100 }));
    series = [{ dataKey: "rate", color: "var(--color-ok)", label: "Occupancy %" }];
    yTickFormatter = (v) => `${v.toFixed(0)}%`;
  } else if ("avg_rent" in sample) {
    title = "Rent Trend";
    chartData = periods.map((p) => ({ period: String(p.period), avg: Number(p.avg_rent) }));
    series = [{ dataKey: "avg", color: "var(--color-accent)", label: "Avg Rent" }];
    yTickFormatter = (v) => `$${v.toFixed(0)}`;
  } else if ("opened" in sample) {
    title = "Maintenance Trend";
    chartData = periods.map((p) => ({ period: String(p.period), opened: Number(p.opened), completed: Number(p.completed) }));
    series = [
      { dataKey: "opened", color: "var(--color-warn)", label: "Opened" },
      { dataKey: "completed", color: "var(--color-ok)", label: "Completed", type: "line" },
    ];
  } else {
    return null;
  }

  const dirColor =
    direction === "improving" ? "var(--color-ok)"
    : direction === "worsening" ? "var(--color-error)"
    : "var(--color-fg-faint)";

  return (
    <div className="mt-2">
      <TimeSeriesChart
        data={chartData}
        series={series}
        xKey="period"
        height={140}
        title={title}
        heroValue={direction}
        heroColor={dirColor}
        yTickFormatter={yTickFormatter}
        xTickFormatter={(v) => (v.length > 7 ? v.slice(0, 7) : v)}
      />
    </div>
  );
}

function LeasesListCard({ data }: { data: unknown }) {
  const d = (data as Record<string, unknown>) ?? {};
  const items = Array.isArray(d.leases)
    ? d.leases
    : Array.isArray(d.items)
      ? d.items
      : Array.isArray(data)
        ? data
        : [];
  const total = Number(d.total ?? items.length);
  const rows = (items as Record<string, unknown>[]).slice(0, 6);
  if (!rows.length) return null;

  return (
    <div className="mt-2 rounded-xl border border-border bg-surface-raised overflow-hidden">
      <div className="px-3 py-2 border-b border-border-subtle flex items-center justify-between">
        <p className="text-[10px] font-semibold text-fg-muted uppercase tracking-widest">Leases</p>
        <span className="text-[10px] text-fg-faint">{total} total</span>
      </div>
      <div className="divide-y divide-border-subtle">
        {rows.map((l, i) => (
          <div key={i} className="flex items-center gap-2 px-3 py-1.5">
            <StatusDot status={String(l.status ?? "active")} />
            <span className="text-[11px] text-fg-secondary truncate flex-1">
              {String(l.tenant_name ?? l.tenant ?? "—")}
            </span>
            <span className="text-[10px] text-fg-faint truncate max-w-[120px]">
              {String(l.property_name ?? l.unit_number ?? "")}
            </span>
            <span className="text-[10px] font-mono text-fg-muted shrink-0">
              {fmt$(Number(l.monthly_rent ?? l.rent ?? 0))}
            </span>
            {l.end_date != null && (
              <span className="text-[10px] font-mono text-fg-ghost shrink-0">
                {fmtDate(String(l.end_date))}
              </span>
            )}
          </div>
        ))}
        {total > rows.length && (
          <div className="px-3 py-1.5 text-center">
            <span className="text-[10px] text-fg-faint">+{total - rows.length} more</span>
          </div>
        )}
      </div>
    </div>
  );
}

function GenericResultPreview({ result }: { result: unknown }) {
  if (typeof result !== "string") return null;
  let parsed: Record<string, unknown> | null = null;
  try { parsed = JSON.parse(result); } catch { /* raw string */ }
  if (!parsed) return null;

  const inner = (parsed.data as Record<string, unknown>) ?? parsed;
  const scalars = Object.entries(inner)
    .filter(([, v]) => typeof v === "string" || typeof v === "number" || typeof v === "boolean")
    .slice(0, 6);
  if (!scalars.length) return null;

  return (
    <div className="mt-2 rounded-xl border border-border bg-surface-raised px-3 py-2 grid grid-cols-2 gap-x-6 gap-y-1">
      {scalars.map(([k, v]) => (
        <div key={k} className="flex items-center justify-between gap-2 py-0.5">
          <span className="text-[10px] text-fg-muted truncate">{k.replace(/_/g, " ")}</span>
          <span className="text-[10px] font-mono text-fg shrink-0">{String(v)}</span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Public component — rendered inline beneath a completed ToolCallRow
// ---------------------------------------------------------------------------

const SCHEMA_COMPONENTS: Record<string, React.ComponentType<{ data: unknown }>> = {
  managers_list: ManagersListCard,
  manager_rankings: ManagersListCard,
  manager_review: ManagerReviewCard,
  delinquency: DelinquencyCard,
  dashboard_overview: DashboardCard,
  properties_list: PropertiesCard,
  rent_roll: RentRollCard,
  expiring_leases: ExpiringLeasesCard,
  vacancies: VacanciesCard,
  maintenance_list: MaintenanceCard,
  leases_list: LeasesListCard,
  trends: TrendsCard,
};

export function ToolResultCard({ tc }: { tc: ToolCall }) {
  if (!tc.result_schema || tc.status !== "done" || !tc.result) return null;

  const Component = SCHEMA_COMPONENTS[tc.result_schema];
  if (Component) {
    return (
      <div className="anim-fade-up" style={{ animationDelay: "100ms" }}>
        <Component data={tc.result} />
      </div>
    );
  }

  return (
    <div className="anim-fade-up" style={{ animationDelay: "100ms" }}>
      <GenericResultPreview result={tc.result} />
    </div>
  );
}
