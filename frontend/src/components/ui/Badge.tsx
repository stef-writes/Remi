"use client";

const VARIANTS: Record<string, string> = {
  default: "bg-zinc-800 text-zinc-400",
  blue: "bg-blue-500/15 text-blue-400",
  violet: "bg-violet-500/15 text-violet-400",
  amber: "bg-amber-500/15 text-amber-400",
  emerald: "bg-emerald-500/15 text-emerald-400",
  red: "bg-red-500/15 text-red-400",
  cyan: "bg-cyan-500/15 text-cyan-400",
};

export function Badge({
  children,
  variant = "default",
  className = "",
}: {
  children: React.ReactNode;
  variant?: keyof typeof VARIANTS;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-mono font-medium ${VARIANTS[variant] ?? VARIANTS.default} ${className}`}
    >
      {children}
    </span>
  );
}
