"use client";

import type { ModuleOutput } from "@/lib/types";
import { DashboardCardView } from "./DashboardCardView";
import { TableViewComponent } from "./TableViewComponent";
import { ProfileViewComponent } from "./ProfileViewComponent";
import { LLMResponseView } from "./LLMResponseView";
import { RawOutputView } from "./RawOutputView";

/**
 * The core mapping: contract string → React component.
 *
 * This is the "seamless" connection between backend and frontend.
 * The backend produces typed outputs with a `contract` label.
 * The frontend renders whatever the contract says it is.
 * Add new contracts here as you create new viewmodel modules.
 */
export function ContractRenderer({ module }: { module: ModuleOutput }) {
  const { output, contract } = module;

  if (!output || module.status !== "completed") {
    return <ModuleStatusBadge module={module} />;
  }

  switch (contract) {
    case "dashboard_card":
      return <DashboardCardView data={output as never} />;
    case "table_view":
      return <TableViewComponent data={output as never} />;
    case "profile_view":
      return <ProfileViewComponent data={output as never} />;
    case "llm_response":
      return <LLMResponseView data={output} />;
    case "list[record]":
      return (
        <TableViewComponent
          data={{
            title: module.module_id,
            columns: [],
            rows: (output as Record<string, unknown>[]) ?? [],
            total_count: Array.isArray(output) ? output.length : 0,
            page: 1,
            page_size: 50,
          }}
        />
      );
    default:
      return <RawOutputView data={output} contract={contract} />;
  }
}

function ModuleStatusBadge({ module }: { module: ModuleOutput }) {
  const colors: Record<string, string> = {
    pending: "bg-zinc-700 text-zinc-300",
    running: "bg-blue-500/20 text-blue-300 animate-pulse",
    completed: "bg-emerald-500/20 text-emerald-300",
    failed: "bg-red-500/20 text-red-300",
    skipped: "bg-zinc-700/50 text-zinc-500",
  };

  return (
    <div className="rounded-xl border border-zinc-700/50 p-4 flex items-center gap-3">
      <div
        className={`px-2.5 py-1 rounded-full text-xs font-medium ${
          colors[module.status] || colors.pending
        }`}
      >
        {module.status}
      </div>
      <span className="text-sm text-zinc-400 font-mono">{module.module_id}</span>
    </div>
  );
}
