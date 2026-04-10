"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { useSessions } from "@/hooks/useSessions";
import { SessionThread } from "./SessionThread";
import { SessionInput } from "./SessionInput";
import { SessionSidebar } from "./SessionSidebar";
import { SessionEmptyState } from "./SessionEmptyState";
import { ResearchArtifact } from "./ResearchArtifact";
import { ThreadSkeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import type { ManagerListItem, ResearchArtifact as ResearchArtifactType } from "@/lib/types";

type AgentMode = "director" | "researcher";

export function AskView() {
  const searchParams = useSearchParams();
  const [provider, setProvider] = useState("anthropic");
  const [model, setModel] = useState("claude-sonnet-4-20250514");
  const [managers, setManagers] = useState<ManagerListItem[]>([]);
  const [managerId, setManagerId] = useState("");
  const [showWorkDetails, setShowWorkDetails] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [activeArtifact, setActiveArtifact] = useState<ResearchArtifactType | null>(null);
  const [agentMode, setAgentMode] = useState<AgentMode>("director");
  const initialQuerySent = useRef(false);

  const lastSendRef = useRef<string | null>(null);

  useEffect(() => {
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
    dismissError,
    stopGenerating,
  } = useSessions(agentMode);

  const handleModeSwitch = useCallback((mode: AgentMode) => {
    if (mode === agentMode) return;
    setAgentMode(mode);
    setActiveArtifact(null);
    createSession();
  }, [agentMode, createSession]);

  useEffect(() => {
    const q = searchParams.get("q");
    if (q && !initialQuerySent.current && connected) {
      initialQuerySent.current = true;
      send(q, "ask", { provider, model, managerId: managerId || undefined });
    }
  }, [searchParams, connected, send, provider, model, managerId]);

  const handleSend = (text: string) => {
    lastSendRef.current = text;
    send(text, "ask", { provider, model, managerId: managerId || undefined });
  };

  const handleRetry = () => {
    if (!lastSendRef.current) {
      const session = activeSession;
      if (!session) return;
      const lastUser = [...session.messages].reverse().find((m) => m.role === "user");
      if (lastUser) {
        send(lastUser.content, "ask", { provider, model, managerId: managerId || undefined });
      }
      return;
    }
    send(lastSendRef.current, "ask", { provider, model, managerId: managerId || undefined });
  };

  const closeSidebar = useCallback(() => setSidebarOpen(false), []);

  const session = activeSession;
  const hasMessages = (session?.messages.length ?? 0) > 0;

  // Pop the latest live artifact into the artifact panel as soon as it arrives.
  const liveArtifacts = session?.liveArtifacts ?? [];
  useEffect(() => {
    if (liveArtifacts.length > 0) {
      setActiveArtifact(liveArtifacts[liveArtifacts.length - 1]);
    }
  }, [liveArtifacts.length]); // eslint-disable-line react-hooks/exhaustive-deps

  // Surface artifacts from past messages when the thread loads.
  useEffect(() => {
    if (!session?.loaded) return;
    for (let i = session.messages.length - 1; i >= 0; i--) {
      const arts = session.messages[i].artifacts;
      if (arts && arts.length > 0) {
        setActiveArtifact(arts[arts.length - 1]);
        break;
      }
    }
  }, [session?.loaded]); // eslint-disable-line react-hooks/exhaustive-deps

  const artifactOpen = activeArtifact !== null;

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

        <div className="flex-1" />

        {/* Mode toggle */}
        <div className="flex items-center rounded-lg bg-surface-sunken p-0.5 gap-0.5">
          <button
            onClick={() => handleModeSwitch("director")}
            className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${
              agentMode === "director"
                ? "bg-surface text-fg shadow-sm"
                : "text-fg-faint hover:text-fg-secondary"
            }`}
          >
            Ask
          </button>
          <button
            onClick={() => handleModeSwitch("researcher")}
            className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${
              agentMode === "researcher"
                ? "bg-surface text-amber-500 shadow-sm"
                : "text-fg-faint hover:text-fg-secondary"
            }`}
            title="Deep Research — statistical analysis, multi-phase reports. ~$0.20–$1.35 per run."
          >
            Research
          </button>
        </div>

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

      {/* Content — split-panel when artifact is present */}
      {activeSessionId && session && !session.loaded ? (
        <ThreadSkeleton />
      ) : !activeSession || !hasMessages ? (
        <SessionEmptyState
          onSend={handleSend}
          connected={connected}
          streaming={session?.streaming ?? false}
          mode={agentMode === "researcher" ? "research" : "ask"}
          managerName={managers.find((m) => m.id === managerId)?.name}
        />
      ) : (
        <div className={`flex-1 min-h-0 flex ${artifactOpen ? "overflow-hidden" : ""}`}>
          <div className={`flex flex-col min-w-0 ${artifactOpen ? "flex-1" : "flex-1"}`}>
            <SessionThread
              messages={session!.messages}
              liveContent={session!.liveContent}
              liveTools={session!.liveTools}
              livePhase={session!.livePhase}
              liveArtifacts={liveArtifacts}
              streaming={session!.streaming}
              showWorkDetails={showWorkDetails}
              onRetry={handleRetry}
            />
          </div>
          {artifactOpen && activeArtifact && (
            <div className="w-[400px] xl:w-[480px] shrink-0 border-l border-border overflow-y-auto">
              <ResearchArtifact
                artifact={activeArtifact}
                onClose={() => setActiveArtifact(null)}
              />
            </div>
          )}
        </div>
      )}

      {/* Input */}
      <SessionInput
        onSend={handleSend}
        streaming={session?.streaming ?? false}
        connected={connected}
        hasMessages={hasMessages}
        showWorkDetails={showWorkDetails}
        onToggleWorkDetails={() => setShowWorkDetails((v) => !v)}
        onStop={stopGenerating}
        managers={managers}
        managerId={managerId}
        onManagerChange={setManagerId}
        mode={agentMode === "researcher" ? "research" : "ask"}
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
