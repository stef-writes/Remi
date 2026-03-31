"use client";

import type { SessionSummary } from "@/lib/types";
import { StatusDot } from "@/components/ui/StatusDot";

function relativeTime(iso: string): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export function SessionSidebar({
  sessions,
  activeSessionId,
  onSelect,
  onCreate,
}: {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
}) {
  return (
    <div className="w-64 shrink-0 bg-zinc-950 border-r border-zinc-800/60 flex flex-col h-full">
      <div className="shrink-0 p-3">
        <button
          onClick={onCreate}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-zinc-800/50 border border-zinc-800/60 text-sm text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          New session
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-3 space-y-0.5">
        {sessions.map((s) => {
          const active = s.id === activeSessionId;
          return (
            <button
              key={s.id}
              onClick={() => onSelect(s.id)}
              className={`w-full text-left px-3 py-2.5 rounded-lg transition-colors ${
                active
                  ? "bg-zinc-800/70 text-zinc-100"
                  : "text-zinc-500 hover:bg-zinc-800/30 hover:text-zinc-300"
              }`}
            >
              <div className="flex items-center gap-2">
                {s.streaming && <StatusDot status="running" size={5} pulse />}
                <span className="text-xs font-medium truncate flex-1">
                  {s.preview || "New session"}
                </span>
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-[10px] text-zinc-700">
                  {relativeTime(s.updatedAt || s.createdAt)}
                </span>
                {s.messageCount > 0 && (
                  <span className="text-[10px] text-zinc-700">
                    {s.messageCount} msg{s.messageCount !== 1 ? "s" : ""}
                  </span>
                )}
              </div>
            </button>
          );
        })}

        {sessions.length === 0 && (
          <p className="text-[11px] text-zinc-700 text-center py-6">
            No sessions yet
          </p>
        )}
      </div>
    </div>
  );
}
