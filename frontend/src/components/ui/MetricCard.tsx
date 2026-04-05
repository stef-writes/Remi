"use client";

interface Props {
  label: string;
  value: string | number;
  sub?: string;
  trend?: "up" | "down" | "flat";
  alert?: boolean;
}

export function MetricCard({ label, value, sub, trend, alert }: Props) {
  const display = typeof value === "number" ? value.toLocaleString() : value;

  return (
    <div
      className={`rounded-2xl border min-w-0 overflow-hidden px-4 py-3.5 sm:px-5 sm:py-4 card-hover ${
        alert
          ? "border-warn/30 bg-warn-soft"
          : "border-border bg-surface"
      }`}
    >
      <p className="text-[10px] sm:text-[11px] font-medium text-fg-muted uppercase tracking-wide mb-1 truncate">
        {label}
      </p>
      <div className="flex items-baseline gap-1.5 min-w-0">
        <span className="text-lg sm:text-2xl font-bold text-fg truncate tracking-tight">
          {display}
        </span>
        {trend && (
          <span
            className={`text-xs font-semibold shrink-0 ${
              trend === "up"
                ? "text-ok"
                : trend === "down"
                ? "text-error"
                : "text-fg-muted"
            }`}
          >
            {trend === "up" ? "↑" : trend === "down" ? "↓" : "→"}
          </span>
        )}
      </div>
      {sub && <p className="text-[10px] sm:text-[11px] text-fg-faint mt-0.5 truncate">{sub}</p>}
    </div>
  );
}
