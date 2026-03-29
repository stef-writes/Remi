"use client";

interface Props {
  label: string;
  value: string | number;
  sub?: string;
  trend?: "up" | "down" | "flat";
  alert?: boolean;
}

export function MetricCard({ label, value, sub, trend, alert }: Props) {
  return (
    <div
      className={`rounded-xl border px-5 py-4 ${
        alert
          ? "border-amber-500/30 bg-amber-500/5"
          : "border-zinc-800/60 bg-zinc-900/40"
      }`}
    >
      <p className="text-[11px] font-medium text-zinc-500 uppercase tracking-wide mb-1">
        {label}
      </p>
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-bold text-zinc-100">
          {typeof value === "number" ? value.toLocaleString() : value}
        </span>
        {trend && (
          <span
            className={`text-xs font-semibold ${
              trend === "up"
                ? "text-emerald-400"
                : trend === "down"
                ? "text-red-400"
                : "text-zinc-500"
            }`}
          >
            {trend === "up" ? "↑" : trend === "down" ? "↓" : "→"}
          </span>
        )}
      </div>
      {sub && <p className="text-[11px] text-zinc-600 mt-1">{sub}</p>}
    </div>
  );
}
