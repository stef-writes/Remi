export interface UsageInfo {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  model?: string;
  provider?: string;
  cost?: number;
  latency_ms?: number;
  trace_id?: string;
  intent?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  tools?: ToolCall[];
  usage?: UsageInfo;
  error?: string;
  artifacts?: ResearchArtifact[];
}

export interface SessionSummary {
  id: string;
  agent: string;
  messageCount: number;
  preview: string;
  createdAt: string;
  updatedAt: string;
  streaming: boolean;
}

export interface ToolCall {
  id: string;
  tool: string;
  arguments: Record<string, unknown>;
  result?: unknown;
  result_schema?: string;
  status: "calling" | "done" | "error";
  duration?: number;
  elapsed_s?: number;
}

export interface ResearchArtifact {
  type: "research_report";
  title: string;
  summary: string[];
  charts: Array<{
    kind: "bar" | "line" | "scatter";
    title: string;
    x_label?: string;
    y_label?: string;
    data: Array<{ label: string; value: number }>;
  }>;
  findings: Array<{
    title: string;
    detail: string;
    severity: "info" | "warn" | "critical";
  }>;
  recommendations: string[];
}

export interface AgentMeta {
  name: string;
  description: string;
  version: string;
  primary: boolean;
  tags: string[];
}
