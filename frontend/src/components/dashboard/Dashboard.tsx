"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { fmt$, pct } from "@/lib/format";
import { useApiQuery } from "@/hooks/useApiQuery";
import { PageContainer } from "@/components/ui/PageContainer";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { EntityFormPanel, type FieldDef } from "@/components/ui/EntityFormPanel";
import { CommandTrigger } from "@/components/ui/CommandMenu";
import type {
  DashboardOverview,
  ManagerOverview,
  PropertyOverview,
  DelinquencyBoard,
  LeaseCalendar,
  VacancyTracker,
  NeedsManagerResponse,
} from "@/lib/types";

const MANAGER_FIELDS: FieldDef[] = [
  { name: "name", label: "Name", required: true, placeholder: "Jane Smith" },
  { name: "email", label: "Email", placeholder: "jane@example.com" },
  { name: "company", label: "Company", placeholder: "Acme Property Mgmt" },
  { name: "phone", label: "Phone", placeholder: "(555) 123-4567" },
];

function OccupancyRing({ rate, size = 140 }: { rate: number; size?: number }) {
  const stroke = 10;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const filled = circumference * rate;
  const color = rate >= 0.95 ? "stroke-ok" : rate >= 0.9 ? "stroke-warn" : "stroke-error";

  return (
    <div className="relative ring-pulse" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke="currentColor" strokeWidth={stroke}
          className="text-border-subtle"
        />
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none" strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={`${filled} ${circumference - filled}`}
          className={`${color} transition-all duration-1000`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold text-fg tracking-tight">{pct(rate)}</span>
        <span className="text-[9px] text-fg-faint uppercase tracking-widest">occupied</span>
      </div>
    </div>
  );
}

function AlertChip({
  href, count, label, sub, color, pulse,
}: {
  href: string; count: number; label: string; sub?: string;
  color: "error" | "warn" | "orange" | "sky" | "violet"; pulse?: boolean;
}) {
  const colors = {
    error: "border-error/20 bg-error-soft text-error hover:border-error/40 hover:shadow-[0_0_20px_-4px_rgba(201,92,92,0.15)]",
    warn: "border-warn/20 bg-warn-soft text-warn hover:border-warn/40 hover:shadow-[0_0_20px_-4px_rgba(212,151,78,0.15)]",
    orange: "border-orange-500/20 bg-orange-500/5 text-orange-400 hover:border-orange-500/40 hover:shadow-[0_0_20px_-4px_rgba(249,115,22,0.15)]",
    sky: "border-sky-500/20 bg-sky-500/5 text-sky-400 hover:border-sky-500/40 hover:shadow-[0_0_20px_-4px_rgba(14,165,233,0.15)]",
    violet: "border-violet-500/20 bg-violet-500/5 text-violet-400 hover:border-violet-500/40 hover:shadow-[0_0_20px_-4px_rgba(139,92,246,0.15)]",
  };

  return (
    <Link
      href={href}
      className={`flex-1 sm:flex-initial shrink-0 min-w-[140px] rounded-2xl border px-5 py-3.5 transition-all group card-hover ${colors[color]}`}
    >
      <div className="flex items-center gap-2">
        {pulse && (
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 bg-current" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-current" />
          </span>
        )}
        <span className="text-2xl font-bold leading-none tracking-tight">{count}</span>
      </div>
      <p className="text-[11px] opacity-80 mt-1 font-medium">{label}</p>
      {sub && <p className="text-[9px] opacity-50">{sub}</p>}
    </Link>
  );
}

function StatRow({ label, value, alert }: { label: string; value: string; alert?: boolean }) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-border-subtle last:border-0">
      <span className="text-xs text-fg-muted">{label}</span>
      <span className={`text-sm font-semibold font-mono tracking-tight ${alert ? "text-warn" : "text-fg"}`}>{value}</span>
    </div>
  );
}

function ManagerCard({ mgr, properties }: { mgr: ManagerOverview; properties: PropertyOverview[] }) {
  const m = mgr.metrics;
  const occColor = m.occupancy_rate >= 0.95 ? "text-ok" : m.occupancy_rate >= 0.9 ? "text-warn" : "text-error";

  return (
    <Link
      href={`/managers/${mgr.manager_id}`}
      className="rounded-2xl border border-border bg-surface p-5 card-hover group transition-all hover:border-accent/20"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-xl bg-accent/10 flex items-center justify-center shrink-0 group-hover:bg-accent/20 transition-colors">
            <span className="text-sm font-bold text-accent">{mgr.manager_name.charAt(0)}</span>
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-fg truncate group-hover:text-accent transition-colors">{mgr.manager_name}</p>
            <p className="text-[10px] text-fg-faint">{mgr.property_count} {mgr.property_count === 1 ? "property" : "properties"}</p>
          </div>
        </div>
        <svg className="w-4 h-4 text-fg-ghost group-hover:text-accent group-hover:translate-x-0.5 transition-all shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
        </svg>
      </div>

      <div className="grid grid-cols-3 gap-3 text-center">
        <div>
          <p className="text-lg font-bold text-fg tracking-tight">{m.total_units}</p>
          <p className="text-[9px] text-fg-faint uppercase tracking-widest">units</p>
        </div>
        <div>
          <p className={`text-lg font-bold tracking-tight ${occColor}`}>{pct(m.occupancy_rate)}</p>
          <p className="text-[9px] text-fg-faint uppercase tracking-widest">occupied</p>
        </div>
        <div>
          <p className="text-lg font-bold text-fg tracking-tight">{fmt$(m.total_actual_rent)}</p>
          <p className="text-[9px] text-fg-faint uppercase tracking-widest">rent</p>
        </div>
      </div>

      {(m.loss_to_lease > 0 || m.open_maintenance > 0 || m.expiring_leases_90d > 0) && (
        <div className="flex gap-3 mt-3 pt-3 border-t border-border-subtle flex-wrap">
          {m.loss_to_lease > 0 && (
            <span className="text-[10px] text-warn">{fmt$(m.loss_to_lease)} LTL</span>
          )}
          {m.open_maintenance > 0 && (
            <span className="text-[10px] text-sky-400">{m.open_maintenance} maint</span>
          )}
          {m.expiring_leases_90d > 0 && (
            <span className="text-[10px] text-fg-muted">{m.expiring_leases_90d} expiring</span>
          )}
        </div>
      )}
    </Link>
  );
}

function PropertyRow({ p }: { p: PropertyOverview }) {
  const occColor = p.occupancy_rate >= 0.95 ? "text-ok" : p.occupancy_rate >= 0.9 ? "text-warn" : "text-error";
  return (
    <Link
      href={`/properties/${p.property_id}`}
      className="grid grid-cols-[1fr_60px_70px_90px_80px] items-center gap-2 px-4 py-2.5 hover:bg-surface-sunken transition-colors group"
    >
      <div className="min-w-0">
        <p className="text-xs font-medium text-fg truncate group-hover:text-accent transition-colors">{p.property_name}</p>
      </div>
      <span className="text-[11px] font-mono text-fg text-right">{p.total_units} u</span>
      <span className={`text-[11px] font-mono text-right font-semibold ${occColor}`}>{pct(p.occupancy_rate)}</span>
      <span className="text-[11px] font-mono text-fg text-right">{fmt$(p.monthly_rent)}</span>
      <span className={`text-[11px] font-mono text-right ${p.loss_to_lease > 0 ? "text-warn" : "text-fg-faint"}`}>{p.loss_to_lease > 0 ? fmt$(p.loss_to_lease) : "—"}</span>
    </Link>
  );
}

function AssignDropdown({
  propertyId,
  managers,
  onAssigned,
}: {
  propertyId: string;
  managers: ManagerOverview[];
  onAssigned: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  async function handleSelect(managerId: string) {
    setSaving(true);
    try {
      await api.assignProperties(managerId, [propertyId]);
      onAssigned();
    } finally {
      setSaving(false);
      setOpen(false);
    }
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen(!open); }}
        disabled={saving}
        className="h-7 px-2.5 rounded-lg border border-dashed border-violet-500/30 bg-violet-500/5 text-[10px] font-medium text-violet-400 hover:bg-violet-500/10 hover:border-violet-500/50 transition-all flex items-center gap-1"
      >
        {saving ? "..." : "Assign"}
        <svg className="w-2.5 h-2.5 opacity-60" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" /></svg>
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 z-50 w-52 rounded-xl border border-border bg-surface shadow-xl shadow-black/20 overflow-hidden anim-scale-in">
          <div className="px-3 py-2 border-b border-border-subtle">
            <p className="text-[10px] font-semibold text-fg-muted uppercase tracking-widest">Assign to</p>
          </div>
          <div className="max-h-48 overflow-y-auto">
            {managers.length === 0 ? (
              <div className="px-3 py-3 text-center text-[10px] text-fg-faint">No managers yet</div>
            ) : (
              managers.map((m) => (
                <button
                  key={m.manager_id}
                  onClick={(e) => { e.preventDefault(); e.stopPropagation(); handleSelect(m.manager_id); }}
                  className="w-full text-left px-3 py-2 text-xs text-fg hover:bg-surface-sunken transition-colors truncate"
                >
                  {m.manager_name}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function openCommandMenu() {
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }));
}

export function Dashboard() {
  const [showAddManager, setShowAddManager] = useState(false);

  const { data, loading, error, refetch } = useApiQuery(async () => {
    const [overview, del, lse, vac, nm] = await Promise.all([
      api.dashboardOverview(),
      api.delinquencyBoard().catch(() => null),
      api.leasesExpiring(90).catch(() => null),
      api.vacancyTracker().catch(() => null),
      api.needsManager().catch(() => null),
    ]);
    return {
      overview: overview as DashboardOverview,
      delinquency: del as DelinquencyBoard | null,
      leases: lse as LeaseCalendar | null,
      vacancies: vac as VacancyTracker | null,
      needsMgr: nm as NeedsManagerResponse | null,
    };
  }, []);

  const overview = data?.overview ?? null;
  const delinquency = data?.delinquency ?? null;
  const leases = data?.leases ?? null;
  const vacancies = data?.vacancies ?? null;
  const needsMgr = data?.needsMgr ?? null;

  const totalUnits = overview?.total_units ?? 0;
  const totalOccupied = overview?.occupied ?? 0;
  const totalRevenue = overview?.total_monthly_rent ?? 0;
  const totalLTL = overview?.total_loss_to_lease ?? 0;
  const totalVacLoss = (overview?.total_market_rent ?? 0) - totalRevenue - totalLTL;
  const avgOcc = overview?.occupancy_rate ?? 0;
  const totalOpenMaint = overview?.properties.reduce((s, p) => s + p.open_maintenance, 0) ?? 0;

  const activeMgrs = overview?.managers.filter((m) => m.metrics.total_units > 0 || m.property_count > 0) ?? [];
  const unassignedProps = overview?.properties.filter((p) => !p.manager_id) ?? [];

  const alerts: { href: string; count: number; label: string; sub?: string; color: "error" | "warn" | "orange" | "sky" | "violet"; pulse?: boolean }[] = [];
  if (delinquency && delinquency.total_delinquent > 0)
    alerts.push({ href: "/delinquency", count: delinquency.total_delinquent, label: "Delinquent tenants", sub: `${fmt$(delinquency.total_balance)} owed`, color: "error", pulse: delinquency.total_delinquent > 5 });
  if (leases && leases.total_expiring > 0)
    alerts.push({ href: "/leases", count: leases.total_expiring, label: "Leases expiring (90d)", sub: `${leases.month_to_month_count} month-to-month`, color: "warn" });
  if (vacancies && vacancies.total_vacant > 0)
    alerts.push({ href: "/vacancies", count: vacancies.total_vacant, label: "Vacant units", sub: `${fmt$(vacancies.total_market_rent_at_risk)}/mo at risk`, color: "orange" });
  if (totalOpenMaint > 0)
    alerts.push({ href: "/properties", count: totalOpenMaint, label: "Open maintenance", color: "sky" });
  if (needsMgr && needsMgr.total > 0)
    alerts.push({ href: "#unassigned", count: needsMgr.total, label: "Need manager", sub: "Assign below", color: "violet" });

  if (loading) {
    return (
      <PageContainer wide>
        <div className="pt-2 pb-1"><CommandTrigger onClick={openCommandMenu} prominent /></div>
        <div className="flex items-center justify-center py-20">
          <div className="text-sm text-fg-faint animate-pulse">Loading dashboard...</div>
        </div>
      </PageContainer>
    );
  }

  if (error) {
    return (
      <PageContainer wide>
        <div className="pt-2 pb-1"><CommandTrigger onClick={openCommandMenu} prominent /></div>
        <div className="py-8">
          <ErrorBanner error={error} onRetry={refetch} />
        </div>
      </PageContainer>
    );
  }

  if (!overview || overview.total_properties === 0) {
    return (
      <PageContainer wide>
        <div className="pt-2 pb-1"><CommandTrigger onClick={openCommandMenu} prominent /></div>
        <div className="flex flex-col items-center justify-center py-24 text-center anim-scale-in">
          <div className="w-16 h-16 rounded-2xl bg-surface-sunken flex items-center justify-center mb-4">
            <svg className="w-8 h-8 text-fg-ghost" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z" />
            </svg>
          </div>
          <p className="text-sm text-fg-muted font-medium">No data yet</p>
          <p className="text-xs text-fg-faint mt-1">Upload an AppFolio report to get started</p>
          <Link
            href="/documents"
            className="mt-4 px-5 py-2.5 rounded-xl bg-accent text-accent-fg text-xs font-medium hover:bg-accent-hover transition-colors"
          >
            Upload Reports
          </Link>
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer wide>
      <div className="pt-2 pb-1 anim-fade-up">
        <CommandTrigger onClick={openCommandMenu} prominent />
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="flex gap-3 flex-wrap sm:flex-nowrap sm:overflow-x-auto pb-1 stagger scrollbar-none">
          {alerts.map((a) => (
            <AlertChip key={a.href} {...a} />
          ))}
        </div>
      )}

      {/* Health overview — occupancy hero + financials */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 anim-fade-up" style={{ animationDelay: "100ms" }}>
        <div className="rounded-2xl border border-border bg-surface p-6 flex flex-col items-center justify-center card-hover relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-br from-accent/5 to-transparent pointer-events-none" />
          <div className="relative">
            <OccupancyRing rate={avgOcc} />
          </div>
          <p className="text-xs text-fg-muted mt-3 relative">
            {totalOccupied.toLocaleString()} of {totalUnits.toLocaleString()} units
          </p>
        </div>

        <div className="rounded-2xl border border-border bg-surface p-6 lg:col-span-2 card-hover">
          <h2 className="text-[10px] font-semibold text-fg-muted uppercase tracking-widest mb-4">Financials</h2>
          <div className="grid grid-cols-2 gap-x-10 gap-y-0">
            <div>
              <StatRow label="Monthly Revenue" value={fmt$(totalRevenue)} />
              <StatRow label="Rev / Unit" value={totalUnits > 0 ? fmt$(Math.round(totalRevenue / totalUnits)) : "—"} />
              <StatRow label="Loss to Lease" value={fmt$(totalLTL)} alert={totalLTL > 0} />
              <StatRow label="Vacancy Loss" value={fmt$(Math.max(totalVacLoss, 0))} alert={totalVacLoss > 0} />
            </div>
            <div>
              <StatRow label="Properties" value={overview.total_properties.toLocaleString()} />
              <StatRow label="Total Units" value={totalUnits.toLocaleString()} />
              <StatRow label="Leases Expiring" value={leases ? `${leases.total_expiring} (90d)` : "—"} alert={(leases?.total_expiring ?? 0) > 0} />
              <StatRow label="Delinquent" value={delinquency ? `${delinquency.total_delinquent} — ${fmt$(delinquency.total_balance)}` : "—"} alert={(delinquency?.total_delinquent ?? 0) > 0} />
            </div>
          </div>

          {totalRevenue + totalLTL + Math.max(totalVacLoss, 0) > 0 && (() => {
            const vacLoss = Math.max(totalVacLoss, 0);
            const potential = totalRevenue + totalLTL + vacLoss;
            const revPct = totalRevenue / potential;
            const ltlPct = totalLTL / potential;
            const vacPct = vacLoss / potential;
            return (
              <div className="mt-5 pt-4 border-t border-border-subtle">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-semibold text-fg-muted uppercase tracking-widest">Revenue vs Potential</span>
                  <span className="text-[10px] text-fg-faint">{fmt$(potential)} potential</span>
                </div>
                <div className="flex h-2.5 rounded-full overflow-hidden bg-border-subtle">
                  <div className="bg-ok transition-all duration-700" style={{ width: `${revPct * 100}%` }} title={`Collected: ${fmt$(totalRevenue)}`} />
                  {ltlPct > 0.005 && (
                    <div className="bg-warn transition-all duration-700" style={{ width: `${ltlPct * 100}%` }} title={`Loss to lease: ${fmt$(totalLTL)}`} />
                  )}
                  {vacPct > 0.005 && (
                    <div className="bg-error transition-all duration-700" style={{ width: `${vacPct * 100}%` }} title={`Vacancy loss: ${fmt$(vacLoss)}`} />
                  )}
                </div>
                <div className="flex gap-4 mt-2">
                  <span className="flex items-center gap-1.5 text-[10px] text-fg-muted"><span className="w-2 h-2 rounded-full bg-ok" />Collected</span>
                  {ltlPct > 0.005 && <span className="flex items-center gap-1.5 text-[10px] text-fg-muted"><span className="w-2 h-2 rounded-full bg-warn" />Below market</span>}
                  {vacPct > 0.005 && <span className="flex items-center gap-1.5 text-[10px] text-fg-muted"><span className="w-2 h-2 rounded-full bg-error" />Vacant</span>}
                </div>
              </div>
            );
          })()}
        </div>
      </div>

      {/* Visual breakdown cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 anim-fade-up" style={{ animationDelay: "200ms" }}>
        {/* Unit composition bar */}
        {totalUnits > 0 && (() => {
          const vacant = totalUnits - totalOccupied;
          const notice = vacancies?.total_notice ?? 0;
          const occPct = (totalOccupied / totalUnits) * 100;
          const noticePct = (notice / totalUnits) * 100;
          const vacPct = (vacant / totalUnits) * 100;
          return (
            <Link href="/vacancies" className="rounded-2xl border border-border bg-surface p-6 card-hover group transition-all hover:border-accent/20">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-[10px] font-semibold text-fg-muted uppercase tracking-widest">Unit Status</h2>
                <span className="text-[10px] text-fg-ghost group-hover:text-accent transition-colors">{totalUnits.toLocaleString()} total</span>
              </div>
              <div className="flex h-4 rounded-full overflow-hidden bg-border-subtle">
                <div className="bg-ok transition-all duration-700" style={{ width: `${occPct}%` }} />
                {noticePct > 0.5 && <div className="bg-warn transition-all duration-700" style={{ width: `${noticePct}%` }} />}
                {vacPct > 0.5 && <div className="bg-error/70 transition-all duration-700" style={{ width: `${vacPct}%` }} />}
              </div>
              <div className="flex gap-5 mt-3">
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-ok" />
                  <span className="text-xs text-fg-secondary"><span className="font-semibold text-fg">{totalOccupied.toLocaleString()}</span> occupied</span>
                </div>
                {notice > 0 && (
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-warn" />
                    <span className="text-xs text-fg-secondary"><span className="font-semibold text-fg">{notice}</span> notice</span>
                  </div>
                )}
                {vacant > 0 && (
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-error/70" />
                    <span className="text-xs text-fg-secondary"><span className="font-semibold text-fg">{vacant}</span> vacant</span>
                  </div>
                )}
              </div>
              {vacancies && vacancies.total_market_rent_at_risk > 0 && (
                <p className="text-[11px] text-fg-faint mt-2">{fmt$(vacancies.total_market_rent_at_risk)}/mo at risk from vacancies</p>
              )}
            </Link>
          );
        })()}

        {/* Lease expiry horizon */}
        {leases && leases.leases.length > 0 && (() => {
          const b30 = leases.leases.filter((l) => !l.is_month_to_month && l.days_left <= 30).length;
          const b60 = leases.leases.filter((l) => !l.is_month_to_month && l.days_left > 30 && l.days_left <= 60).length;
          const b90 = leases.leases.filter((l) => !l.is_month_to_month && l.days_left > 60 && l.days_left <= 90).length;
          const mtm = leases.month_to_month_count;
          const maxBucket = Math.max(b30, b60, b90, mtm, 1);
          const bar = (count: number, color: string) => (
            <div className={`${color} rounded-r-full h-5 transition-all duration-700`} style={{ width: `${Math.max((count / maxBucket) * 100, count > 0 ? 8 : 0)}%` }} />
          );
          return (
            <Link href="/leases" className="rounded-2xl border border-border bg-surface p-6 card-hover group transition-all hover:border-accent/20">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-[10px] font-semibold text-fg-muted uppercase tracking-widest">Lease Expirations</h2>
                <span className="text-[10px] text-fg-ghost group-hover:text-accent transition-colors">{leases.total_expiring} total</span>
              </div>
              <div className="space-y-2.5">
                <div className="flex items-center gap-3">
                  <span className="text-[10px] text-fg-muted w-12 shrink-0 text-right">30 days</span>
                  <div className="flex-1">{bar(b30, "bg-error")}</div>
                  <span className="text-xs font-semibold font-mono text-fg w-6 text-right">{b30}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-[10px] text-fg-muted w-12 shrink-0 text-right">60 days</span>
                  <div className="flex-1">{bar(b60, "bg-warn")}</div>
                  <span className="text-xs font-semibold font-mono text-fg w-6 text-right">{b60}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-[10px] text-fg-muted w-12 shrink-0 text-right">90 days</span>
                  <div className="flex-1">{bar(b90, "bg-warn/50")}</div>
                  <span className="text-xs font-semibold font-mono text-fg w-6 text-right">{b90}</span>
                </div>
                {mtm > 0 && (
                  <div className="flex items-center gap-3">
                    <span className="text-[10px] text-fg-muted w-12 shrink-0 text-right">MTM</span>
                    <div className="flex-1">{bar(mtm, "bg-accent/40")}</div>
                    <span className="text-xs font-semibold font-mono text-fg w-6 text-right">{mtm}</span>
                  </div>
                )}
              </div>
            </Link>
          );
        })()}

        {/* Delinquency snapshot */}
        {delinquency && delinquency.total_delinquent > 0 && (() => {
          const total0_30 = delinquency.tenants.reduce((s, t) => s + t.balance_0_30, 0);
          const total30p = delinquency.tenants.reduce((s, t) => s + t.balance_30_plus, 0);
          const totalBal = delinquency.total_balance || 1;
          return (
            <Link href="/delinquency" className="rounded-2xl border border-border bg-surface p-6 card-hover group transition-all hover:border-accent/20">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-[10px] font-semibold text-fg-muted uppercase tracking-widest">Delinquency</h2>
                <span className="text-[10px] text-fg-ghost group-hover:text-accent transition-colors">{delinquency.total_delinquent} tenants</span>
              </div>
              <div className="flex items-end gap-6">
                <div className="flex-1">
                  <p className="text-3xl font-bold text-error tracking-tight">{fmt$(delinquency.total_balance)}</p>
                  <p className="text-[11px] text-fg-faint mt-1">total outstanding</p>
                </div>
                <div className="flex gap-2 items-end h-16">
                  <div className="flex flex-col items-center gap-1">
                    <div className="w-10 bg-warn rounded-t transition-all duration-700" style={{ height: `${(total0_30 / totalBal) * 64}px`, minHeight: total0_30 > 0 ? 8 : 0 }} />
                    <span className="text-[9px] text-fg-muted">0-30</span>
                  </div>
                  <div className="flex flex-col items-center gap-1">
                    <div className="w-10 bg-error rounded-t transition-all duration-700" style={{ height: `${(total30p / totalBal) * 64}px`, minHeight: total30p > 0 ? 8 : 0 }} />
                    <span className="text-[9px] text-fg-muted">30+</span>
                  </div>
                </div>
              </div>
              <div className="flex gap-4 mt-3 text-[10px]">
                <span className="text-fg-muted">0-30d: <span className="font-semibold text-warn">{fmt$(total0_30)}</span></span>
                <span className="text-fg-muted">30+d: <span className="font-semibold text-error">{fmt$(total30p)}</span></span>
              </div>
            </Link>
          );
        })()}

        {/* Maintenance card */}
        {totalOpenMaint > 0 && (
          <Link href="/properties" className="rounded-2xl border border-border bg-surface p-6 card-hover group transition-all hover:border-accent/20">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-[10px] font-semibold text-fg-muted uppercase tracking-widest">Maintenance</h2>
              <span className="text-[10px] text-fg-ghost group-hover:text-accent transition-colors">{totalOpenMaint} open</span>
            </div>
            <div className="flex items-end gap-6">
              <div className="flex-1">
                <p className="text-3xl font-bold text-fg tracking-tight">{totalOpenMaint}</p>
                <p className="text-[11px] text-fg-faint mt-1">open requests</p>
              </div>
            </div>
            {overview.properties.filter((p) => p.open_maintenance > 0).length > 1 && (
              <div className="mt-4 pt-3 border-t border-border-subtle space-y-1.5">
                {[...overview.properties].filter((p) => p.open_maintenance > 0).sort((a, b) => b.open_maintenance - a.open_maintenance).slice(0, 5).map((p) => (
                  <div key={p.property_id} className="flex items-center gap-2">
                    <span className="text-[10px] text-fg-muted truncate w-28 shrink-0">{p.property_name}</span>
                    <div className="flex-1 h-1.5 rounded-full bg-border-subtle overflow-hidden">
                      <div className="h-full rounded-full bg-sky-400 transition-all duration-500" style={{ width: `${(p.open_maintenance / totalOpenMaint) * 100}%` }} />
                    </div>
                    <span className="text-[10px] font-mono text-fg-secondary w-5 text-right">{p.open_maintenance}</span>
                  </div>
                ))}
              </div>
            )}
          </Link>
        )}
      </div>

      {/* Manager cards — primary organizational view */}
      {activeMgrs.length > 0 && (
        <div className="anim-fade-up" style={{ animationDelay: "250ms" }}>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[10px] font-semibold text-fg-muted uppercase tracking-widest">Property Managers</h2>
            <button
              onClick={() => setShowAddManager(true)}
              className="flex items-center gap-1.5 text-[10px] font-medium text-accent hover:text-accent-hover transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              Add Manager
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {activeMgrs.map((mgr) => (
              <ManagerCard
                key={mgr.manager_id}
                mgr={mgr}
                properties={overview.properties.filter((p) => p.manager_id === mgr.manager_id)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Unassigned properties — shown separately when they exist */}
      {unassignedProps.length > 0 && (
        <div className="rounded-2xl border border-dashed border-border bg-surface/60 anim-fade-up" style={{ animationDelay: "300ms" }}>
          <div className="px-5 py-4 border-b border-border-subtle flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-violet-400" />
              <h2 className="text-[10px] font-semibold text-fg-muted uppercase tracking-widest">Unassigned Properties</h2>
            </div>
            <span className="text-[10px] text-fg-faint">{unassignedProps.length} {unassignedProps.length === 1 ? "property" : "properties"}</span>
          </div>
          <div className="divide-y divide-border-subtle">
            {unassignedProps.slice(0, 20).map((p) => (
              <div key={p.property_id} className="grid grid-cols-[1fr_60px_70px_90px_80px_auto] items-center gap-2 px-4 py-2.5 hover:bg-surface-sunken transition-colors group">
                <Link href={`/properties/${p.property_id}`} className="min-w-0">
                  <p className="text-xs font-medium text-fg truncate group-hover:text-accent transition-colors">{p.property_name}</p>
                </Link>
                <span className="text-[11px] font-mono text-fg text-right">{p.total_units} u</span>
                <span className={`text-[11px] font-mono text-right font-semibold ${p.occupancy_rate >= 0.95 ? "text-ok" : p.occupancy_rate >= 0.9 ? "text-warn" : "text-error"}`}>{pct(p.occupancy_rate)}</span>
                <span className="text-[11px] font-mono text-fg text-right">{fmt$(p.monthly_rent)}</span>
                <span className={`text-[11px] font-mono text-right ${p.loss_to_lease > 0 ? "text-warn" : "text-fg-faint"}`}>{p.loss_to_lease > 0 ? fmt$(p.loss_to_lease) : "—"}</span>
                <AssignDropdown
                  propertyId={p.property_id}
                  managers={activeMgrs}
                  onAssigned={refetch}
                />
              </div>
            ))}
            {unassignedProps.length > 20 && (
              <div className="px-4 py-3 text-center">
                <Link href="/properties" className="text-[11px] text-accent hover:text-accent-hover transition-colors">
                  View all {unassignedProps.length} properties
                </Link>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Add manager button (when no managers exist yet) */}
      {activeMgrs.length === 0 && (
        <div className="flex gap-3 anim-fade-up" style={{ animationDelay: "250ms" }}>
          <button
            onClick={() => setShowAddManager(true)}
            className="flex-1 flex items-center justify-center gap-2.5 rounded-2xl border border-dashed border-border bg-surface/80 px-5 py-5 text-sm font-medium text-fg-muted hover:border-accent/40 hover:text-accent hover:bg-accent-soft hover:shadow-lg hover:shadow-accent/10 transition-all btn-glow"
          >
            <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center">
              <svg className="w-4 h-4 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
            </div>
            Add a Property Manager to organize your portfolio
          </button>
        </div>
      )}

      <EntityFormPanel
        open={showAddManager}
        onClose={() => setShowAddManager(false)}
        title="Add Property Manager"
        fields={MANAGER_FIELDS}
        submitLabel="Create Manager"
        onSubmit={async (values) => {
          await api.createManager(values as { name: string; email?: string; company?: string; phone?: string });
          refetch();
        }}
      />
    </PageContainer>
  );
}
