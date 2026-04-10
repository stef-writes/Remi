"use client";

import { pct } from "@/lib/format";

interface Thresholds {
  ok: number;
  warn: number;
}

interface Props {
  rate: number;
  size?: number;
  label?: string;
  thresholds?: Thresholds;
}

export function HealthRing({
  rate,
  size = 140,
  label = "occupied",
  thresholds = { ok: 0.95, warn: 0.9 },
}: Props) {
  const stroke = 10;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const filled = circumference * Math.min(Math.max(rate, 0), 1);
  const color =
    rate >= thresholds.ok
      ? "stroke-ok"
      : rate >= thresholds.warn
        ? "stroke-warn"
        : "stroke-error";

  return (
    <div className="relative ring-pulse" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          className="text-border-subtle"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circumference - filled}`}
          className={`${color} transition-all duration-1000`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-bold text-fg tracking-tight" style={{ fontSize: Math.round(size * 0.21) }}>{pct(rate)}</span>
        <span className="text-fg-faint uppercase tracking-widest" style={{ fontSize: Math.max(7, Math.round(size * 0.085)) }}>{label}</span>
      </div>
    </div>
  );
}
