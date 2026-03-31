"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { fmt$, fmtDate, pct } from "@/lib/format";
import { useApiQuery } from "@/hooks/useApiQuery";
import { ReviewPrepTab } from "./ReviewPrepTab";
import { MetricCard } from "@/components/ui/MetricCard";
import { MetricStrip } from "@/components/ui/MetricStrip";
import { PageContainer } from "@/components/ui/PageContainer";
import { Badge } from "@/components/ui/Badge";
import { StatusDot } from "@/components/ui/StatusDot";
import type {
  ManagerReview,
  ManagerPropertySummary,
  DelinquencyBoard,
  DelinquentTenant,
  LeaseCalendar,
  ExpiringLease,
  VacancyTracker,
  VacantUnit,
  ManagerSnapshot,
} from "@/lib/types";

type Tab = "overview" | "delinquency" | "leases" | "vacancies" | "performance" | "review";

const TABS: { key: Tab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "delinquency", label: "Delinquency" },
  { key: "leases", label: "Leases" },
  { key: "vacancies", label: "Vacancies" },
  { key: "performance", label: "Performance" },
  { key: "review", label: "Review Prep" },
];

/* ------------------------------------------------------------------ */
/* Sub-components                                                      */
/* ------------------------------------------------------------------ */

function PropertyRow({ p }: { p: ManagerPropertySummary }) {
  const occ = p.total_units > 0 ? p.occupied / p.total_units : 0;
  return (
    <Link
      href={`/properties/${p.property_id}`}
      className="flex items-center gap-4 px-5 py-3 border-b border-border-subtle hover:bg-surface-raised transition-colors"
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <StatusDot status={p.issue_count === 0 ? "done" : p.emergency_maintenance > 0 ? "error" : "calling"} size={6} />
          <span className="text-sm font-medium text-fg truncate">{p.property_name}</span>
        </div>
      </div>
      <div className="flex items-center gap-6 shrink-0 text-xs">
        <div className="text-right w-16">
          <p className="text-fg-muted">Units</p>
          <p className="text-fg font-medium">{p.occupied}/{p.total_units}</p>
        </div>
        <div className="text-right w-16">
          <p className="text-fg-muted">Occ.</p>
          <p className={`font-medium ${occ < 0.9 ? "text-warn" : "text-fg"}`}>{pct(occ)}</p>
        </div>
        <div className="text-right w-20">
          <p className="text-fg-muted">Revenue</p>
          <p className="text-fg font-mono font-medium">{fmt$(p.monthly_actual)}</p>
        </div>
        <div className="text-right w-20">
          <p className="text-fg-muted">LTL</p>
          <p className={`font-mono font-medium ${p.loss_to_lease > 0 ? "text-warn" : "text-fg-muted"}`}>{fmt$(p.loss_to_lease)}</p>
        </div>
        <div className="flex flex-wrap gap-1 w-40 justify-end">
          {p.vacant > 0 && <Badge variant="red">{p.vacant} vac</Badge>}
          {p.expiring_leases > 0 && <Badge variant="amber">{p.expiring_leases} exp</Badge>}
          {p.expired_leases > 0 && <Badge variant="red">{p.expired_leases} expired</Badge>}
          {p.below_market_units > 0 && <Badge variant="amber">{p.below_market_units} ↓mkt</Badge>}
          {p.open_maintenance > 0 && <Badge variant="cyan">{p.open_maintenance} maint</Badge>}
          {p.issue_count === 0 && <Badge variant="emerald">OK</Badge>}
        </div>
      </div>
    </Link>
  );
}

function OverviewTab({ review }: { review: ManagerReview }) {
  const totalIssues = review.vacant + review.open_maintenance + review.expiring_leases_90d + review.expired_leases + review.below_market_units;

  return (
    <div className="space-y-6">
      <MetricStrip>
        <MetricCard label="Units" value={review.total_units} sub={`${review.occupied} occupied`} />
        <MetricCard label="Occupancy" value={pct(review.occupancy_rate)} trend={review.occupancy_rate >= 0.9 ? "up" : "down"} />
        <MetricCard label="Revenue" value={fmt$(review.total_actual_rent)} />
        <MetricCard label="Market Rent" value={fmt$(review.total_market_rent)} />
        <MetricCard label="Loss to Lease" value={fmt$(review.total_loss_to_lease)} alert={review.total_loss_to_lease > 0} />
        <MetricCard label="Vacancy Loss" value={fmt$(review.total_vacancy_loss)} alert={review.total_vacancy_loss > 0} />
        <MetricCard label="Delinquent" value={review.delinquent_count} sub={review.total_delinquent_balance > 0 ? fmt$(review.total_delinquent_balance) + " owed" : undefined} alert={review.delinquent_count > 0} />
        <MetricCard label="Expiring (90d)" value={review.expiring_leases_90d} alert={review.expiring_leases_90d > 0} />
        <MetricCard label="Issues" value={totalIssues} alert={totalIssues > 0} />
      </MetricStrip>

      {/* Properties table */}
      <section className="rounded-xl border border-border bg-surface overflow-hidden">
        <div className="px-5 py-3 border-b border-border-subtle">
          <h2 className="text-xs font-semibold text-fg-secondary uppercase tracking-wide">
            Properties ({review.properties.length})
          </h2>
        </div>
        <div className="max-h-[600px] overflow-y-auto">
          {review.properties.map((p) => (
            <PropertyRow key={p.property_id} p={p} />
          ))}
          {review.properties.length === 0 && (
            <p className="text-sm text-fg-faint text-center py-12">No properties</p>
          )}
        </div>
      </section>

      {/* Top issues */}
      {review.top_issues.length > 0 && (
        <section className="rounded-xl border border-border bg-surface overflow-hidden">
          <div className="px-5 py-3 border-b border-border-subtle">
            <h2 className="text-xs font-semibold text-fg-secondary uppercase tracking-wide">
              Unit Issues ({review.top_issues.length})
            </h2>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {review.top_issues.map((issue) => (
              <Link
                key={issue.unit_id}
                href={`/properties/${issue.property_id}`}
                className="flex items-center gap-4 px-5 py-2.5 border-b border-border-subtle hover:bg-surface-raised transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <span className="text-sm text-fg-secondary font-mono">{issue.unit_number}</span>
                  <span className="text-[10px] text-fg-faint ml-2">{issue.property_name}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  {issue.issues.map((iss) => (
                    <Badge key={iss} variant={iss === "vacant" || iss === "expired_lease" ? "red" : iss === "below_market" || iss === "expiring_soon" ? "amber" : "cyan"}>
                      {iss.replace(/_/g, " ")}
                    </Badge>
                  ))}
                </div>
                {issue.monthly_impact > 0 && (
                  <span className="text-xs text-warn font-mono">-{fmt$(issue.monthly_impact)}/mo</span>
                )}
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function DelinquencyTab({ data }: { data: DelinquencyBoard | null }) {
  if (!data || data.total_delinquent === 0) {
    return <p className="text-sm text-fg-faint text-center py-12">No delinquent tenants</p>;
  }

  return (
    <div className="space-y-4">
      <MetricStrip className="lg:grid-cols-2">
        <MetricCard label="Delinquent Tenants" value={data.total_delinquent} alert />
        <MetricCard label="Total Balance Owed" value={fmt$(data.total_balance)} alert />
      </MetricStrip>
      <div className="rounded-xl border border-border bg-surface overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Tenant</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Property</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Unit</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Status</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">0-30</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">30+</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Total</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Last Paid</th>
              </tr>
            </thead>
            <tbody>
              {data.tenants.map((t) => (
                <tr key={t.tenant_id} className="border-b border-border-subtle hover:bg-surface-raised">
                  <td className="px-4 py-2 text-fg font-medium">{t.tenant_name}</td>
                  <td className="px-4 py-2 text-fg-secondary">{t.property_name || "—"}</td>
                  <td className="px-4 py-2 text-fg-secondary font-mono">{t.unit_number || "—"}</td>
                  <td className="px-4 py-2">
                    <Badge variant={t.status === "evict" ? "red" : t.status === "notice" ? "amber" : "blue"}>{t.status}</Badge>
                  </td>
                  <td className="px-4 py-2 text-right text-fg-secondary font-mono">{fmt$(t.balance_0_30)}</td>
                  <td className="px-4 py-2 text-right font-mono">
                    <span className={t.balance_30_plus > 0 ? "text-error" : "text-fg-muted"}>{fmt$(t.balance_30_plus)}</span>
                  </td>
                  <td className="px-4 py-2 text-right font-mono font-bold text-error">{fmt$(t.balance_owed)}</td>
                  <td className="px-4 py-2 text-fg-muted">{t.last_payment_date ? fmtDate(t.last_payment_date) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function LeasesTab({ data }: { data: LeaseCalendar | null }) {
  if (!data || data.total_expiring === 0) {
    return <p className="text-sm text-fg-faint text-center py-12">No expiring leases in the next {data?.days_window || 90} days</p>;
  }

  return (
    <div className="space-y-4">
      <MetricStrip className="lg:grid-cols-3">
        <MetricCard label="Expiring" value={data.total_expiring} alert={data.total_expiring > 5} />
        <MetricCard label="Month-to-Month" value={data.month_to_month_count} alert={data.month_to_month_count > 0} />
        <MetricCard label="Window" value={`${data.days_window}d`} />
      </MetricStrip>
      <div className="rounded-xl border border-border bg-surface overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Tenant</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Property</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Unit</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Rent</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Market</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Expires</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Days Left</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">MTM</th>
              </tr>
            </thead>
            <tbody>
              {data.leases.map((l) => (
                <tr key={l.lease_id} className="border-b border-border-subtle hover:bg-surface-raised">
                  <td className="px-4 py-2 text-fg font-medium">{l.tenant_name}</td>
                  <td className="px-4 py-2 text-fg-secondary">{l.property_name}</td>
                  <td className="px-4 py-2 text-fg-secondary font-mono">{l.unit_number}</td>
                  <td className="px-4 py-2 text-right text-fg-secondary font-mono">{fmt$(l.monthly_rent)}</td>
                  <td className="px-4 py-2 text-right font-mono">
                    <span className={l.market_rent > l.monthly_rent ? "text-warn" : "text-fg-secondary"}>{fmt$(l.market_rent)}</span>
                  </td>
                  <td className="px-4 py-2 text-fg-secondary">{fmtDate(l.end_date)}</td>
                  <td className="px-4 py-2 text-right">
                    <span className={l.days_left <= 30 ? "text-error font-bold" : l.days_left <= 60 ? "text-warn" : "text-fg-secondary"}>
                      {l.days_left}
                    </span>
                  </td>
                  <td className="px-4 py-2">{l.is_month_to_month ? <Badge variant="amber">MTM</Badge> : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function VacanciesTab({ data }: { data: VacancyTracker | null }) {
  if (!data || (data.total_vacant === 0 && data.total_notice === 0)) {
    return <p className="text-sm text-fg-faint text-center py-12">No vacant or notice units</p>;
  }

  return (
    <div className="space-y-4">
      <MetricStrip className="lg:grid-cols-4">
        <MetricCard label="Vacant" value={data.total_vacant} alert={data.total_vacant > 0} />
        <MetricCard label="On Notice" value={data.total_notice} alert={data.total_notice > 0} />
        <MetricCard label="Rent at Risk" value={fmt$(data.total_market_rent_at_risk)} alert />
        <MetricCard label="Avg Days Vacant" value={data.avg_days_vacant ?? "—"} />
      </MetricStrip>
      <div className="rounded-xl border border-border bg-surface overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Property</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Unit</th>
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Status</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Days Vacant</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Market Rent</th>
                <th className="text-center px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Listed</th>
              </tr>
            </thead>
            <tbody>
              {data.units.map((u) => (
                <tr key={u.unit_id} className="border-b border-border-subtle hover:bg-surface-raised">
                  <td className="px-4 py-2 text-fg font-medium">{u.property_name}</td>
                  <td className="px-4 py-2 text-fg-secondary font-mono">{u.unit_number}</td>
                  <td className="px-4 py-2">
                    <Badge variant={u.occupancy_status?.includes("vacant") ? "red" : "amber"}>
                      {(u.occupancy_status || "vacant").replace(/_/g, " ")}
                    </Badge>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <span className={u.days_vacant && u.days_vacant > 30 ? "text-error font-bold" : "text-fg-secondary"}>
                      {u.days_vacant ?? "—"}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right text-fg-secondary font-mono">{u.market_rent > 0 ? fmt$(u.market_rent) : "—"}</td>
                  <td className="px-4 py-2 text-center">
                    {u.listed_on_website || u.listed_on_internet ? (
                      <span className="text-ok">Yes</span>
                    ) : (
                      <span className="text-fg-faint">No</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function PerformanceTab({ snapshots, managerName }: { snapshots: ManagerSnapshot[]; managerName: string }) {
  if (snapshots.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-sm text-fg-faint">No performance snapshots yet.</p>
        <p className="text-xs text-fg-ghost mt-1">Snapshots are captured each time reports are uploaded.</p>
      </div>
    );
  }

  const sorted = [...snapshots].sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

  return (
    <div className="space-y-4">
      <p className="text-xs text-fg-muted">{sorted.length} snapshots for {managerName}</p>
      <div className="rounded-xl border border-border bg-surface overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Snapshot</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Props</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Units</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Occ</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Revenue</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">LTL</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Delinquent</th>
                <th className="text-right px-4 py-2.5 text-[10px] font-semibold text-fg-muted uppercase">Vacant</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((s, i) => {
                const prev = i > 0 ? sorted[i - 1] : null;
                return (
                  <tr key={s.timestamp} className="border-b border-border-subtle hover:bg-surface-raised">
                    <td className="px-4 py-2 text-fg-secondary text-[10px]">{fmtDate(s.timestamp)}</td>
                    <td className="px-4 py-2 text-right text-fg-secondary">{s.property_count}</td>
                    <td className="px-4 py-2 text-right text-fg-secondary">
                      {s.total_units}
                      {prev && s.total_units !== prev.total_units && (
                        <Delta prev={prev.total_units} curr={s.total_units} />
                      )}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <span className={s.occupancy_rate < 0.9 ? "text-warn" : "text-fg-secondary"}>{pct(s.occupancy_rate)}</span>
                      {prev && <Delta prev={prev.occupancy_rate} curr={s.occupancy_rate} fmt={pct} />}
                    </td>
                    <td className="px-4 py-2 text-right text-fg-secondary">
                      {fmt$(s.total_rent)}
                      {prev && <Delta prev={prev.total_rent} curr={s.total_rent} fmt={fmt$} />}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <span className={s.loss_to_lease > 0 ? "text-warn" : "text-fg-muted"}>
                        {s.loss_to_lease > 0 ? fmt$(s.loss_to_lease) : "—"}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <span className={s.delinquent_count > 0 ? "text-error" : "text-fg-muted"}>{s.delinquent_count || "—"}</span>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <span className={s.vacant > 0 ? "text-error" : "text-fg-muted"}>{s.vacant || "—"}</span>
                      {prev && <Delta prev={prev.vacant} curr={s.vacant} invert />}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Delta({ prev, curr, fmt: fmtFn, invert }: { prev: number; curr: number; fmt?: (n: number) => string; invert?: boolean }) {
  const diff = curr - prev;
  if (Math.abs(diff) < 0.001) return null;
  const positive = invert ? diff < 0 : diff > 0;
  const display = fmtFn ? fmtFn(Math.abs(diff)) : String(Math.abs(diff));
  return (
    <span className={`ml-1 text-[9px] font-bold ${positive ? "text-ok" : "text-error"}`}>
      {positive ? "+" : "-"}{display}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Main component                                                      */
/* ------------------------------------------------------------------ */

export function ManagerReviewView({ managerId }: { managerId: string }) {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("overview");

  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editCompany, setEditCompany] = useState("");
  const [editSaving, setEditSaving] = useState(false);

  const [deleting, setDeleting] = useState(false);

  const { data, loading, refetch } = useApiQuery(async () => {
    const [review, delinquency, leases, vacancies, snaps, actionItems] = await Promise.all([
      api.getManagerReview(managerId).catch(() => null),
      api.delinquencyBoard(managerId).catch(() => null),
      api.leasesExpiring(90, managerId).catch(() => null),
      api.vacancyTracker(managerId).catch(() => null),
      api.snapshots(managerId).catch(() => ({ total: 0, snapshots: [] })),
      api.listActionItems({ manager_id: managerId }).catch(() => ({ total: 0, items: [] })),
    ]);

    return {
      review: review as ManagerReview | null,
      delinquency: delinquency as DelinquencyBoard | null,
      leases: leases as LeaseCalendar | null,
      vacancies: vacancies as VacancyTracker | null,
      snapshots: snaps.snapshots as ManagerSnapshot[],
      actionCount: actionItems.total,
    };
  }, [managerId]);

  const review = data?.review ?? null;
  const delinquency = data?.delinquency ?? null;
  const leases = data?.leases ?? null;
  const vacancies = data?.vacancies ?? null;
  const snapshots = data?.snapshots ?? [];
  const actionCount = data?.actionCount ?? 0;

  function startEdit() {
    if (!review) return;
    setEditName(review.name);
    setEditEmail(review.email || "");
    setEditCompany(review.company || "");
    setEditing(true);
  }

  async function saveEdit() {
    setEditSaving(true);
    try {
      await api.updateManager(managerId, {
        name: editName.trim(),
        email: editEmail.trim() || undefined,
        company: editCompany.trim() || undefined,
      });
      setEditing(false);
      refetch();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to update manager");
    } finally {
      setEditSaving(false);
    }
  }

  async function handleDelete() {
    if (!confirm("Delete this manager? This action cannot be undone.")) return;
    setDeleting(true);
    try {
      await api.deleteManager(managerId);
      router.push("/");
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete manager");
      setDeleting(false);
    }
  }

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-sm text-fg-faint animate-pulse">Loading...</div>
      </div>
    );
  }

  if (!review) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-sm text-fg-muted">Manager not found</div>
      </div>
    );
  }

  // Badge counts for tabs
  const delCount = delinquency?.total_delinquent ?? 0;
  const leaseCount = leases?.total_expiring ?? 0;
  const vacCount = (vacancies?.total_vacant ?? 0) + (vacancies?.total_notice ?? 0);
  const snapCount = snapshots.length;

  return (
    <PageContainer wide>
        {/* Header */}
        <div>
          <Link href="/" className="text-xs text-fg-faint hover:text-fg-secondary transition-colors">
            &larr; All Managers
          </Link>

          {editing ? (
            <div className="mt-2 space-y-2 rounded-lg border border-border bg-surface-raised p-4">
              <div className="grid gap-2 sm:grid-cols-3">
                <input
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  placeholder="Name"
                  className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm text-fg placeholder:text-fg-faint focus:outline-none focus:ring-1 focus:ring-accent"
                />
                <input
                  value={editEmail}
                  onChange={(e) => setEditEmail(e.target.value)}
                  placeholder="Email"
                  className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm text-fg placeholder:text-fg-faint focus:outline-none focus:ring-1 focus:ring-accent"
                />
                <input
                  value={editCompany}
                  onChange={(e) => setEditCompany(e.target.value)}
                  placeholder="Company"
                  className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm text-fg placeholder:text-fg-faint focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={saveEdit}
                  disabled={editSaving || !editName.trim()}
                  className="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-fg disabled:opacity-50"
                >
                  {editSaving ? "Saving..." : "Save"}
                </button>
                <button
                  onClick={() => setEditing(false)}
                  disabled={editSaving}
                  className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-fg-secondary hover:text-fg disabled:opacity-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-3 mt-2">
              <h1 className="text-xl font-bold text-fg">{review.name}</h1>
              <button
                onClick={startEdit}
                className="rounded-md border border-border px-2 py-1 text-[10px] font-medium text-fg-muted hover:text-fg hover:border-fg-muted transition-colors"
              >
                Edit
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="rounded-md border border-border px-2 py-1 text-[10px] font-medium text-fg-muted hover:text-error hover:border-error transition-colors disabled:opacity-50"
              >
                {deleting ? "Deleting..." : "Delete"}
              </button>
            </div>
          )}

          <div className="flex items-center gap-3 mt-1">
            {review.company && <span className="text-xs text-fg-muted">{review.company}</span>}
            <span className="text-xs text-fg-faint">{review.property_count} properties · {review.total_units} units</span>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1 border-b border-border overflow-x-auto">
          {TABS.map(({ key, label }) => {
            const count = key === "delinquency" ? delCount : key === "leases" ? leaseCount : key === "vacancies" ? vacCount : key === "performance" ? snapCount : key === "review" ? actionCount : 0;
            return (
              <button
                key={key}
                onClick={() => setTab(key)}
                className={`px-4 py-2.5 text-xs font-medium border-b-2 transition-all ${
                  tab === key
                    ? "border-accent text-fg"
                    : "border-transparent text-fg-muted hover:text-fg-secondary"
                }`}
              >
                {label}
                {count > 0 && key !== "overview" && (
                  <span className={`ml-1.5 text-[9px] px-1.5 py-0.5 rounded-full ${
                    key === "delinquency" || key === "vacancies" ? "bg-error-soft text-error" : key === "leases" ? "bg-warn-soft text-warn" : key === "review" ? "bg-accent/20 text-accent" : "bg-surface-sunken text-fg-faint"
                  }`}>
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Tab content */}
        {tab === "overview" && <OverviewTab review={review} />}
        {tab === "delinquency" && <DelinquencyTab data={delinquency} />}
        {tab === "leases" && <LeasesTab data={leases} />}
        {tab === "vacancies" && <VacanciesTab data={vacancies} />}
        {tab === "performance" && <PerformanceTab snapshots={snapshots} managerName={review.name} />}
        {tab === "review" && <ReviewPrepTab managerId={managerId} />}
    </PageContainer>
  );
}
