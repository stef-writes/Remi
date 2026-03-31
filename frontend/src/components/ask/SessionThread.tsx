"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Markdown } from "@/components/ui/Markdown";
import type { ChatMessage, ToolCall, UsageInfo } from "@/lib/types";

const TOOL_LABELS: Record<string, string> = {
  onto_signals: "Checking signals",
  onto_explain: "Looking at evidence",
  onto_search: "Searching data",
  onto_get: "Looking up details",
  onto_related: "Checking related data",
  onto_aggregate: "Calculating",
  onto_schema: "Checking structure",
  onto_timeline: "Looking at history",
  onto_codify_observation: "Saving observation",
  onto_codify_policy: "Recording policy",
  onto_codify_causal_link: "Recording link",
  onto_define_type: "Defining category",
  document_list: "Checking reports",
  document_query: "Searching reports",
  semantic_search: "Searching context",
  vector_stats: "Checking index",
  sandbox_exec_python: "Running analysis",
  sandbox_exec_shell: "Running command",
  sandbox_write_file: "Saving work",
  sandbox_read_file: "Reading file",
  sandbox_list_files: "Checking files",
  trace_list: "Reviewing past work",
  trace_show: "Inspecting details",
  trace_spans: "Reviewing steps",
  memory_store: "Remembering",
  memory_recall: "Recalling",
};

function toolLabel(name: string): string {
  return TOOL_LABELS[name] || name.replace(/_/g, " ");
}

function ToolCallRow({ tc }: { tc: ToolCall }) {
  const [open, setOpen] = useState(false);

  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 py-0.5 text-left transition-colors"
      >
        {tc.status === "calling" ? (
          <span className="w-3 h-3 shrink-0 flex items-center justify-center">
            <span className="w-1.5 h-1.5 rounded-full bg-warn animate-pulse" />
          </span>
        ) : (
          <svg className="w-3 h-3 text-ok shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
          </svg>
        )}
        <span className="text-xs text-fg-faint">{toolLabel(tc.tool)}</span>
        {tc.duration != null && (
          <span className="text-[10px] text-fg-ghost">{(tc.duration / 1000).toFixed(1)}s</span>
        )}
      </button>
      {open && (
        <div className="ml-5 mt-1 mb-2 rounded-lg bg-surface-raised border border-border p-2.5 space-y-2">
          <pre className="text-[10px] text-fg-muted font-mono overflow-x-auto leading-relaxed">
            {JSON.stringify(tc.arguments, null, 2)}
          </pre>
          {tc.result !== undefined && (
            <div className="border-t border-border pt-2">
              <pre className="text-[10px] text-fg-muted font-mono overflow-x-auto max-h-28 overflow-y-auto leading-relaxed">
                {typeof tc.result === "string" ? tc.result : JSON.stringify(tc.result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const MODEL_PRICING: Record<string, [number, number]> = {
  "claude-opus-4-20250514": [5.0, 25.0],
  "claude-sonnet-4-20250514": [3.0, 15.0],
  "claude-sonnet-4-5-20250929": [3.0, 15.0],
  "claude-haiku-4-5-20251001": [1.0, 5.0],
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

function formatLatency(ms: number): string {
  if (ms >= 60_000) return `${(ms / 60_000).toFixed(1)}m`;
  if (ms >= 1_000) return `${(ms / 1_000).toFixed(1)}s`;
  return `${ms}ms`;
}

function UsageBadge({ usage }: { usage: UsageInfo }) {
  const cost = usage.cost ?? calcCost(usage);
  return (
    <div className="flex items-center gap-1.5 text-[10px] text-fg-faint select-none">
      {usage.latency_ms != null && (
        <>
          <span className="font-medium">{formatLatency(usage.latency_ms)}</span>
          <span className="text-fg-ghost">·</span>
        </>
      )}
      <span>{formatTokens(usage.prompt_tokens)} in</span>
      <span className="text-fg-ghost">/</span>
      <span>{formatTokens(usage.completion_tokens)} out</span>
      {cost !== null && (
        <>
          <span className="text-fg-ghost">·</span>
          <span>${cost < 0.01 ? cost.toFixed(4) : cost.toFixed(3)}</span>
        </>
      )}
      {usage.model && (
        <>
          <span className="text-fg-ghost">·</span>
          <span>{usage.model.replace(/^claude-/, "").replace(/-\d{8}$/, "")}</span>
        </>
      )}
      {usage.intent && (
        <>
          <span className="text-fg-ghost">·</span>
          <span className="text-fg-ghost">{usage.intent}</span>
        </>
      )}
    </div>
  );
}

function RetryButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1 text-[11px] text-fg-faint hover:text-fg-secondary transition-colors"
      title="Regenerate"
    >
      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182M2.985 14.652" />
      </svg>
      Retry
    </button>
  );
}

export function SessionThread({
  messages,
  liveContent,
  liveTools,
  streaming,
  showWorkDetails,
  onRetry,
}: {
  messages: ChatMessage[];
  liveContent: string;
  liveTools: ToolCall[];
  streaming: boolean;
  showWorkDetails: boolean;
  onRetry?: () => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages.length, liveTools.length, liveContent]);

  const lastAssistantIdx = messages.reduce(
    (acc, m, i) => (m.role === "assistant" && !m.error ? i : acc),
    -1
  );

  return (
    <div ref={scrollRef} className="flex-1 overflow-y-auto">
      <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
        <AnimatePresence initial={false}>
          {messages.map((msg, i) => {
            if (msg.error) {
              return (
                <motion.div
                  key={msg.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex justify-start"
                >
                  <div className="flex items-start gap-2 max-w-[85%]">
                    <svg className="w-4 h-4 text-error mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                    </svg>
                    <div>
                      <p className="text-sm text-error-fg">{msg.error}</p>
                      {onRetry && (
                        <button onClick={onRetry} className="mt-1 text-[11px] text-error/60 hover:text-error transition-colors">
                          Try again
                        </button>
                      )}
                    </div>
                  </div>
                </motion.div>
              );
            }

            if (msg.role === "user") {
              return (
                <motion.div
                  key={msg.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex justify-end"
                >
                  <div className="max-w-[75%] rounded-2xl rounded-br-md px-4 py-2.5 bg-user-bubble text-sm text-user-bubble-fg leading-relaxed">
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                  </div>
                </motion.div>
              );
            }

            return (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex justify-start"
              >
                <div className="max-w-[90%] space-y-2">
                  {msg.tools && msg.tools.length > 0 && showWorkDetails && (
                    <div className="pl-0.5 space-y-0">
                      {msg.tools.map((tc) => (
                        <ToolCallRow key={tc.id} tc={tc} />
                      ))}
                    </div>
                  )}

                  <div className="text-sm leading-relaxed text-fg-secondary">
                    <Markdown content={msg.content} />
                  </div>

                  <div className="flex items-center gap-3 pt-0.5">
                    {msg.usage && msg.usage.total_tokens > 0 && (
                      <UsageBadge usage={msg.usage} />
                    )}
                    {i === lastAssistantIdx && !streaming && onRetry && (
                      <RetryButton onClick={onRetry} />
                    )}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>

        {streaming && liveTools.length > 0 && !liveContent && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-start">
            <div className="max-w-[90%] space-y-1">
              <div className="flex items-center gap-2 py-1">
                <span className="w-1.5 h-1.5 rounded-full bg-warn animate-pulse" />
                <span className="text-[13px] text-fg-faint">
                  {toolLabel(liveTools[liveTools.length - 1].tool)}...
                </span>
              </div>
              {showWorkDetails && (
                <div className="pl-0.5 space-y-0">
                  {liveTools.map((tc) => (
                    <ToolCallRow key={tc.id} tc={tc} />
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}

        {streaming && liveContent && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-start">
            <div className="max-w-[90%] space-y-2">
              {showWorkDetails && liveTools.length > 0 && (
                <div className="pl-0.5 space-y-0">
                  {liveTools.map((tc) => (
                    <ToolCallRow key={tc.id} tc={tc} />
                  ))}
                </div>
              )}
              <div className="text-sm leading-relaxed text-fg-secondary">
                <Markdown content={liveContent} />
                <span className="inline-block w-[2px] h-[16px] bg-fg-faint animate-pulse ml-0.5 align-text-bottom rounded-full" />
              </div>
            </div>
          </motion.div>
        )}

        {streaming && !liveContent && liveTools.length === 0 && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-start">
            <div className="flex items-center gap-1.5 py-2">
              <motion.span className="w-1.5 h-1.5 rounded-full bg-fg-ghost" animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1, repeat: Infinity, delay: 0 }} />
              <motion.span className="w-1.5 h-1.5 rounded-full bg-fg-ghost" animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1, repeat: Infinity, delay: 0.15 }} />
              <motion.span className="w-1.5 h-1.5 rounded-full bg-fg-ghost" animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1, repeat: Infinity, delay: 0.3 }} />
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}
