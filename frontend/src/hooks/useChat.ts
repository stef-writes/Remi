"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatMessage, ToolCall } from "@/lib/types";

const WS_URL =
  process.env.NEXT_PUBLIC_CHAT_WS_URL || "ws://localhost:8000/ws/chat";

interface JsonRpc {
  jsonrpc: "2.0";
  id?: number | string | null;
  method?: string;
  result?: Record<string, unknown>;
  params?: Record<string, unknown>;
  error?: { code: number; message: string };
}

let _id = 0;

export function useChat(agent: string) {
  const wsRef = useRef<WebSocket | null>(null);
  const pending = useRef<Map<number, (m: JsonRpc) => void>>(new Map());
  const [connected, setConnected] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [liveTools, setLiveTools] = useState<ToolCall[]>([]);
  const [streaming, setStreaming] = useState(false);
  const toolTimers = useRef<Map<string, number>>(new Map());

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    const ws = new WebSocket(WS_URL);
    ws.onopen = () => setConnected(true);
    ws.onmessage = (e) => {
      try {
        const msg: JsonRpc = JSON.parse(e.data);
        if (msg.id != null && pending.current.has(Number(msg.id))) {
          pending.current.get(Number(msg.id))!(msg);
          pending.current.delete(Number(msg.id));
          return;
        }
        if (msg.method) handleNotification(msg);
      } catch {
        /* skip */
      }
    };
    ws.onclose = () => {
      setConnected(false);
      setTimeout(connect, 2000);
    };
    ws.onerror = () => ws.close();
    wsRef.current = ws;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleNotification(msg: JsonRpc) {
    const p = msg.params ?? {};
    switch (msg.method) {
      case "chat.delta":
        break; // streamed content — we get final from chat.done
      case "chat.tool_call": {
        const tc: ToolCall = {
          id: (p.call_id as string) || `tc-${Date.now()}`,
          tool: p.tool as string,
          arguments: p.arguments as Record<string, unknown>,
          status: "calling",
        };
        toolTimers.current.set(tc.id, Date.now());
        setLiveTools((prev) => [...prev, tc]);
        break;
      }
      case "chat.tool_result": {
        const callId = p.call_id as string;
        const start = toolTimers.current.get(callId);
        const dur = start ? Date.now() - start : undefined;
        toolTimers.current.delete(callId);
        setLiveTools((prev) =>
          prev.map((t) =>
            t.id === callId
              ? { ...t, result: p.result, status: "done" as const, duration: dur }
              : t
          )
        );
        break;
      }
      case "chat.done": {
        const response = p.response as string;
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: response ?? "",
            timestamp: Date.now(),
            tools: [...(liveToolsRef.current ?? [])],
          },
        ]);
        setLiveTools([]);
        setStreaming(false);
        break;
      }
      case "chat.error":
        setStreaming(false);
        break;
    }
  }

  const liveToolsRef = useRef(liveTools);
  liveToolsRef.current = liveTools;

  const rpc = useCallback(
    (method: string, params: Record<string, unknown>) =>
      new Promise<JsonRpc>((resolve) => {
        const id = ++_id;
        pending.current.set(id, resolve);
        wsRef.current?.send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
      }),
    []
  );

  const send = useCallback(
    async (text: string) => {
      let sid = sessionId;
      if (!sid) {
        const r = await rpc("chat.create", { agent });
        sid = r.result?.session_id as string;
        setSessionId(sid);
      }
      setStreaming(true);
      setLiveTools([]);
      setMessages((prev) => [
        ...prev,
        { role: "user", content: text, timestamp: Date.now() },
      ]);
      await rpc("chat.send", { session_id: sid, message: text });
    },
    [sessionId, rpc, agent]
  );

  const reset = useCallback(() => {
    setSessionId(null);
    setMessages([]);
    setLiveTools([]);
    setStreaming(false);
  }, []);

  useEffect(() => {
    connect();
    return () => wsRef.current?.close();
  }, [connect]);

  useEffect(() => {
    reset();
  }, [agent, reset]);

  return { connected, messages, liveTools, streaming, send, reset };
}
