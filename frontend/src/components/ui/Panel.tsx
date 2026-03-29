"use client";

import { type ReactNode } from "react";

export function Panel({
  children,
  className = "",
  padding = true,
}: {
  children: ReactNode;
  className?: string;
  padding?: boolean;
}) {
  return (
    <div
      className={`rounded-xl border border-zinc-800/60 bg-zinc-900/40 backdrop-blur-sm ${
        padding ? "p-5" : ""
      } ${className}`}
    >
      {children}
    </div>
  );
}

export function PanelHeader({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex items-center justify-between mb-4 ${className}`}>
      {children}
    </div>
  );
}

export function PanelTitle({ children }: { children: ReactNode }) {
  return (
    <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-500">
      {children}
    </h2>
  );
}
