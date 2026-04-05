"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatMessage, SessionSummary, ToolCall, UsageInfo } from "@/lib/types";

let _msgSeq = 0;
function msgId(): string {
  return `msg-${Date.now()}-${++_msgSeq}`;
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface SessionState {
  messages: ChatMessage[];
  liveContent: string;
  liveTools: ToolCall[];
  streaming: boolean;
  error: string | null;
  loaded: boolean;
}

function emptySessionState(): SessionState {
  return {
    messages: [],
    liveContent: "",
    liveTools: [],
    streaming: false,
    error: null,
    loaded: false,
  };
}

export function useSessions(agent: string) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessionStates, setSessionStates] = useState<Map<string, SessionState>>(new Map());
  const toolTimers = useRef<Map<string, number>>(new Map());

  const abortRef = useRef<AbortController | null>(null);
  const sessionStatesRef = useRef(sessionStates);
  sessionStatesRef.current = sessionStates;

  const activeSessionIdRef = useRef(activeSessionId);
  activeSessionIdRef.current = activeSessionId;

  const updateState = useCallback(
    (sid: string, updater: (prev: SessionState) => SessionState) => {
      setSessionStates((map) => {
        const next = new Map(map);
        next.set(sid, updater(map.get(sid) ?? emptySessionState()));
        return next;
      });
    },
    [],
  );

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/agents/sessions`)
      .then((r) => r.json())
      .then((data) => {
        const list = (data.sessions ?? []) as Array<Record<string, unknown>>;
        setSessions(
          list.map((s) => ({
            id: s.session_id as string,
            agent: s.agent as string,
            messageCount: (s.message_count as number) ?? 0,
            preview: "",
            createdAt: s.created_at as string,
            updatedAt: s.updated_at as string,
            streaming: false,
          })),
        );
      })
      .catch(() => {});
  }, []);

  const createSession = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/agents/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent }),
      });
      const data = await res.json();
      const sid = data.session_id as string;
      const now = new Date().toISOString();
      const summary: SessionSummary = {
        id: sid,
        agent,
        messageCount: 0,
        preview: "",
        createdAt: now,
        updatedAt: now,
        streaming: false,
      };
      setSessions((prev) => [summary, ...prev]);
      setSessionStates((map) => {
        const next = new Map(map);
        next.set(sid, { ...emptySessionState(), loaded: true });
        return next;
      });
      setActiveSessionId(sid);
    } catch (err) {
      console.warn("[useSessions] createSession failed:", err);
    }
  }, [agent]);

  const selectSession = useCallback(
    async (sid: string) => {
      setActiveSessionId(sid);
      const state = sessionStatesRef.current.get(sid);
      if (state?.loaded) return;

      try {
        const res = await fetch(`${API_BASE}/api/v1/agents/sessions/${sid}`);
        const data = await res.json();
        const rawMessages = (data.messages ?? []) as Array<Record<string, unknown>>;
        const messages: ChatMessage[] = rawMessages.map((m) => ({
          id: msgId(),
          role: m.role as "user" | "assistant",
          content: (m.content as string) ?? "",
          timestamp: 0,
        }));
        updateState(sid, (s) => ({ ...s, messages, loaded: true }));

        const firstUser = messages.find((m) => m.role === "user");
        if (firstUser) {
          setSessions((prev) =>
            prev.map((ss) =>
              ss.id === sid ? { ...ss, preview: firstUser.content.slice(0, 80) } : ss,
            ),
          );
        }
      } catch (err) {
        console.warn("[useSessions] selectSession/history failed:", err);
        updateState(sid, (s) => ({ ...s, loaded: true }));
      }
    },
    [updateState],
  );

  const send = useCallback(
    async (
      text: string,
      mode: "ask" | "research" | "agent" = "agent",
      opts?: { provider?: string; model?: string; managerId?: string },
    ) => {
      let sid = activeSessionIdRef.current;

      if (!sid) {
        try {
          const res = await fetch(`${API_BASE}/api/v1/agents/sessions`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              agent,
              ...(opts?.provider && { provider: opts.provider }),
              ...(opts?.model && { model: opts.model }),
            }),
          });
          const data = await res.json();
          sid = data.session_id as string;
          const now = new Date().toISOString();
          const summary: SessionSummary = {
            id: sid,
            agent,
            messageCount: 0,
            preview: text.slice(0, 80),
            createdAt: now,
            updatedAt: now,
            streaming: true,
          };
          setSessions((prev) => [summary, ...prev]);
          setSessionStates((map) => {
            const next = new Map(map);
            next.set(sid!, { ...emptySessionState(), loaded: true });
            return next;
          });
          setActiveSessionId(sid);
        } catch (err) {
          console.warn("[useSessions] send: session creation failed:", err);
          return;
        }
      }

      const sessionId = sid;

      updateState(sessionId, (s) => ({
        ...s,
        streaming: true,
        error: null,
        liveTools: [],
        liveContent: "",
        messages: [
          ...s.messages,
          { id: msgId(), role: "user" as const, content: text, timestamp: Date.now() },
        ],
      }));

      setSessions((prev) =>
        prev.map((ss) => {
          if (ss.id !== sessionId) return ss;
          return {
            ...ss,
            streaming: true,
            messageCount: ss.messageCount + 1,
            preview: ss.preview || text.slice(0, 80),
            updatedAt: new Date().toISOString(),
          };
        }),
      );

      if (abortRef.current) abortRef.current.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const res = await fetch(`${API_BASE}/api/v1/agents/${agent}/ask`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question: text,
            session_id: sessionId,
            mode,
            ...(opts?.managerId && { manager_id: opts.managerId }),
          }),
          signal: controller.signal,
        });

        if (!res.ok || !res.body) {
          throw new Error(`Ask failed: ${res.statusText}`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.trim()) continue;
            try {
              const evt = JSON.parse(line) as { event: string; data: Record<string, unknown> };
              handleStreamEvent(sessionId, evt);
            } catch {
              // malformed line
            }
          }
        }

        if (buffer.trim()) {
          try {
            const evt = JSON.parse(buffer) as { event: string; data: Record<string, unknown> };
            handleStreamEvent(sessionId, evt);
          } catch {
            // ignore
          }
        }

        finalize(sessionId);
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        console.warn("[useSessions] streaming failed:", err);
        updateState(sessionId, (s) => ({
          ...s,
          error: err instanceof Error ? err.message : "Stream failed",
          streaming: false,
          liveContent: "",
          liveTools: [],
        }));
        setSessions((prev) =>
          prev.map((ss) => (ss.id === sessionId ? { ...ss, streaming: false } : ss)),
        );
      }
    },
    [agent, updateState],
  );

  function handleStreamEvent(
    sid: string,
    evt: { event: string; data: Record<string, unknown> },
  ) {
    switch (evt.event) {
      case "delta": {
        const content = evt.data.content as string;
        if (content) {
          updateState(sid, (s) => ({ ...s, liveContent: s.liveContent + content }));
        }
        break;
      }
      case "tool_call": {
        const tc: ToolCall = {
          id: (evt.data.call_id as string) || `tc-${Date.now()}`,
          tool: evt.data.tool as string,
          arguments: (evt.data.arguments as Record<string, unknown>) ?? {},
          status: "calling",
        };
        toolTimers.current.set(tc.id, Date.now());
        updateState(sid, (s) => ({ ...s, liveTools: [...s.liveTools, tc] }));
        break;
      }
      case "tool_result": {
        const callId = evt.data.call_id as string;
        const start = toolTimers.current.get(callId);
        const dur = start ? Date.now() - start : undefined;
        toolTimers.current.delete(callId);
        updateState(sid, (s) => ({
          ...s,
          liveTools: s.liveTools.map((t) =>
            t.id === callId ? { ...t, result: evt.data.result, status: "done" as const, duration: dur } : t,
          ),
        }));
        break;
      }
      case "done": {
        const response = evt.data.response as string | undefined;
        const rawUsage = evt.data.usage as Record<string, number> | undefined;
        const usage: UsageInfo | undefined = rawUsage
          ? {
              prompt_tokens: rawUsage.prompt_tokens ?? 0,
              completion_tokens: rawUsage.completion_tokens ?? 0,
              total_tokens: rawUsage.total_tokens ?? 0,
              model: evt.data.model as string | undefined,
              provider: evt.data.provider as string | undefined,
              cost: evt.data.cost as number | undefined,
              latency_ms: evt.data.latency_ms as number | undefined,
              trace_id: evt.data.trace_id as string | undefined,
              intent: evt.data.intent as string | undefined,
            }
          : undefined;
        updateState(sid, (s) => {
          const finalContent = response || s.liveContent || "";
          return {
            ...s,
            messages: [
              ...s.messages,
              {
                id: msgId(),
                role: "assistant" as const,
                content: finalContent,
                timestamp: Date.now(),
                tools: [...s.liveTools],
                usage,
              },
            ],
            liveTools: [],
            liveContent: "",
            streaming: false,
          };
        });
        setSessions((prev) =>
          prev.map((ss) =>
            ss.id === sid ? { ...ss, streaming: false, messageCount: ss.messageCount + 1 } : ss,
          ),
        );
        break;
      }
      case "error": {
        const message = (evt.data.message as string) || "An error occurred";
        updateState(sid, (s) => ({
          ...s,
          error: message,
          streaming: false,
          liveContent: "",
          liveTools: [],
          messages: [
            ...s.messages,
            { id: msgId(), role: "assistant" as const, content: "", timestamp: Date.now(), error: message },
          ],
        }));
        setSessions((prev) =>
          prev.map((ss) => (ss.id === sid ? { ...ss, streaming: false } : ss)),
        );
        break;
      }
    }
  }

  function finalize(sid: string) {
    setSessionStates((map) => {
      const state = map.get(sid);
      if (state?.streaming) {
        const next = new Map(map);
        const finalContent = state.liveContent;
        if (finalContent) {
          next.set(sid, {
            ...state,
            messages: [
              ...state.messages,
              {
                id: msgId(),
                role: "assistant" as const,
                content: finalContent,
                timestamp: Date.now(),
                tools: [...state.liveTools],
              },
            ],
            liveContent: "",
            liveTools: [],
            streaming: false,
          });
        } else {
          next.set(sid, { ...state, streaming: false, liveContent: "", liveTools: [] });
        }
        return next;
      }
      return map;
    });
    setSessions((prev) =>
      prev.map((ss) => (ss.id === sid && ss.streaming ? { ...ss, streaming: false } : ss)),
    );
  }

  const dismissError = useCallback(() => {
    const sid = activeSessionIdRef.current;
    if (sid) updateState(sid, (s) => ({ ...s, error: null }));
  }, [updateState]);

  const stopGenerating = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    const sid = activeSessionIdRef.current;
    if (!sid) return;
    updateState(sid, (s) => ({
      ...s,
      streaming: false,
      liveContent: "",
      liveTools: [],
    }));
    setSessions((prev) =>
      prev.map((ss) => (ss.id === sid ? { ...ss, streaming: false } : ss)),
    );
  }, [updateState]);

  const activeSession = activeSessionId ? sessionStates.get(activeSessionId) ?? null : null;

  const [connected, setConnected] = useState(false);
  useEffect(() => {
    let cancelled = false;
    const check = () => {
      fetch(`${API_BASE}/health`, { method: "GET" })
        .then((r) => { if (!cancelled) setConnected(r.ok); })
        .catch(() => { if (!cancelled) setConnected(false); });
    };
    check();
    const id = setInterval(check, 15_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return {
    connected,
    sessions,
    activeSessionId,
    activeSession,
    createSession,
    selectSession,
    send,
    dismissError,
    stopGenerating,
  };
}
