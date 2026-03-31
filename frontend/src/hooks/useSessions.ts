"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatMessage, SessionSummary, ToolCall, UsageInfo } from "@/lib/types";

let _msgSeq = 0;
function msgId(): string {
  return `msg-${Date.now()}-${++_msgSeq}`;
}

const WS_URL =
  process.env.NEXT_PUBLIC_CHAT_WS_URL || "ws://localhost:8000/ws/chat";

const RPC_TIMEOUT_MS = 120_000;
const RECONNECT_BASE_MS = 2_000;
const RECONNECT_MAX_MS = 30_000;

interface JsonRpc {
  jsonrpc: "2.0";
  id?: number | string | null;
  method?: string;
  result?: Record<string, unknown>;
  params?: Record<string, unknown>;
  error?: { code: number; message: string };
}

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
  const wsRef = useRef<WebSocket | null>(null);
  const idCounter = useRef(0);
  const pending = useRef<
    Map<number, { resolve: (m: JsonRpc) => void; reject: (e: Error) => void }>
  >(new Map());
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelay = useRef(RECONNECT_BASE_MS);
  const toolTimers = useRef<Map<string, number>>(new Map());

  const [connected, setConnected] = useState(false);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessionStates, setSessionStates] = useState<
    Map<string, SessionState>
  >(new Map());

  const sessionStatesRef = useRef(sessionStates);
  sessionStatesRef.current = sessionStates;

  const activeSessionIdRef = useRef(activeSessionId);
  activeSessionIdRef.current = activeSessionId;

  const getState = useCallback(
    (sid: string): SessionState =>
      sessionStatesRef.current.get(sid) ?? emptySessionState(),
    []
  );

  const updateState = useCallback(
    (sid: string, updater: (prev: SessionState) => SessionState) => {
      setSessionStates((map) => {
        const next = new Map(map);
        next.set(sid, updater(map.get(sid) ?? emptySessionState()));
        return next;
      });
    },
    []
  );

  // --- WebSocket plumbing ---------------------------------------------------

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimer.current !== null) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
  }, []);

  const flushPending = useCallback((err: Error) => {
    for (const { reject } of pending.current.values()) reject(err);
    pending.current.clear();
  }, []);

  const rpc = useCallback(
    (method: string, params: Record<string, unknown>) =>
      new Promise<JsonRpc>((resolve, reject) => {
        const id = ++idCounter.current;
        const timer = setTimeout(() => {
          pending.current.delete(id);
          reject(new Error("RPC timeout"));
        }, RPC_TIMEOUT_MS);
        pending.current.set(id, {
          resolve: (m) => {
            clearTimeout(timer);
            resolve(m);
          },
          reject: (e) => {
            clearTimeout(timer);
            reject(e);
          },
        });
        wsRef.current?.send(
          JSON.stringify({ jsonrpc: "2.0", id, method, params })
        );
      }),
    []
  );

  // --- Notification demuxing ------------------------------------------------

  const handleNotification = useCallback(
    (msg: JsonRpc) => {
      const p = msg.params ?? {};
      const sid = p.session_id as string | undefined;
      if (!sid) return;

      switch (msg.method) {
        case "chat.delta": {
          const content = p.content as string;
          if (content) {
            updateState(sid, (s) => ({
              ...s,
              liveContent: s.liveContent + content,
            }));
          }
          break;
        }
        case "chat.tool_call": {
          const tc: ToolCall = {
            id: (p.call_id as string) || `tc-${Date.now()}`,
            tool: p.tool as string,
            arguments: p.arguments as Record<string, unknown>,
            status: "calling",
          };
          toolTimers.current.set(tc.id, Date.now());
          updateState(sid, (s) => ({
            ...s,
            liveTools: [...s.liveTools, tc],
          }));
          break;
        }
        case "chat.tool_result": {
          const callId = p.call_id as string;
          const start = toolTimers.current.get(callId);
          const dur = start ? Date.now() - start : undefined;
          toolTimers.current.delete(callId);
          updateState(sid, (s) => ({
            ...s,
            liveTools: s.liveTools.map((t) =>
              t.id === callId
                ? {
                    ...t,
                    result: p.result,
                    status: "done" as const,
                    duration: dur,
                  }
                : t
            ),
          }));
          break;
        }
        case "chat.done": {
          const response = p.response as string;
          const rawUsage = p.usage as Record<string, number> | undefined;
          const rawCost = p.cost as number | undefined;
          const usage: UsageInfo | undefined = rawUsage
            ? {
                prompt_tokens: rawUsage.prompt_tokens ?? 0,
                completion_tokens: rawUsage.completion_tokens ?? 0,
                total_tokens: rawUsage.total_tokens ?? 0,
                model: p.model as string | undefined,
                provider: p.provider as string | undefined,
                cost: rawCost,
                latency_ms: p.latency_ms as number | undefined,
                trace_id: p.trace_id as string | undefined,
                intent: p.intent as string | undefined,
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
              ss.id === sid
                ? { ...ss, streaming: false, messageCount: ss.messageCount + 1 }
                : ss
            )
          );
          break;
        }
        case "chat.error": {
          const message = (p.message as string) || "An error occurred";
          updateState(sid, (s) => ({
            ...s,
            error: message,
            streaming: false,
            liveContent: "",
            liveTools: [],
            messages: [
              ...s.messages,
              {
                id: msgId(),
                role: "assistant" as const,
                content: "",
                timestamp: Date.now(),
                error: message,
              },
            ],
          }));
          setSessions((prev) =>
            prev.map((ss) =>
              ss.id === sid ? { ...ss, streaming: false } : ss
            )
          );
          break;
        }
      }
    },
    [updateState]
  );

  // --- Connect + load session list ------------------------------------------

  const loadSessionList = useCallback(
    async (rpcFn: typeof rpc) => {
      try {
        const r = await rpcFn("chat.list", {});
        const list = (r.result?.sessions as Array<Record<string, unknown>>) ?? [];
        const summaries: SessionSummary[] = list.map((s) => ({
          id: s.id as string,
          agent: s.agent as string,
          messageCount: s.message_count as number,
          preview: "",
          createdAt: s.created_at as string,
          updatedAt: s.updated_at as string,
          streaming: false,
        }));
        setSessions(summaries);
        return summaries;
      } catch {
        return [];
      }
    },
    []
  );

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(WS_URL);
    ws.onopen = () => {
      setConnected(true);
      reconnectDelay.current = RECONNECT_BASE_MS;
      loadSessionList(rpc);
    };
    ws.onmessage = (e) => {
      try {
        const msg: JsonRpc = JSON.parse(e.data);
        if (msg.id != null && pending.current.has(Number(msg.id))) {
          const entry = pending.current.get(Number(msg.id))!;
          pending.current.delete(Number(msg.id));
          if (msg.error) {
            entry.reject(new Error(msg.error.message));
          } else {
            entry.resolve(msg);
          }
          return;
        }
        if (msg.method) handleNotification(msg);
      } catch {
        /* malformed JSON */
      }
    };
    ws.onclose = () => {
      setConnected(false);
      flushPending(new Error("WebSocket disconnected"));
      const delay = reconnectDelay.current;
      reconnectDelay.current = Math.min(delay * 2, RECONNECT_MAX_MS);
      reconnectTimer.current = setTimeout(connect, delay);
    };
    ws.onerror = () => ws.close();
    wsRef.current = ws;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    connect();
    return () => {
      clearReconnectTimer();
      wsRef.current?.close();
    };
  }, [connect, clearReconnectTimer]);

  // --- Public API -----------------------------------------------------------

  const createSession = useCallback(async () => {
    try {
      const r = await rpc("chat.create", { agent });
      const sid = r.result?.session_id as string;
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
    } catch {
      /* ignore */
    }
  }, [rpc, agent]);

  const selectSession = useCallback(
    async (sid: string) => {
      setActiveSessionId(sid);
      const state = sessionStatesRef.current.get(sid);
      if (state?.loaded) return;

      try {
        const r = await rpc("chat.history", { session_id: sid });
        const rawMessages =
          (r.result?.messages as Array<Record<string, unknown>>) ?? [];
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
              ss.id === sid
                ? { ...ss, preview: firstUser.content.slice(0, 80) }
                : ss
            )
          );
        }
      } catch {
        updateState(sid, (s) => ({ ...s, loaded: true }));
      }
    },
    [rpc, updateState]
  );

  const send = useCallback(
    async (
      text: string,
      mode: "ask" | "agent" = "ask",
      opts?: { provider?: string; model?: string; managerId?: string },
    ) => {
      let sid = activeSessionIdRef.current;

      if (!sid) {
        try {
          const r = await rpc("chat.create", {
            agent,
            ...(opts?.provider && { provider: opts.provider }),
            ...(opts?.model && { model: opts.model }),
          });
          sid = r.result?.session_id as string;
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
        } catch (e) {
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
        })
      );

      try {
        await rpc("chat.send", {
          session_id: sessionId,
          message: text,
          mode,
          ...(opts?.provider && { provider: opts.provider }),
          ...(opts?.model && { model: opts.model }),
          ...(opts?.managerId && { manager_id: opts.managerId }),
        });
      } catch (e) {
        if (e instanceof Error && e.message !== "WebSocket disconnected") {
          updateState(sessionId, (s) => ({
            ...s,
            error: e instanceof Error ? e.message : "Send failed",
            streaming: false,
            liveContent: "",
          }));
        }
        setSessions((prev) =>
          prev.map((ss) =>
            ss.id === sessionId ? { ...ss, streaming: false } : ss
          )
        );
      }
    },
    [rpc, agent, updateState]
  );

  const deleteSession = useCallback(
    async (sid: string) => {
      setSessions((prev) => prev.filter((s) => s.id !== sid));
      setSessionStates((map) => {
        const next = new Map(map);
        next.delete(sid);
        return next;
      });
      if (activeSessionIdRef.current === sid) {
        setActiveSessionId(null);
      }
    },
    []
  );

  const dismissError = useCallback(() => {
    const sid = activeSessionIdRef.current;
    if (sid) {
      updateState(sid, (s) => ({ ...s, error: null }));
    }
  }, [updateState]);

  const stopGenerating = useCallback(() => {
    const sid = activeSessionIdRef.current;
    if (!sid) return;

    rpc("chat.stop", { session_id: sid }).catch(() => {});

    updateState(sid, (s) => ({
      ...s,
      streaming: false,
      liveContent: "",
      liveTools: [],
    }));
    setSessions((prev) =>
      prev.map((ss) =>
        ss.id === sid ? { ...ss, streaming: false } : ss
      )
    );
  }, [rpc, updateState]);

  const activeSession = activeSessionId
    ? sessionStates.get(activeSessionId) ?? null
    : null;

  return {
    connected,
    sessions,
    activeSessionId,
    activeSession,
    createSession,
    selectSession,
    send,
    deleteSession,
    dismissError,
    stopGenerating,
  };
}
