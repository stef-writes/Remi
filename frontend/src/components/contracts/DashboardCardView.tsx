"use client";

import type { DashboardCard } from "@/lib/types";

const SEVERITY_COLORS: Record<string, string> = {
  info: "border-blue-500/30 bg-blue-500/5",
  warning: "border-amber-500/30 bg-amber-500/5",
  critical: "border-red-500/30 bg-red-500/5",
};

const TREND_ICONS: Record<string, string> = {
  up: "↑",
  down: "↓",
  flat: "→",
};

export function DashboardCardView({ data }: { data: DashboardCard }) {
  const severity = data.severity ?? "info";
  const colorClass = SEVERITY_COLORS[severity] || SEVERITY_COLORS.info;
  const trend = data.trend_direction ? TREND_ICONS[data.trend_direction] : null;

  return (
    <div
      className={`rounded-xl border p-6 ${colorClass} transition-all hover:scale-[1.02]`}
    >
      <p className="text-sm font-medium text-zinc-400 uppercase tracking-wide">
        {data.title}
      </p>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="text-4xl font-bold text-zinc-100">
          {typeof data.value === "number" ? data.value.toLocaleString() : data.value}
        </span>
        {data.unit && (
          <span className="text-lg text-zinc-400">{data.unit}</span>
        )}
        {trend && (
          <span
            className={`text-lg font-semibold ${
              data.trend_direction === "up"
                ? "text-emerald-400"
                : data.trend_direction === "down"
                ? "text-red-400"
                : "text-zinc-400"
            }`}
          >
            {trend} {data.trend}
          </span>
        )}
      </div>
    </div>
  );
}
