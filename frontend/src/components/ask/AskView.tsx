"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useChat } from "@/hooks/useChat";
import { Badge } from "@/components/ui/Badge";
import { StatusDot } from "@/components/ui/StatusDot";
import type { ToolCall } from "@/lib/types";

const AGENTS = [
  { id: "portfolio_analyst", label: "Portfolio", desc: "Cross-portfolio analytics and financial performance" },
  { id: "property_inspector", label: "Property", desc: "Deep-dive into a single property" },
  { id: "maintenance_triage", label: "Maintenance", desc: "Work order triage and prioritization" },
];

const PROMPTS: Record<string, string[]> = {
  portfolio_analyst: [
    "What's the overall occupancy rate across all portfolios?",
    "Which properties are underperforming financially?",
    "Show me leases expiring in the next 30 days",
    "Compare revenue across Bay Area vs Midwest portfolios",
  ],
  property_inspector: [
    "Give me a full breakdown of Sunset Terrace",
    "Which units at Lakeside Commons have below-market rent?",
    "What's the maintenance situation at Innovation Hub?",
  ],
  maintenance_triage: [
    "What are the most urgent open maintenance requests?",
    "Which properties have the highest maintenance costs?",
    "Prioritize all open requests by severity",
  ],
};

function ToolCallInline({ tc }: { tc: ToolCall }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-lg border border-zinc-800/50 bg-zinc-800/20 overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-zinc-800/30 transition-colors"
      >
        <StatusDot status={tc.status} size={5} />
        <span className="text-[11px] font-mono text-zinc-400">{tc.tool.replace(/_/g, " ")}</span>
        {tc.duration != null && (
          <span className="text-[9px] text-zinc-700 ml-auto">{tc.duration}ms</span>
        )}
        <svg
          className={`w-3 h-3 text-zinc-600 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="px-3 py-2 border-t border-zinc-800/30 space-y-2">
          <div>
            <p className="text-[9px] text-zinc-600 uppercase tracking-wider font-semibold mb-0.5">Args</p>
            <pre className="text-[10px] text-zinc-500 font-mono overflow-x-auto">
              {JSON.stringify(tc.arguments, null, 2)}
            </pre>
          </div>
          {tc.result !== undefined && (
            <div>
              <p className="text-[9px] text-emerald-600 uppercase tracking-wider font-semibold mb-0.5">Result</p>
              <pre className="text-[10px] text-zinc-500 font-mono overflow-x-auto max-h-32 overflow-y-auto">
                {typeof tc.result === "string" ? tc.result : JSON.stringify(tc.result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function AskView() {
  const [agent, setAgent] = useState("portfolio_analyst");
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const { connected, messages, liveTools, streaming, send, reset } = useChat(agent);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, liveTools.length]);

  const handleSend = (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || streaming || !connected) return;
    send(msg);
    setInput("");
  };

  const prompts = PROMPTS[agent] ?? [];

  return (
    <div className="h-full flex flex-col">
      {/* Top bar */}
      <div className="shrink-0 h-13 border-b border-zinc-800/60 flex items-center px-6 gap-4">
        <h1 className="text-sm font-semibold text-zinc-300 mr-2">Ask REMI</h1>
        <div className="flex gap-1">
          {AGENTS.map((a) => (
            <button
              key={a.id}
              onClick={() => setAgent(a.id)}
              className={`px-3 py-1.5 rounded-lg text-[11px] font-medium transition-all ${
                agent === a.id
                  ? "bg-zinc-800 text-zinc-100"
                  : "text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800/30"
              }`}
            >
              {a.label}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <button
          onClick={reset}
          className="text-[10px] text-zinc-600 hover:text-zinc-400 font-mono transition-colors"
        >
          new conversation
        </button>
        <StatusDot status={connected ? "connected" : "disconnected"} size={6} />
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-6 space-y-5">
          {/* Empty state with prompt suggestions */}
          {messages.length === 0 && !streaming && (
            <div className="py-16 space-y-6">
              <div className="text-center">
                <div className="w-14 h-14 rounded-2xl bg-zinc-800/50 border border-zinc-800 flex items-center justify-center mx-auto mb-4">
                  <svg className="w-7 h-7 text-zinc-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
                  </svg>
                </div>
                <h2 className="text-lg font-semibold text-zinc-300">
                  {AGENTS.find((a) => a.id === agent)?.desc}
                </h2>
                <p className="text-sm text-zinc-600 mt-1">
                  Ask anything about your portfolio. REMI will query your data to answer.
                </p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-lg mx-auto">
                {prompts.map((p) => (
                  <button
                    key={p}
                    onClick={() => handleSend(p)}
                    disabled={!connected}
                    className="text-left text-[12px] px-4 py-3 rounded-xl border border-zinc-800/50 bg-zinc-900/30 text-zinc-400 hover:text-zinc-200 hover:border-zinc-700 hover:bg-zinc-800/30 transition-all disabled:opacity-40"
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Message thread */}
          <AnimatePresence initial={false}>
            {messages.map((msg, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div className={`max-w-[85%] space-y-2 ${msg.role === "user" ? "items-end" : "items-start"} flex flex-col`}>
                  <div
                    className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "bg-blue-600 text-white rounded-br-md"
                        : "bg-zinc-800/50 border border-zinc-800/40 text-zinc-200 rounded-bl-md"
                    }`}
                  >
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                  </div>

                  {msg.tools && msg.tools.length > 0 && (
                    <div className="w-full space-y-1">
                      <p className="text-[9px] text-zinc-600 uppercase tracking-wider font-semibold px-1">
                        Queried {msg.tools.length} data source{msg.tools.length > 1 ? "s" : ""}
                      </p>
                      {msg.tools.map((tc) => (
                        <ToolCallInline key={tc.id} tc={tc} />
                      ))}
                    </div>
                  )}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>

          {/* Live tool calls */}
          {streaming && liveTools.length > 0 && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-start">
              <div className="max-w-[85%] space-y-1">
                <div className="flex items-center gap-2 px-1 mb-1">
                  <StatusDot status="running" size={6} pulse />
                  <span className="text-[10px] text-zinc-500">Querying data...</span>
                </div>
                {liveTools.map((tc) => (
                  <ToolCallInline key={tc.id} tc={tc} />
                ))}
              </div>
            </motion.div>
          )}

          {/* Typing dots */}
          {streaming && liveTools.length === 0 && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-start">
              <div className="bg-zinc-800/50 border border-zinc-800/40 rounded-2xl rounded-bl-md px-4 py-3">
                <div className="flex gap-1.5">
                  <motion.span className="w-1.5 h-1.5 rounded-full bg-zinc-500" animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1.2, repeat: Infinity, delay: 0 }} />
                  <motion.span className="w-1.5 h-1.5 rounded-full bg-zinc-500" animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1.2, repeat: Infinity, delay: 0.2 }} />
                  <motion.span className="w-1.5 h-1.5 rounded-full bg-zinc-500" animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1.2, repeat: Infinity, delay: 0.4 }} />
                </div>
              </div>
            </motion.div>
          )}
        </div>
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-zinc-800/60">
        <div className="max-w-3xl mx-auto px-6 py-4">
          <div className="flex gap-3 items-end">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder={connected ? "Ask about your properties, leases, finances..." : "Connecting to backend..."}
              disabled={streaming || !connected}
              rows={1}
              className="flex-1 px-4 py-2.5 rounded-xl bg-zinc-900/60 border border-zinc-800/60 text-zinc-100 placeholder-zinc-700 focus:outline-none focus:ring-1 focus:ring-zinc-700 text-sm resize-none disabled:opacity-40 transition-all"
            />
            <button
              onClick={() => handleSend()}
              disabled={!input.trim() || streaming || !connected}
              className="shrink-0 h-10 px-5 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-800 disabled:text-zinc-600 text-white text-sm font-medium transition-all"
            >
              Ask
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
