"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { StatusDot } from "@/components/ui/StatusDot";
import type { ChatMessage, ToolCall, UsageInfo } from "@/lib/types";

const TOOL_LABELS: Record<string, string> = {
  onto_signals: "Checking portfolio signals",
  onto_explain: "Looking at the evidence",
  onto_search: "Searching portfolio data",
  onto_get: "Looking up details",
  onto_related: "Checking related data",
  onto_aggregate: "Calculating numbers",
  onto_schema: "Checking data structure",
  onto_timeline: "Looking at history",
  onto_codify_observation: "Saving an observation",
  onto_codify_policy: "Recording a policy",
  onto_codify_causal_link: "Recording a relationship",
  onto_define_type: "Defining a new category",
  document_list: "Checking uploaded reports",
  document_query: "Searching report data",
  semantic_search: "Searching for context",
  vector_stats: "Checking search index",
  sandbox_exec_python: "Running analysis",
  sandbox_exec_shell: "Running a command",
  sandbox_write_file: "Saving work",
  sandbox_read_file: "Reading a file",
  sandbox_list_files: "Checking files",
  trace_list: "Reviewing past work",
  trace_show: "Inspecting details",
  trace_spans: "Reviewing steps",
  memory_store: "Remembering this",
  memory_recall: "Recalling past context",
};

function toolLabel(name: string): string {
  return TOOL_LABELS[name] || name.replace(/_/g, " ");
}

function ToolCallCompact({ tc }: { tc: ToolCall }) {
  return (
    <div className="flex items-center gap-2 px-2 py-1 rounded-md text-left w-full">
      <StatusDot status={tc.status} size={4} />
      <span className="text-[11px] text-zinc-500 flex-1">{toolLabel(tc.tool)}</span>
      {tc.duration != null && (
        <span className="text-[9px] text-zinc-700">{(tc.duration / 1000).toFixed(1)}s</span>
      )}
    </div>
  );
}

function ToolCallDetailed({ tc }: { tc: ToolCall }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-lg border border-zinc-800/50 bg-zinc-800/20 overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-zinc-800/30 transition-colors"
      >
        <StatusDot status={tc.status} size={5} />
        <span className="text-[11px] text-zinc-400">{toolLabel(tc.tool)}</span>
        {tc.duration != null && (
          <span className="text-[9px] text-zinc-700 ml-auto">{(tc.duration / 1000).toFixed(1)}s</span>
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
            <p className="text-[9px] text-zinc-600 uppercase tracking-wider font-semibold mb-0.5">Details</p>
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

// Per-million-token pricing: [input, output]
const MODEL_PRICING: Record<string, [number, number]> = {
  "claude-opus-4-6-20260320": [15.0, 75.0],
  "claude-sonnet-4-6-20260320": [3.0, 15.0],
  "claude-sonnet-4-5-20250514": [3.0, 15.0],
  "claude-3-5-sonnet-20241022": [3.0, 15.0],
  "claude-3-opus-20240229": [15.0, 75.0],
  "gpt-4o": [2.5, 10.0],
  "gpt-4o-mini": [0.15, 0.6],
  "gpt-4-turbo": [10.0, 30.0],
  "gemini-2.0-flash": [0.1, 0.4],
  "gemini-1.5-pro": [1.25, 5.0],
};

function calcCost(usage: UsageInfo): number | null {
  const model = usage.model;
  if (!model) return null;
  const pricing = MODEL_PRICING[model];
  if (!pricing) return null;
  const [inputPer1M, outputPer1M] = pricing;
  return (
    (usage.prompt_tokens * inputPer1M) / 1_000_000 +
    (usage.completion_tokens * outputPer1M) / 1_000_000
  );
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function UsageBadge({ usage }: { usage: UsageInfo }) {
  const cost = usage.cost ?? calcCost(usage);
  return (
    <div className="flex items-center gap-2 text-[10px] text-zinc-500 mt-1 pl-1 select-none">
      <span title="Prompt tokens">{formatTokens(usage.prompt_tokens)} in</span>
      <span className="text-zinc-700">/</span>
      <span title="Completion tokens">{formatTokens(usage.completion_tokens)} out</span>
      {cost !== null && (
        <>
          <span className="text-zinc-700">·</span>
          <span title="Estimated cost">${cost < 0.01 ? cost.toFixed(4) : cost.toFixed(2)}</span>
        </>
      )}
      {usage.model && (
        <>
          <span className="text-zinc-700">·</span>
          <span className="text-zinc-600">{usage.model.replace(/^claude-/, "").replace(/-\d{8}$/, "")}</span>
        </>
      )}
    </div>
  );
}

export function SessionThread({
  messages,
  liveContent,
  liveTools,
  streaming,
  showWorkDetails,
}: {
  messages: ChatMessage[];
  liveContent: string;
  liveTools: ToolCall[];
  streaming: boolean;
  showWorkDetails: boolean;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages.length, liveTools.length, liveContent]);

  return (
    <div ref={scrollRef} className="flex-1 overflow-y-auto">
      <div className="max-w-3xl mx-auto px-6 py-6 space-y-5">
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

                {msg.role === "assistant" && msg.tools && msg.tools.length > 0 && showWorkDetails && (
                  <div className="w-full space-y-0.5 pl-1">
                    {msg.tools.map((tc) => (
                      <ToolCallDetailed key={tc.id} tc={tc} />
                    ))}
                  </div>
                )}

                {msg.role === "assistant" && msg.usage && msg.usage.total_tokens > 0 && (
                  <UsageBadge usage={msg.usage} />
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {streaming && liveTools.length > 0 && !liveContent && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-start">
            <div className="max-w-[85%]">
              <div className="bg-zinc-800/50 border border-zinc-800/40 rounded-2xl rounded-bl-md px-4 py-3">
                <div className="flex items-center gap-2.5">
                  <StatusDot status="running" size={6} pulse />
                  <span className="text-sm text-zinc-400">
                    {toolLabel(liveTools[liveTools.length - 1].tool)}...
                  </span>
                </div>
                {showWorkDetails && (
                  <div className="mt-2 pt-2 border-t border-zinc-800/30 space-y-0.5">
                    {liveTools.map((tc) => (
                      <ToolCallCompact key={tc.id} tc={tc} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        )}

        {streaming && liveContent && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-start">
            <div className="max-w-[85%]">
              <div className="bg-zinc-800/50 border border-zinc-800/40 rounded-2xl rounded-bl-md px-4 py-3 text-sm leading-relaxed text-zinc-200">
                <div className="whitespace-pre-wrap">
                  {liveContent}
                  <span className="inline-block w-1.5 h-4 bg-zinc-400 animate-pulse ml-0.5 align-text-bottom" />
                </div>
              </div>
            </div>
          </motion.div>
        )}

        {streaming && !liveContent && liveTools.length === 0 && (
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
  );
}
