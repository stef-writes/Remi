"use client";

const COLORS: Record<string, string> = {
  idle: "#52525b",
  running: "#3b82f6",
  done: "#22c55e",
  completed: "#22c55e",
  error: "#ef4444",
  failed: "#ef4444",
  pending: "#71717a",
  skipped: "#71717a",
  calling: "#f59e0b",
  connected: "#22c55e",
  disconnected: "#ef4444",
};

export function StatusDot({
  status,
  size = 8,
  pulse = false,
}: {
  status: string;
  size?: number;
  pulse?: boolean;
}) {
  const color = COLORS[status] ?? COLORS.idle;
  const shouldPulse = pulse || status === "running" || status === "calling";

  return (
    <span className="relative inline-flex" style={{ width: size, height: size }}>
      {shouldPulse && (
        <span
          className="absolute inset-0 rounded-full animate-ping opacity-40"
          style={{ backgroundColor: color }}
        />
      )}
      <span
        className="relative inline-flex rounded-full w-full h-full"
        style={{ backgroundColor: color }}
      />
    </span>
  );
}
