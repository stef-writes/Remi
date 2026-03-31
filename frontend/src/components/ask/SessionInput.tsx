"use client";

import { useRef, useState } from "react";
import type { ModelsConfig } from "@/lib/types";

function ModeToggle({
  mode,
  onChange,
}: {
  mode: "ask" | "agent";
  onChange: (m: "ask" | "agent") => void;
}) {
  return (
    <div className="flex rounded-lg border border-zinc-800/60 overflow-hidden">
      <button
        onClick={() => onChange("ask")}
        className={`px-3 py-1 text-[10px] font-semibold transition-colors ${
          mode === "ask"
            ? "bg-zinc-800 text-zinc-200"
            : "text-zinc-600 hover:text-zinc-400"
        }`}
      >
        Quick question
      </button>
      <button
        onClick={() => onChange("agent")}
        className={`px-3 py-1 text-[10px] font-semibold transition-colors ${
          mode === "agent"
            ? "bg-rose-800/80 text-rose-100"
            : "text-zinc-600 hover:text-zinc-400"
        }`}
      >
        Deep dive
      </button>
    </div>
  );
}

function ModelPicker({
  provider,
  model,
  modelsConfig,
  onChange,
}: {
  provider: string;
  model: string;
  modelsConfig: ModelsConfig | null;
  onChange: (provider: string, model: string) => void;
}) {
  const [open, setOpen] = useState(false);

  if (!modelsConfig) {
    return (
      <span className="text-[10px] text-zinc-700">
        {provider}/{model}
      </span>
    );
  }

  const availableProviders = modelsConfig.providers.filter((p) => p.available);

  const shortModel = (m: string) => {
    const parts = m.split("-");
    if (parts.length > 3) return parts.slice(0, 3).join("-");
    return m;
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 px-2 py-1 rounded-lg text-[10px] text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/60 transition-colors"
      >
        <span className="text-zinc-600">{provider}</span>
        <span className="text-zinc-700">/</span>
        <span className="text-zinc-400 font-medium">{shortModel(model)}</span>
        <svg
          className={`w-3 h-3 text-zinc-600 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute bottom-full left-0 mb-1 w-64 bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl overflow-hidden z-50">
          {availableProviders.map((p) => (
            <div key={p.name}>
              <div className="px-3 py-1.5 text-[9px] font-semibold text-zinc-600 uppercase tracking-wider bg-zinc-900/80">
                {p.name}
              </div>
              {p.models.map((m) => {
                const active = provider === p.name && model === m;
                return (
                  <button
                    key={`${p.name}/${m}`}
                    onClick={() => {
                      onChange(p.name, m);
                      setOpen(false);
                    }}
                    className={`w-full text-left px-3 py-1.5 text-[11px] transition-colors ${
                      active
                        ? "bg-zinc-800 text-zinc-200"
                        : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50"
                    }`}
                  >
                    {m}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function SessionInput({
  onSend,
  streaming,
  connected,
  mode,
  onModeChange,
  provider,
  model,
  modelsConfig,
  onModelChange,
  hasMessages,
  showWorkDetails,
  onToggleWorkDetails,
}: {
  onSend: (text: string, mode: "ask" | "agent") => void;
  streaming: boolean;
  connected: boolean;
  mode: "ask" | "agent";
  onModeChange: (m: "ask" | "agent") => void;
  provider: string;
  model: string;
  modelsConfig: ModelsConfig | null;
  onModelChange: (provider: string, model: string) => void;
  hasMessages: boolean;
  showWorkDetails: boolean;
  onToggleWorkDetails: () => void;
}) {
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    const msg = input.trim();
    if (!msg || streaming || !connected) return;
    onSend(msg, mode);
    setInput("");
  };

  return (
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
            placeholder={
              connected
                ? mode === "agent"
                  ? "Ask REMI to analyze something in depth..."
                  : "Ask about your managers, properties, leases..."
                : "Connecting..."
            }
            disabled={streaming || !connected}
            rows={1}
            className="flex-1 px-4 py-2.5 rounded-xl bg-zinc-900/60 border border-zinc-800/60 text-zinc-100 placeholder-zinc-700 focus:outline-none focus:ring-1 focus:ring-rose-800 text-sm resize-none disabled:opacity-40 transition-all"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || streaming || !connected}
            className={`shrink-0 h-10 px-5 rounded-xl text-sm font-medium transition-all disabled:bg-zinc-800 disabled:text-zinc-600 ${
              mode === "agent"
                ? "bg-rose-800 hover:bg-rose-700 text-rose-100"
                : "bg-zinc-700 hover:bg-zinc-600 text-zinc-200"
            }`}
          >
            {mode === "agent" ? "Analyze" : "Ask"}
          </button>
        </div>
        <div className="flex items-center justify-between mt-2">
          <div className="flex items-center gap-2">
            <ModeToggle mode={mode} onChange={onModeChange} />
            <ModelPicker
              provider={provider}
              model={model}
              modelsConfig={modelsConfig}
              onChange={onModelChange}
            />
          </div>
          <div className="flex items-center gap-3">
            {hasMessages && (
              <button
                onClick={onToggleWorkDetails}
                className="text-[10px] text-zinc-700 hover:text-zinc-500 transition-colors"
              >
                {showWorkDetails ? "Hide work details" : "Show work details"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
