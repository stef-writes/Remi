"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { DomainSchemaResponse } from "@/lib/api/misc";

const GREETINGS = [
  "Hey there.",
  "Good to see you.",
  "Ready when you are.",
  "Let's get into it.",
];

const FALLBACK_SUGGESTIONS = [
  { text: "How's my portfolio looking today?", icon: "📊" },
  { text: "Which managers are performing best?", icon: "🏆" },
  { text: "Are any leases expiring soon?", icon: "📋" },
  { text: "Show me the delinquency picture", icon: "💰" },
  { text: "What should I be paying attention to?", icon: "🔍" },
];

const RESEARCH_SUGGESTIONS = [
  { text: "Write a full delinquency analysis across all managers", icon: "📊" },
  { text: "Compare manager performance over the last 90 days", icon: "🏆" },
  { text: "Generate a lease expiry risk report", icon: "📋" },
  { text: "Identify maintenance patterns and surface any outliers", icon: "🔧" },
  { text: "Which properties carry the highest vacancy risk?", icon: "🔍" },
];

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning.";
  if (hour < 17) return "Good afternoon.";
  return GREETINGS[Math.floor(Math.random() * GREETINGS.length)];
}

function useGreeting(): string {
  const [greeting, setGreeting] = useState("Hey there.");
  useEffect(() => {
    setGreeting(getGreeting());
  }, []);
  return greeting;
}

const PROCESS_ICONS: Record<string, string> = {
  collections: "💰",
  leasing: "📋",
  maintenance: "🔧",
  turnover: "🔄",
  performance: "📈",
};

function buildResearchSuggestions(schema: DomainSchemaResponse): Array<{ text: string; icon: string }> {
  const suggestions: Array<{ text: string; icon: string }> = [];

  suggestions.push({ text: "Write a full delinquency analysis across all managers", icon: "📊" });

  for (const proc of schema.processes.slice(0, 3)) {
    if (proc.name === "collections") {
      suggestions.push({ text: "Generate a delinquency risk report with trends", icon: "💰" });
    } else if (proc.name === "leasing") {
      suggestions.push({ text: "Generate a lease expiry risk report", icon: "📋" });
    } else if (proc.name === "maintenance") {
      suggestions.push({ text: "Identify maintenance patterns and surface any outliers", icon: "🔧" });
    }
  }

  if (schema.entity_types.find(et => et.name === "PropertyManager")) {
    suggestions.push({ text: "Compare manager performance over the last 90 days", icon: "🏆" });
  }

  if (suggestions.length < 5) {
    suggestions.push({ text: "Which properties carry the highest vacancy risk?", icon: "🔍" });
  }

  return suggestions.slice(0, 5);
}

function buildSuggestions(schema: DomainSchemaResponse): Array<{ text: string; icon: string }> {
  const suggestions: Array<{ text: string; icon: string }> = [];

  suggestions.push({ text: "How's my portfolio looking today?", icon: "📊" });

  const managerType = schema.entity_types.find(et => et.name === "PropertyManager");
  if (managerType) {
    suggestions.push({ text: "Which managers are performing best?", icon: "🏆" });
  }

  for (const proc of schema.processes.slice(0, 3)) {
    const icon = PROCESS_ICONS[proc.name] ?? "📋";
    const processLabel = proc.name.replace(/_/g, " ");
    if (proc.name === "collections") {
      suggestions.push({ text: "Show me the delinquency picture", icon });
    } else if (proc.name === "leasing") {
      suggestions.push({ text: "Are any leases expiring in the next 90 days?", icon });
    } else if (proc.name === "maintenance") {
      suggestions.push({ text: "Any open maintenance issues I should know about?", icon });
    } else {
      suggestions.push({ text: `What's happening with ${processLabel}?`, icon });
    }
  }

  if (suggestions.length < 5) {
    suggestions.push({ text: "What should I be paying attention to?", icon: "🔍" });
  }

  return suggestions.slice(0, 5);
}

function buildManagerSuggestions(
  managerName: string,
  schema: DomainSchemaResponse | null,
  mode: "ask" | "research" = "ask",
): Array<{ text: string; icon: string }> {
  if (mode === "research") {
    const base = [
      { text: `Write a full performance review for ${managerName}`, icon: "📊" },
      { text: `Analyze delinquency trends across ${managerName}'s portfolio`, icon: "💰" },
    ];
    if (schema) {
      if (schema.processes.some(p => p.name === "leasing")) {
        base.push({ text: `Generate a lease expiry risk report for ${managerName}`, icon: "📋" });
      }
      if (schema.processes.some(p => p.name === "maintenance")) {
        base.push({ text: `Identify maintenance outliers in ${managerName}'s properties`, icon: "🔧" });
      }
    }
    base.push({ text: `Which of ${managerName}'s properties are underperforming?`, icon: "🔍" });
    return base.slice(0, 5);
  }

  const base = [
    { text: `How is ${managerName} doing overall?`, icon: "👤" },
    { text: `Any issues with ${managerName}'s properties?`, icon: "🏠" },
  ];

  if (schema) {
    const hasCollections = schema.processes.some(p => p.name === "collections");
    const hasLeasing = schema.processes.some(p => p.name === "leasing");
    const hasMaintenance = schema.processes.some(p => p.name === "maintenance");

    if (hasCollections) {
      base.push({ text: `What's ${managerName}'s delinquency situation?`, icon: "💰" });
    }
    if (hasLeasing) {
      base.push({ text: `Are any of ${managerName}'s leases expiring soon?`, icon: "📋" });
    }
    if (hasMaintenance) {
      base.push({ text: `How's ${managerName} doing on maintenance?`, icon: "🔧" });
    }
  } else {
    base.push(
      { text: `What's ${managerName}'s occupancy rate?`, icon: "📊" },
      { text: `Are any of ${managerName}'s leases expiring soon?`, icon: "📋" },
    );
  }

  return base.slice(0, 5);
}

export function SessionEmptyState({
  onSend,
  connected,
  streaming,
  mode = "ask",
  managerName,
}: {
  onSend: (text: string) => void;
  connected: boolean;
  streaming: boolean;
  mode?: "ask" | "research";
  managerName?: string;
}) {
  const [schema, setSchema] = useState<DomainSchemaResponse | null>(null);
  const greeting = useGreeting();

  useEffect(() => {
    api.domainSchema().then(setSchema).catch(() => {});
  }, []);

  const suggestions = managerName
    ? buildManagerSuggestions(managerName, schema, mode)
    : mode === "research"
      ? schema
        ? buildResearchSuggestions(schema)
        : RESEARCH_SUGGESTIONS
      : schema
        ? buildSuggestions(schema)
        : FALLBACK_SUGGESTIONS;

  const subtitle = mode === "research"
    ? "Deep statistical analysis and multi-phase reports."
    : schema
      ? `${schema.entity_types.length} entity types, ${schema.processes.length} processes`
      : "Ask me anything about your portfolio.";

  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="flex flex-col items-center max-w-md w-full px-4 py-16">
        <div className="w-10 h-1 rounded-full bg-accent/40 mb-6" />

        <h2 className="text-lg font-medium text-fg mb-1 tracking-tight" suppressHydrationWarning>
          {greeting}
        </h2>
        <p className="text-sm text-fg-muted mb-10 text-center max-w-xs leading-relaxed">
          {managerName
            ? `Focused on ${managerName}'s portfolio.`
            : subtitle}
        </p>

        <div className="grid grid-cols-1 gap-2 w-full">
          {suggestions.map((q) => (
            <button
              key={q.text}
              onClick={() => onSend(q.text)}
              disabled={!connected || streaming}
              className="group text-left px-4 py-3 rounded-xl border border-border text-[13px] text-fg-muted hover:text-fg hover:border-accent/30 hover:bg-accent-soft transition-all disabled:opacity-30 leading-snug flex items-center gap-3"
            >
              <span className="text-base opacity-60 group-hover:opacity-100 transition-opacity">{q.icon}</span>
              <span>{q.text}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
