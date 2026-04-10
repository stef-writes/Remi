"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ManagerListItem } from "@/lib/types";

export function SessionInput({
  onSend,
  streaming,
  connected,
  hasMessages,
  showWorkDetails,
  onToggleWorkDetails,
  onStop,
  managers,
  managerId,
  onManagerChange,
  mode = "ask",
}: {
  onSend: (text: string) => void;
  streaming: boolean;
  connected: boolean;
  hasMessages: boolean;
  showWorkDetails: boolean;
  onToggleWorkDetails: () => void;
  onStop?: () => void;
  managers?: ManagerListItem[];
  managerId?: string;
  onManagerChange?: (id: string) => void;
  mode?: "ask" | "research";
}) {
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    const msg = input.trim();
    if (!msg || streaming || !connected) return;
    onSend(msg);
    setInput("");
    if (inputRef.current) inputRef.current.style.height = "auto";
  };

  const autoResize = useCallback(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    const maxHeight = 140;
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
    el.style.overflowY = el.scrollHeight > maxHeight ? "auto" : "hidden";
  }, []);

  useEffect(() => { autoResize(); }, [input, autoResize]);

  const selectedManager = managers?.find((m) => m.id === managerId);
  const placeholders = connected
    ? selectedManager
      ? mode === "research"
        ? [
            `Write a full performance review for ${selectedManager.name}`,
            `Analyze delinquency trends across ${selectedManager.name}'s portfolio`,
            `Generate a lease expiry risk report for ${selectedManager.name}`,
          ]
        : [
            `How is ${selectedManager.name} doing?`,
            `Any issues with ${selectedManager.name}'s properties?`,
            "What's their occupancy looking like?",
          ]
      : mode === "research"
        ? [
            "Write a full delinquency analysis across all managers",
            "Compare manager performance over the last 90 days",
            "Which properties carry the highest vacancy risk?",
          ]
        : [
            "How's my portfolio looking today?",
            "Anything I should worry about?",
            "Which managers are crushing it?",
            "Are any managers actually doing a good job?",
          ]
    : ["Connecting..."];

  const [placeholderIdx] = useState(() => Math.floor(Math.random() * placeholders.length));

  return (
    <div className="shrink-0 pb-5 pt-2">
      <div className="max-w-2xl mx-auto px-4">
        <div className="rounded-2xl bg-surface border border-border shadow-sm transition-all focus-within:border-accent/30 focus-within:shadow-md">
          <div className="flex items-end gap-2 p-3">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
              }}
              placeholder={placeholders[placeholderIdx]}
              disabled={streaming || !connected}
              rows={1}
              className="flex-1 py-1 bg-transparent text-fg placeholder-fg-faint focus:outline-none text-sm resize-none disabled:opacity-40 overflow-hidden"
            />
            {streaming && onStop ? (
              <button
                onClick={onStop}
                className="shrink-0 w-8 h-8 rounded-xl flex items-center justify-center bg-surface-sunken hover:bg-border text-fg-muted transition-all"
                title="Stop"
              >
                <svg className="w-3 h-3" viewBox="0 0 16 16" fill="currentColor">
                  <rect x="3.5" y="3.5" width="9" height="9" rx="1.5" />
                </svg>
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!input.trim() || streaming || !connected}
                className="shrink-0 w-8 h-8 rounded-xl flex items-center justify-center transition-all disabled:opacity-20 disabled:cursor-default bg-accent hover:bg-accent-hover text-accent-fg"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 10.5L12 3m0 0l7.5 7.5M12 3v18" />
                </svg>
              </button>
            )}
          </div>

          <div className="flex items-center justify-between px-3 pb-2.5">
            <div className="flex items-center gap-2">
              {managers && managers.length > 0 && onManagerChange && (
                <select
                  value={managerId ?? ""}
                  onChange={(e) => onManagerChange(e.target.value)}
                  className="bg-surface-sunken rounded-full px-3 py-1 text-xs font-medium text-fg-muted focus:outline-none focus:text-fg transition-all border-none cursor-pointer max-w-[180px] truncate"
                >
                  <option value="">All managers</option>
                  {managers
                    .filter((m) => m.metrics.total_units > 0 || m.property_count > 0)
                    .map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name}
                      </option>
                    ))}
                </select>
              )}
            </div>
            <div className="flex items-center gap-2">
              {hasMessages && (
                <button
                  onClick={onToggleWorkDetails}
                  className="text-[10px] text-fg-faint hover:text-fg-secondary transition-colors"
                >
                  {showWorkDetails ? "Hide work" : "Show work"}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
