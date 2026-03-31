"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useSessions } from "@/hooks/useSessions";
import { SessionThread } from "./SessionThread";
import { SessionInput } from "./SessionInput";
import { SessionSidebar } from "./SessionSidebar";
import { SessionEmptyState } from "./SessionEmptyState";
import { ThreadSkeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import type { AgentMeta, ManagerListItem, ModelsConfig } from "@/lib/types";

const FALLBACK_AGENT = "director";

export function AskView() {
  const [agents, setAgents] = useState<AgentMeta[]>([]);
  const [agent, setAgent] = useState(FALLBACK_AGENT);
  const [modelsConfig, setModelsConfig] = useState<ModelsConfig | null>(null);
  const [provider, setProvider] = useState("anthropic");
  const [model, setModel] = useState("claude-sonnet-4-20250514");
  const [mode, setMode] = useState<"ask" | "agent">("ask");
  const [managers, setManagers] = useState<ManagerListItem[]>([]);
  const [managerId, setManagerId] = useState("");
  const [showWorkDetails, setShowWorkDetails] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const lastSendRef = useRef<{ text: string; mode: "ask" | "agent" } | null>(null);

  useEffect(() => {
    api.listAgents().then((list) => {
      if (!list.length) return;
      setAgents(list);
      const primary = list.find((a) => a.primary) ?? list[0];
      setAgent(primary.name);
    }).catch(() => {});

    api.listModels().then((cfg) => {
      setModelsConfig(cfg);
      setProvider(cfg.default_provider);
      setModel(cfg.default_model);
    }).catch(() => {});

    api.listManagers().then(setManagers).catch(() => {});
  }, []);

  const {
    connected,
    sessions,
    activeSessionId,
    activeSession,
    createSession,
    selectSession,
    send,
    deleteSession: _deleteSession,
    dismissError,
    stopGenerating,
  } = useSessions(agent);

  const handleSend = (text: string, sendMode?: "ask" | "agent") => {
    const m = sendMode ?? mode;
    lastSendRef.current = { text, mode: m };
    send(text, m, { provider, model, managerId: managerId || undefined });
  };

  const handleRetry = () => {
    if (!lastSendRef.current) {
      const session = activeSession;
      if (!session) return;
      const lastUser = [...session.messages].reverse().find((m) => m.role === "user");
      if (lastUser) {
        send(lastUser.content, mode, { provider, model, managerId: managerId || undefined });
      }
      return;
    }
    send(lastSendRef.current.text, lastSendRef.current.mode, { provider, model, managerId: managerId || undefined });
  };

  const closeSidebar = useCallback(() => setSidebarOpen(false), []);

  const session = activeSession;
  const hasMessages = (session?.messages.length ?? 0) > 0;

  return (
    <div className="h-full flex flex-col relative bg-surface">
      {/* Top bar */}
      <div className="shrink-0 h-11 flex items-center px-4 gap-3 border-b border-border-subtle">
        <button
          onClick={() => setSidebarOpen(true)}
          className="p-1.5 rounded-lg text-fg-faint hover:text-fg-secondary hover:bg-surface-sunken transition-all"
          title="History"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </button>

        {agents.length > 1 && (
          <div className="flex gap-0.5 bg-surface-sunken rounded-lg p-0.5">
            {agents.map((a) => (
              <button
                key={a.name}
                onClick={() => setAgent(a.name)}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all capitalize ${
                  agent === a.name
                    ? "bg-surface text-fg shadow-sm"
                    : "text-fg-muted hover:text-fg-secondary"
                }`}
              >
                {a.name}
              </button>
            ))}
          </div>
        )}

        <div className="flex-1" />

        {activeSessionId && (
          <button
            onClick={createSession}
            className="p-1.5 rounded-lg text-fg-faint hover:text-fg-secondary hover:bg-surface-sunken transition-all"
            title="New conversation"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
          </button>
        )}

        <div className="flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-ok" : "bg-error"}`} />
          <span className="text-[10px] text-fg-faint">{connected ? "Live" : "Offline"}</span>
        </div>
      </div>

      {/* Error banner */}
      {session?.error && !hasMessages && (
        <div className="shrink-0 mx-4 mt-3 px-4 py-2.5 rounded-xl bg-error-soft border border-error/20 flex items-center justify-between">
          <span className="text-sm text-error-fg">{session.error}</span>
          <button onClick={dismissError} className="text-[10px] text-error/60 hover:text-error ml-4 shrink-0">
            dismiss
          </button>
        </div>
      )}

      {/* Content */}
      {activeSessionId && session && !session.loaded ? (
        <ThreadSkeleton />
      ) : !activeSession || !hasMessages ? (
        <SessionEmptyState
          onSend={(text) => handleSend(text)}
          connected={connected}
          streaming={session?.streaming ?? false}
          mode={mode}
          managerName={managers.find((m) => m.id === managerId)?.name}
        />
      ) : (
        <SessionThread
          messages={session!.messages}
          liveContent={session!.liveContent}
          liveTools={session!.liveTools}
          streaming={session!.streaming}
          showWorkDetails={showWorkDetails}
          onRetry={handleRetry}
        />
      )}

      {/* Input */}
      <SessionInput
        onSend={handleSend}
        streaming={session?.streaming ?? false}
        connected={connected}
        mode={mode}
        onModeChange={setMode}
        hasMessages={hasMessages}
        showWorkDetails={showWorkDetails}
        onToggleWorkDetails={() => setShowWorkDetails((v) => !v)}
        onStop={stopGenerating}
        managers={managers}
        managerId={managerId}
        onManagerChange={setManagerId}
      />

      <SessionSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelect={selectSession}
        onCreate={createSession}
        open={sidebarOpen}
        onClose={closeSidebar}
      />
    </div>
  );
}
