"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { MetricCard } from "@/components/ui/MetricCard";
import { Badge } from "@/components/ui/Badge";
import type {
  PropertyDetail,
  RentRollResponse,
  RentRollRow,
  UnitIssue,
} from "@/lib/types";

interface FinancialSummary {
  period: string;
  gross_revenue: number;
  operating_expenses: number;
  maintenance_costs: number;
  vacancy_loss: number;
  noi: number;
}

function fmt$(n: number) {
  return "$" + n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

const ISSUE_LABELS: Record<UnitIssue, { label: string; color: string }> = {
  vacant: { label: "Vacant", color: "bg-red-500/20 text-red-300 border-red-500/30" },
  down_for_maintenance: { label: "Down", color: "bg-orange-500/20 text-orange-300 border-orange-500/30" },
  below_market: { label: "Below Market", color: "bg-amber-500/20 text-amber-300 border-amber-500/30" },
  expired_lease: { label: "Expired Lease", color: "bg-red-500/20 text-red-300 border-red-500/30" },
  expiring_soon: { label: "Expiring", color: "bg-yellow-500/20 text-yellow-300 border-yellow-500/30" },
  open_maintenance: { label: "Maint.", color: "bg-sky-500/20 text-sky-300 border-sky-500/30" },
};

type IssueFilter = UnitIssue | "all";

function IssuePill({ issue }: { issue: UnitIssue }) {
  const cfg = ISSUE_LABELS[issue];
  return (
    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${cfg.color}`}>
      {cfg.label}
    </span>
  );
}

function UnitRow({ row, expanded, onToggle }: { row: RentRollRow; expanded: boolean; onToggle: () => void }) {
  const hasIssues = row.issues.length > 0;

  return (
    <>
      <tr
        onClick={onToggle}
        className={`border-b border-zinc-800/30 cursor-pointer transition-colors ${
          hasIssues ? "bg-zinc-800/10 hover:bg-zinc-800/30" : "hover:bg-zinc-800/20"
        }`}
      >
        <td className="px-4 py-2.5">
          <span className="font-mono text-zinc-200 text-sm">{row.unit_number}</span>
        </td>
        <td className="px-4 py-2.5">
          <Badge
            variant={
              row.status === "occupied"
                ? "emerald"
                : row.status === "vacant"
                ? "red"
                : row.status === "maintenance"
                ? "amber"
                : "default"
            }
          >
            {row.status}
          </Badge>
        </td>
        <td className="px-4 py-2.5 text-sm text-zinc-400">
          {row.tenant?.name ?? <span className="text-zinc-600">—</span>}
        </td>
        <td className="px-4 py-2.5 font-mono text-sm text-zinc-300">{fmt$(row.current_rent)}</td>
        <td className="px-4 py-2.5 font-mono text-sm text-zinc-500">{fmt$(row.market_rent)}</td>
        <td className="px-4 py-2.5 text-sm">
          {row.pct_below_market > 0 ? (
            <span className="text-amber-400 font-medium">-{row.pct_below_market}%</span>
          ) : (
            <span className="text-zinc-600">—</span>
          )}
        </td>
        <td className="px-4 py-2.5 text-sm">
          {row.lease ? (
            <span
              className={
                (row.lease.days_to_expiry ?? 999) <= 0
                  ? "text-red-400"
                  : (row.lease.days_to_expiry ?? 999) <= 90
                  ? "text-yellow-400"
                  : "text-zinc-400"
              }
            >
              {row.lease.end_date}
            </span>
          ) : (
            <span className="text-zinc-600">—</span>
          )}
        </td>
        <td className="px-4 py-2.5 text-sm text-center">
          {row.open_maintenance > 0 ? (
            <span className="text-sky-400 font-medium">{row.open_maintenance}</span>
          ) : (
            <span className="text-zinc-700">0</span>
          )}
        </td>
        <td className="px-4 py-2.5">
          <div className="flex flex-wrap gap-1">
            {row.issues.map((issue) => (
              <IssuePill key={issue} issue={issue} />
            ))}
          </div>
        </td>
      </tr>

      {expanded && (
        <tr className="bg-zinc-800/20 border-b border-zinc-800/30">
          <td colSpan={9} className="px-6 py-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-sm">
              {/* Unit details */}
              <div className="space-y-2">
                <h4 className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">Unit</h4>
                <div className="space-y-1 text-zinc-400">
                  {row.bedrooms != null && <p>{row.bedrooms} bed / {row.bathrooms ?? "—"} bath</p>}
                  {row.sqft != null && <p>{row.sqft.toLocaleString()} sq ft</p>}
                  {row.floor != null && <p>Floor {row.floor}</p>}
                  <p>
                    Rent gap:{" "}
                    <span className={row.rent_gap < 0 ? "text-amber-400 font-medium" : "text-emerald-400"}>
                      {fmt$(row.rent_gap)}/mo
                    </span>
                  </p>
                </div>
              </div>

              {/* Lease + tenant */}
              <div className="space-y-2">
                <h4 className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">Lease &amp; Tenant</h4>
                {row.lease && row.tenant ? (
                  <div className="space-y-1 text-zinc-400">
                    <p className="text-zinc-200 font-medium">{row.tenant.name}</p>
                    <p className="text-zinc-500">{row.tenant.email}</p>
                    {row.tenant.phone && <p className="text-zinc-500">{row.tenant.phone}</p>}
                    <p>
                      Lease {row.lease.start_date} → {row.lease.end_date}
                      <Badge variant={row.lease.status === "active" ? "emerald" : "red"} className="ml-2">
                        {row.lease.status}
                      </Badge>
                    </p>
                    <p>Deposit: {fmt$(row.lease.deposit)}</p>
                    {row.lease.days_to_expiry != null && (
                      <p className={row.lease.days_to_expiry <= 30 ? "text-red-400 font-medium" : ""}>
                        {row.lease.days_to_expiry > 0
                          ? `${row.lease.days_to_expiry} days until expiry`
                          : `Expired ${Math.abs(row.lease.days_to_expiry)} days ago`}
                      </p>
                    )}
                  </div>
                ) : (
                  <p className="text-zinc-600">No active lease</p>
                )}
              </div>

              {/* Maintenance */}
              <div className="space-y-2">
                <h4 className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">
                  Open Maintenance ({row.maintenance_items.length})
                </h4>
                {row.maintenance_items.length > 0 ? (
                  <div className="space-y-2">
                    {row.maintenance_items.map((mr) => (
                      <div key={mr.id} className="rounded-lg bg-zinc-900/60 border border-zinc-800/40 px-3 py-2">
                        <div className="flex items-center gap-2">
                          <Badge
                            variant={
                              mr.priority === "emergency"
                                ? "red"
                                : mr.priority === "high"
                                ? "amber"
                                : "default"
                            }
                          >
                            {mr.priority}
                          </Badge>
                          <span className="text-zinc-300 text-sm">{mr.title}</span>
                        </div>
                        <p className="text-xs text-zinc-500 mt-1">
                          {mr.category} · {mr.status}
                          {mr.cost != null && ` · est. ${fmt$(mr.cost)}`}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-zinc-600">None</p>
                )}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export function PropertyDetailView({ propertyId }: { propertyId: string }) {
  const [property, setProperty] = useState<PropertyDetail | null>(null);
  const [rentRoll, setRentRoll] = useState<RentRollResponse | null>(null);
  const [financials, setFinancials] = useState<FinancialSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedUnit, setExpandedUnit] = useState<string | null>(null);
  const [issueFilter, setIssueFilter] = useState<IssueFilter>("all");

  useEffect(() => {
    Promise.all([
      api.getProperty(propertyId),
      api.getRentRoll(propertyId),
    ])
      .then(([prop, roll]) => {
        setProperty(prop);
        setRentRoll(roll);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [propertyId]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-sm text-zinc-600 animate-pulse">Loading property...</div>
      </div>
    );
  }

  if (!property || !rentRoll) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-sm text-zinc-500">Property not found</div>
      </div>
    );
  }

  const latestFin = financials.length > 0 ? financials[financials.length - 1] : null;

  const filteredRows =
    issueFilter === "all"
      ? rentRoll.rows
      : rentRoll.rows.filter((r) => r.issues.includes(issueFilter));

  const issueCounts: Record<UnitIssue, number> = {
    vacant: 0,
    down_for_maintenance: 0,
    below_market: 0,
    expired_lease: 0,
    expiring_soon: 0,
    open_maintenance: 0,
  };
  for (const row of rentRoll.rows) {
    for (const issue of row.issues) {
      issueCounts[issue]++;
    }
  }
  const unitsWithIssues = rentRoll.rows.filter((r) => r.issues.length > 0).length;

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-6xl mx-auto px-8 py-8 space-y-6">
        {/* Breadcrumb + header */}
        <div>
          <Link href="/" className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors">
            &larr; Home
          </Link>
          <h1 className="text-2xl font-bold text-zinc-100 mt-2">{property.name}</h1>
          <div className="flex items-center gap-3 mt-1">
            <Badge variant={property.property_type === "commercial" ? "cyan" : "blue"}>
              {property.property_type}
            </Badge>
            {property.address && (
              <span className="text-sm text-zinc-500">
                {property.address.street}, {property.address.city}
                {property.address.state ? `, ${property.address.state}` : ""}
              </span>
            )}
          </div>
        </div>

        {/* KPI row — revenue-focused */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <MetricCard
            label="Occupancy"
            value={`${rentRoll.total_units > 0 ? Math.round((rentRoll.occupied / rentRoll.total_units) * 100) : 0}%`}
            sub={`${rentRoll.occupied}/${rentRoll.total_units} units`}
            trend={rentRoll.vacant === 0 ? "up" : "down"}
          />
          <MetricCard label="Actual Rent" value={fmt$(rentRoll.total_actual_rent)} />
          <MetricCard label="Market Rent" value={fmt$(rentRoll.total_market_rent)} />
          <MetricCard
            label="Loss to Lease"
            value={fmt$(rentRoll.total_loss_to_lease)}
            alert={rentRoll.total_loss_to_lease > 0}
            sub={
              rentRoll.total_market_rent > 0
                ? `${((rentRoll.total_loss_to_lease / rentRoll.total_market_rent) * 100).toFixed(1)}% of market`
                : undefined
            }
          />
          <MetricCard
            label="Vacancy Loss"
            value={fmt$(rentRoll.total_vacancy_loss)}
            alert={rentRoll.total_vacancy_loss > 0}
            sub={`${rentRoll.vacant} vacant units`}
          />
        </div>

        {/* Financial period (if available) */}
        {latestFin && (
          <section className="rounded-xl border border-zinc-800/60 bg-zinc-900/40 p-5">
            <h2 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-4">
              Financial Period <span className="text-zinc-600 font-normal">&middot; {latestFin.period}</span>
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <div>
                <p className="text-[10px] text-zinc-600">Gross Revenue</p>
                <p className="text-sm font-semibold text-zinc-200">{fmt$(latestFin.gross_revenue)}</p>
              </div>
              <div>
                <p className="text-[10px] text-zinc-600">Expenses</p>
                <p className="text-sm font-semibold text-zinc-200">{fmt$(latestFin.operating_expenses)}</p>
              </div>
              <div>
                <p className="text-[10px] text-zinc-600">Maintenance</p>
                <p className="text-sm font-semibold text-zinc-200">{fmt$(latestFin.maintenance_costs)}</p>
              </div>
              <div>
                <p className="text-[10px] text-zinc-600">Vacancy Loss</p>
                <p className="text-sm font-semibold text-red-400">{fmt$(latestFin.vacancy_loss)}</p>
              </div>
              <div>
                <p className="text-[10px] text-zinc-600">NOI</p>
                <p className="text-sm font-bold text-emerald-400">{fmt$(latestFin.noi)}</p>
              </div>
            </div>
          </section>
        )}

        {/* Issue filter bar */}
        <section className="rounded-xl border border-zinc-800/60 bg-zinc-900/40 overflow-hidden">
          <div className="px-5 py-3 border-b border-zinc-800/40 flex items-center justify-between">
            <h2 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide">
              Rent Roll{" "}
              <span className="text-zinc-600 font-normal">
                &middot; {filteredRows.length} of {rentRoll.rows.length} units
                {unitsWithIssues > 0 && ` · ${unitsWithIssues} with issues`}
              </span>
            </h2>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setIssueFilter("all")}
                className={`text-[10px] px-2 py-1 rounded-md border transition-colors ${
                  issueFilter === "all"
                    ? "bg-zinc-700 border-zinc-600 text-zinc-200"
                    : "border-zinc-800 text-zinc-500 hover:text-zinc-300"
                }`}
              >
                All
              </button>
              {(Object.entries(issueCounts) as [UnitIssue, number][])
                .filter(([, count]) => count > 0)
                .map(([issue, count]) => (
                  <button
                    key={issue}
                    onClick={() => setIssueFilter(issue === issueFilter ? "all" : issue)}
                    className={`text-[10px] px-2 py-1 rounded-md border transition-colors ${
                      issueFilter === issue
                        ? ISSUE_LABELS[issue].color
                        : "border-zinc-800 text-zinc-500 hover:text-zinc-300"
                    }`}
                  >
                    {ISSUE_LABELS[issue].label} ({count})
                  </button>
                ))}
            </div>
          </div>

          {/* Rent roll table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800/60">
                  {["Unit", "Status", "Tenant", "Rent", "Market", "Gap", "Lease End", "Maint", "Issues"].map(
                    (h) => (
                      <th
                        key={h}
                        className="text-left px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide"
                      >
                        {h}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => (
                  <UnitRow
                    key={row.unit_id}
                    row={row}
                    expanded={expandedUnit === row.unit_id}
                    onToggle={() =>
                      setExpandedUnit(expandedUnit === row.unit_id ? null : row.unit_id)
                    }
                  />
                ))}
                {filteredRows.length === 0 && (
                  <tr>
                    <td colSpan={9} className="text-center py-12 text-sm text-zinc-600">
                      No units match the selected filter
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
