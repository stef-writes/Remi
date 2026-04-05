"use client";

import { useEffect, type ReactNode } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  title?: string;
  width?: "sm" | "md" | "lg" | "xl";
  children: ReactNode;
}

const WIDTHS = {
  sm: "sm:max-w-sm",
  md: "sm:max-w-md",
  lg: "sm:max-w-lg",
  xl: "sm:max-w-xl",
};

export function SlidePanel({ open, onClose, title, width = "lg", children }: Props) {
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div
        className="absolute inset-0 bg-fg/10 drawer-overlay"
        onClick={onClose}
      />
      <div
        className={`relative w-full ${WIDTHS[width]} h-full bg-surface border-l border-border shadow-2xl drawer-panel flex flex-col`}
      >
        <div className="flex items-center justify-between px-4 sm:px-6 py-3 sm:py-4 border-b border-border-subtle shrink-0">
          {title && (
            <h2 className="text-sm font-semibold text-fg truncate mr-2">{title}</h2>
          )}
          <button
            onClick={onClose}
            className="ml-auto w-8 h-8 sm:w-7 sm:h-7 rounded-lg flex items-center justify-center text-fg-muted hover:text-fg hover:bg-surface-sunken transition-colors shrink-0"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4 sm:py-5">
          {children}
        </div>
      </div>
    </div>
  );
}
