"use client";

import Link from "next/link";
import { api } from "@/lib/api";
import { fmt$ } from "@/lib/format";
import { useApiQuery } from "@/hooks/useApiQuery";
import type { ManagerListItem } from "@/lib/types";

function getTimeOfDay(): "morning" | "afternoon" | "evening" {
  const h = new Date().getHours();
  if (h < 12) return "morning";
  if (h < 17) return "afternoon";
  return "evening";
}

function formatDate(): string {
  return new Date().toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

function buildOneLiner(managers: ManagerListItem[]): { text: string; tone: "good" | "neutral" | "warn" } | null {
  const active = managers.filter((m) => m.total_units > 0);
  if (active.length === 0) return null;

  const totalUnits = active.reduce((s, m) => s + m.total_units, 0);
  const totalOccupied = active.reduce((s, m) => s + m.occupied, 0);
  const avgOcc = totalUnits > 0 ? totalOccupied / totalUnits : 0;
  const totalVacant = active.reduce((s, m) => s + m.vacant, 0);
  const totalExpired = active.reduce((s, m) => s + m.expired_leases, 0);
  const totalExpiring = active.reduce((s, m) => s + m.expiring_leases_90d, 0);
  const totalEmergency = active.reduce((s, m) => s + m.emergency_maintenance, 0);
  const totalLTL = active.reduce((s, m) => s + m.total_loss_to_lease, 0);

  const flags: string[] = [];

  if (totalEmergency > 0) flags.push(`${totalEmergency} emergency work order${totalEmergency > 1 ? "s" : ""}`);
  if (totalExpired > 0) flags.push(`${totalExpired} expired lease${totalExpired > 1 ? "s" : ""}`);
  if (totalVacant > 3) flags.push(`${totalVacant} vacancies`);
  if (totalExpiring > 5) flags.push(`${totalExpiring} leases expiring soon`);
  if (totalLTL > 5000) flags.push(`${fmt$(totalLTL)}/mo in lost rent`);

  const occPct = (avgOcc * 100).toFixed(1);

  if (flags.length === 0) {
    return {
      text: `${occPct}% occupied across ${totalUnits.toLocaleString()} units. Nothing urgent.`,
      tone: "good",
    };
  }

  if (flags.length === 1) {
    return {
      text: `${occPct}% occupied — but ${flags[0]}.`,
      tone: "warn",
    };
  }

  return {
    text: `${occPct}% occupied. Heads up: ${flags.slice(0, 2).join(" and ")}.`,
    tone: "warn",
  };
}

const TONE_DOT: Record<string, string> = {
  good: "bg-ok",
  neutral: "bg-fg-faint",
  warn: "bg-warn",
};

export function DashboardBrief() {
  const { data, loading } = useApiQuery<ManagerListItem[]>(
    () => api.listManagers().catch(() => []),
    []
  );
  const managers = data ?? [];

  const timeOfDay = getTimeOfDay();
  const brief = buildOneLiner(managers);

  return (
    <div className="h-full flex items-center justify-center">
      <div className="max-w-md w-full px-6">
        <div className="w-8 h-0.5 rounded-full bg-accent/30 mb-6" />

        <p className="text-xs text-fg-faint tracking-wide">{formatDate()}</p>

        <h1 className="text-xl font-medium text-fg mt-1 tracking-tight">
          {timeOfDay === "morning" ? "Good morning." : timeOfDay === "afternoon" ? "Good afternoon." : "Good evening."}
        </h1>

        {/* The brief */}
        {loading && (
          <div className="mt-5">
            <div className="h-4 w-3/4 bg-surface-sunken rounded animate-pulse" />
          </div>
        )}

        {!loading && brief && (
          <div className="mt-5 flex items-start gap-2.5">
            <span className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${TONE_DOT[brief.tone]}`} />
            <p className="text-sm text-fg-secondary leading-relaxed">{brief.text}</p>
          </div>
        )}

        {!loading && !brief && (
          <p className="mt-5 text-sm text-fg-faint">No data yet. Upload some reports to get started.</p>
        )}

        {/* Quick links */}
        <div className="mt-8 flex gap-3">
          <Link
            href="/ask"
            className="text-xs text-accent hover:text-accent-hover transition-colors"
          >
            Ask REMI →
          </Link>
          <Link
            href="/"
            className="text-xs text-fg-faint hover:text-fg-secondary transition-colors"
          >
            View managers
          </Link>
        </div>
      </div>
    </div>
  );
}
