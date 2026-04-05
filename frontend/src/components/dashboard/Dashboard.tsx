"use client";

import Link from "next/link";
import { api } from "@/lib/api";
import { fmt$, pct } from "@/lib/format";
import { useApiQuery } from "@/hooks/useApiQuery";
import { PageContainer } from "@/components/ui/PageContainer";
import { CommandTrigger, useCommandMenu } from "@/components/ui/CommandMenu";
import type {
  ManagerListItem,
  DelinquencyBoard,
  LeaseCalendar,
  VacancyTracker,
  NeedsManagerResponse,
} from "@/lib/types";

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

function openCommandMenu() {
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }));
}

export function Dashboard() {
  const { data: dashboardData, loading } = useApiQuery(async () => {
    const [mgrs, del, lse, vac, nm] = await Promise.all([
      api.listManagers().catch(() => []),
      api.delinquencyBoard().catch(() => null),
      api.leasesExpiring(90).catch(() => null),
      api.vacancyTracker().catch(() => null),
      api.needsManager().catch(() => null),
    ]);
    return {
      managers: mgrs as ManagerListItem[],
      delinquency: del as DelinquencyBoard | null,
      leases: lse as LeaseCalendar | null,
      vacancies: vac as VacancyTracker | null,
      needsMgr: nm as NeedsManagerResponse | null,
    };
  }, []);

  const managers = dashboardData?.managers ?? [];
  const delinquency = dashboardData?.delinquency ?? null;
  const leases = dashboardData?.leases ?? null;
  const vacancies = dashboardData?.vacancies ?? null;
  const needsMgr = dashboardData?.needsMgr ?? null;

  const activeMgrs = managers.filter((m) => m.total_units > 0 || m.property_count > 0);

  const totalUnits = activeMgrs.reduce((s, m) => s + m.total_units, 0);
  const totalOccupied = activeMgrs.reduce((s, m) => s + m.occupied, 0);
  const totalRevenue = activeMgrs.reduce((s, m) => s + m.total_actual_rent, 0);
  const totalLTL = activeMgrs.reduce((s, m) => s + m.total_loss_to_lease, 0);
  const totalVacLoss = activeMgrs.reduce((s, m) => s + m.total_vacancy_loss, 0);
  const avgOcc = totalUnits > 0 ? totalOccupied / totalUnits : 0;

  const totalOpenMaint = activeMgrs.reduce((s, m) => s + m.open_maintenance, 0);
  const totalEmergency = activeMgrs.reduce((s, m) => s + m.emergency_maintenance, 0);

  const alerts: { href: string; count: number; label: string; sub?: string; color: "error" | "warn" | "orange" | "sky" | "violet"; pulse?: boolean }[] = [];
  if (delinquency && delinquency.total_delinquent > 0)
    alerts.push({ href: "/delinquency", count: delinquency.total_delinquent, label: "Delinquent tenants", sub: `${fmt$(delinquency.total_balance)} owed`, color: "error", pulse: delinquency.total_delinquent > 5 });
  if (leases && leases.total_expiring > 0)
    alerts.push({ href: "/leases", count: leases.total_expiring, label: "Leases expiring (90d)", sub: `${leases.month_to_month_count} month-to-month`, color: "warn" });
  if (vacancies && vacancies.total_vacant > 0)
    alerts.push({ href: "/vacancies", count: vacancies.total_vacant, label: "Vacant units", sub: `${fmt$(vacancies.total_market_rent_at_risk)}/mo at risk`, color: "orange" });
  if (totalOpenMaint > 0)
    alerts.push({ href: "/managers", count: totalEmergency || totalOpenMaint, label: totalEmergency > 0 ? "Emergency maintenance" : "Open maintenance", sub: totalEmergency > 0 ? `${totalOpenMaint} total open` : undefined, color: "sky", pulse: totalEmergency > 0 });
  if (needsMgr && needsMgr.total > 0)
    alerts.push({ href: "/documents", count: needsMgr.total, label: "Need manager", sub: "Upload with PM to assign", color: "violet" });

  if (loading) {
    return (
      <PageContainer wide>
        <div className="pt-2 pb-1"><CommandTrigger onClick={openCommandMenu} prominent /></div>
        <div className="flex items-center justify-center py-20">
          <div className="text-sm text-fg-faint animate-pulse">Loading portfolio...</div>
        </div>
      </PageContainer>
    );
  }

  if (activeMgrs.length === 0) {
    return (
      <PageContainer wide>
        <div className="pt-2 pb-1"><CommandTrigger onClick={openCommandMenu} prominent /></div>
        <div className="flex flex-col items-center justify-center py-24 text-center anim-scale-in">
          <div className="w-16 h-16 rounded-2xl bg-surface-sunken flex items-center justify-center mb-4">
            <svg className="w-8 h-8 text-fg-ghost" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z" />
            </svg>
          </div>
          <p className="text-sm text-fg-muted font-medium">Your portfolio is empty</p>
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

      {/* Alerts — staggered entry, wrap on narrow screens */}
      {alerts.length > 0 && (
        <div className="flex gap-3 flex-wrap sm:flex-nowrap sm:overflow-x-auto pb-1 stagger scrollbar-none">
          {alerts.map((a) => (
            <AlertChip key={a.href} {...a} />
          ))}
        </div>
      )}

      {/* Portfolio health — occupancy hero + financials */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 anim-fade-up" style={{ animationDelay: "100ms" }}>
        {/* Occupancy hero with glass */}
        <div className="rounded-2xl border border-border bg-surface p-6 flex flex-col items-center justify-center card-hover relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-br from-accent/5 to-transparent pointer-events-none" />
          <div className="relative">
            <OccupancyRing rate={avgOcc} />
          </div>
          <p className="text-xs text-fg-muted mt-3 relative">
            {totalOccupied.toLocaleString()} of {totalUnits.toLocaleString()} units
          </p>
        </div>

        {/* Financial summary */}
        <div className="rounded-2xl border border-border bg-surface p-6 lg:col-span-2 card-hover">
          <h2 className="text-[10px] font-semibold text-fg-muted uppercase tracking-widest mb-4">Portfolio Financials</h2>
          <div className="grid grid-cols-2 gap-x-10 gap-y-0">
            <div>
              <StatRow label="Monthly Revenue" value={fmt$(totalRevenue)} />
              <StatRow label="Loss to Lease" value={fmt$(totalLTL)} alert={totalLTL > 0} />
              <StatRow label="Vacancy Loss" value={fmt$(totalVacLoss)} alert={totalVacLoss > 0} />
            </div>
            <div>
              <StatRow label="Active Managers" value={String(activeMgrs.length)} />
              <StatRow label="Total Properties" value={String(activeMgrs.reduce((s, m) => s + m.property_count, 0))} />
              <StatRow label="Total Units" value={totalUnits.toLocaleString()} />
            </div>
          </div>
        </div>
      </div>

      {/* Manager access */}
      <Link
        href="/managers"
        className="group flex items-center justify-between rounded-2xl border border-border bg-surface p-5 hover:border-accent/30 hover:bg-accent-soft card-hover transition-all anim-fade-up"
        style={{ animationDelay: "200ms" }}
      >
        <div className="flex items-center gap-4">
          <div className="w-11 h-11 rounded-xl bg-accent/10 flex items-center justify-center shrink-0 group-hover:bg-accent/20 transition-colors">
            <svg className="w-5 h-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z" />
            </svg>
          </div>
          <div>
            <h2 className="text-sm font-semibold text-fg group-hover:text-accent transition-colors">{activeMgrs.length} Property Managers</h2>
            <p className="text-[11px] text-fg-faint mt-0.5">Review performance, drill into portfolios</p>
          </div>
        </div>
        <svg className="w-5 h-5 text-fg-ghost group-hover:text-accent group-hover:translate-x-1 transition-all" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
        </svg>
      </Link>
    </PageContainer>
  );
}
