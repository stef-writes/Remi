"use client";

import { useCallback, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import type { FileEntry } from "@/hooks/useFileUpload";
import type { ManagerListItem, ReviewItem } from "@/lib/types";

const ACCEPT =
  ".csv,.xlsx,.xls,.pdf,.docx,.txt,.md,.jpg,.jpeg,.png,.gif,.webp";

interface UploadPanelProps {
  entries: FileEntry[];
  processing: boolean;
  onFiles: (files: FileList | File[]) => void;
  onClear: () => void;
  managers?: ManagerListItem[];
  selectedManagerId?: string;
  onManagerChange?: (managerId: string) => void;
}

function StatusIcon({ status }: { status: FileEntry["status"] }) {
  if (status === "queued") {
    return (
      <span className="w-4 h-4 rounded-full border-2 border-border-subtle" />
    );
  }
  if (status === "uploading") {
    return (
      <span className="w-4 h-4 rounded-full border-2 border-accent border-t-transparent animate-spin" />
    );
  }
  if (status === "done") {
    return (
      <svg className="w-4 h-4 text-ok" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
      </svg>
    );
  }
  return (
    <svg className="w-4 h-4 text-error" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}

const SEVERITY_STYLES: Record<string, string> = {
  action_needed: "border-error/20 bg-error-soft",
  warning: "border-warn/20 bg-warn-soft",
  info: "border-accent/20 bg-accent/5",
};

const SEVERITY_TEXT: Record<string, string> = {
  action_needed: "text-error",
  warning: "text-warn",
  info: "text-accent",
};

const SEVERITY_BADGE: Record<string, "blue" | "emerald" | "amber"> = {
  action_needed: "amber",
  warning: "amber",
  info: "blue",
};

const KIND_LABELS: Record<string, string> = {
  ambiguous_row: "Ambiguous Row",
  validation_warning: "Validation",
  entity_match: "Entity Match",
  classification_uncertain: "Unknown Type",
  manager_inferred: "Manager",
};

function ReviewItemCard({
  item,
  documentId,
  reportType,
  onResolved,
}: {
  item: ReviewItem;
  documentId: string;
  reportType: string;
  onResolved: (item: ReviewItem) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [resolved, setResolved] = useState(false);
  const [editData, setEditData] = useState<Record<string, string> | null>(null);

  const handleOptionSelect = async (optionId: string) => {
    setBusy(true);
    try {
      if (item.kind === "entity_match" && item.entity_type === "PropertyManager") {
        if (optionId !== "new" && item.entity_id) {
          await api.correctEntity(item.entity_type, item.entity_id, {
            resolved_to: optionId,
          });
        }
      }
      setResolved(true);
      onResolved(item);
    } catch {
      // resolution failed — user can retry
    } finally {
      setBusy(false);
    }
  };

  const handleCorrectRow = async () => {
    if (!editData || !item.row_data) return;
    setBusy(true);
    try {
      const corrected = { ...item.row_data, ...editData };
      const res = await api.correctRow(documentId, corrected, reportType);
      if (res.accepted) {
        setResolved(true);
        onResolved(item);
      }
    } catch {
      // correction failed — user can retry
    } finally {
      setBusy(false);
    }
  };

  if (resolved) {
    return (
      <div className="rounded-lg border border-ok/20 bg-ok/5 px-3 py-2 flex items-center gap-2">
        <svg className="w-3.5 h-3.5 text-ok shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
        </svg>
        <span className="text-[10px] text-ok">Resolved</span>
      </div>
    );
  }

  const style = SEVERITY_STYLES[item.severity] ?? SEVERITY_STYLES.info;
  const textStyle = SEVERITY_TEXT[item.severity] ?? SEVERITY_TEXT.info;
  const badgeVariant = SEVERITY_BADGE[item.severity] ?? "blue";

  return (
    <div className={`rounded-lg border ${style} px-3 py-2.5 space-y-2`}>
      <div className="flex items-start gap-2">
        <Badge variant={badgeVariant} className="shrink-0 mt-px">
          {KIND_LABELS[item.kind] ?? item.kind}
        </Badge>
        <p className={`text-[11px] ${textStyle} flex-1`}>{item.message}</p>
      </div>

      {item.suggestion && (
        <p className="text-[10px] text-fg-muted pl-1">
          Suggestion: {item.suggestion}
        </p>
      )}

      {/* Option buttons for entity_match / classification_uncertain */}
      {item.options && item.options.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pl-1">
          {item.options.map((opt) => (
            <button
              key={opt.id}
              onClick={() => handleOptionSelect(opt.id)}
              disabled={busy}
              className="px-2.5 py-1 rounded-md text-[10px] font-medium border border-border bg-surface hover:bg-surface-raised hover:border-fg-faint transition-all disabled:opacity-50"
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}

      {/* Editable row data for ambiguous_row items */}
      {item.kind === "ambiguous_row" && item.row_data && (
        <div className="space-y-1.5 pl-1">
          {!editData ? (
            <button
              onClick={() => {
                const initial: Record<string, string> = {};
                for (const [k, v] of Object.entries(item.row_data ?? {})) {
                  initial[k] = v != null ? String(v) : "";
                }
                setEditData(initial);
              }}
              className="text-[10px] text-accent hover:underline"
            >
              Edit and re-submit
            </button>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-1.5 max-h-40 overflow-y-auto">
                {Object.entries(editData).map(([key, val]) => (
                  <div key={key} className="flex flex-col gap-0.5">
                    <label className="text-[9px] text-fg-faint uppercase tracking-wide">{key}</label>
                    <input
                      type="text"
                      value={val}
                      onChange={(e) =>
                        setEditData((prev) => prev ? { ...prev, [key]: e.target.value } : prev)
                      }
                      className={`bg-surface border rounded px-1.5 py-0.5 text-[10px] text-fg focus:outline-none focus:border-accent/40 ${
                        key === item.field_name ? "border-error/40" : "border-border"
                      }`}
                    />
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleCorrectRow}
                  disabled={busy}
                  className="px-2.5 py-1 rounded-md text-[10px] font-medium bg-accent text-accent-fg hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  {busy ? "Submitting..." : "Re-submit"}
                </button>
                <button
                  onClick={() => setEditData(null)}
                  className="text-[10px] text-fg-faint hover:text-fg-secondary"
                >
                  Cancel
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function ReviewSection({
  items,
  documentId,
  reportType,
}: {
  items: ReviewItem[];
  documentId: string;
  reportType: string;
}) {
  const [expanded, setExpanded] = useState(true);
  const [resolvedCount, setResolvedCount] = useState(0);

  const actionItems = items.filter((i) => i.severity === "action_needed");
  const warningItems = items.filter((i) => i.severity === "warning");
  const infoItems = items.filter((i) => i.severity === "info");
  const sortedItems = [...actionItems, ...warningItems, ...infoItems];

  if (sortedItems.length === 0) return null;

  const needsAction = actionItems.length;
  const remaining = needsAction - resolvedCount;

  return (
    <div className="mt-2 space-y-1.5">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-2 w-full text-left"
      >
        <svg
          className={`w-3 h-3 text-fg-faint transition-transform ${expanded ? "rotate-90" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
        </svg>
        <span className="text-[10px] font-medium text-fg-secondary">
          {remaining > 0
            ? `${remaining} item${remaining !== 1 ? "s" : ""} need review`
            : `${sortedItems.length} review item${sortedItems.length !== 1 ? "s" : ""}`}
        </span>
        {remaining > 0 && (
          <span className="w-1.5 h-1.5 rounded-full bg-error animate-pulse" />
        )}
        {remaining === 0 && resolvedCount > 0 && (
          <svg className="w-3 h-3 text-ok" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
          </svg>
        )}
      </button>
      {expanded && (
        <div className="space-y-1.5 ml-5">
          {sortedItems.map((item, i) => (
            <ReviewItemCard
              key={`${item.kind}-${item.row_index ?? i}-${item.entity_id ?? ""}`}
              item={item}
              documentId={documentId}
              reportType={reportType}
              onResolved={() => setResolvedCount((c) => c + 1)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function DuplicateIcon() {
  return (
    <svg className="w-4 h-4 text-warn" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
    </svg>
  );
}

function FileRow({ entry }: { entry: FileEntry }) {
  const reviewItems = entry.result?.knowledge?.review_items ?? [];
  const isDuplicate = !!entry.result?.duplicate;

  return (
    <div className="py-2">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 shrink-0">
          {isDuplicate ? <DuplicateIcon /> : <StatusIcon status={entry.status} />}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-fg truncate">{entry.file.name}</p>
          {entry.status === "queued" && (
            <p className="text-[10px] text-fg-ghost mt-0.5">Waiting...</p>
          )}
          {entry.status === "uploading" && (
            <p className="text-[10px] text-accent mt-0.5">Processing...</p>
          )}
          {entry.status === "done" && entry.summary && (
            <p className={`text-[10px] mt-0.5 ${isDuplicate ? "text-warn" : "text-ok"}`}>{entry.summary}</p>
          )}
          {entry.status === "done" && entry.warnings.length > 0 && (
            <div className="mt-1 space-y-0.5">
              {entry.warnings.map((w, i) => (
                <p key={i} className={`text-[10px] ${isDuplicate ? "text-warn" : "text-warning"}`}>{w}</p>
              ))}
            </div>
          )}
          {entry.status === "error" && entry.error && (
            <p className="text-[10px] text-error mt-0.5">{entry.error}</p>
          )}
        </div>
        {entry.result && (
          <Badge variant={isDuplicate ? "amber" : "blue"} className="shrink-0 mt-0.5">
            {isDuplicate ? "duplicate" : entry.result.report_type.replace(/_/g, " ")}
          </Badge>
        )}
      </div>

      {entry.status === "done" && entry.result && reviewItems.length > 0 && (
        <ReviewSection
          items={reviewItems}
          documentId={entry.result.id}
          reportType={entry.result.report_type}
        />
      )}
    </div>
  );
}

export function UploadPanel({ entries, processing, onFiles, onClear, managers, selectedManagerId, onManagerChange }: UploadPanelProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      if (e.dataTransfer.files.length > 0) {
        onFiles(e.dataTransfer.files);
      }
    },
    [onFiles],
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (files && files.length > 0) {
        onFiles(files);
      }
      if (fileRef.current) fileRef.current.value = "";
    },
    [onFiles],
  );

  const hasEntries = entries.length > 0;
  const allDone = hasEntries && entries.every((e) => e.status === "done" || e.status === "error");
  const totalReviewItems = entries.reduce(
    (sum, e) => sum + (e.result?.knowledge?.review_items?.filter((ri) => ri.severity === "action_needed").length ?? 0),
    0,
  );

  const hasManagers = managers && managers.length > 0 && onManagerChange;

  return (
    <div className="space-y-3">
      {/* Manager scope selector */}
      {hasManagers && (
        <div className="rounded-xl border border-border-subtle bg-surface-sunken/50 px-4 py-3">
          <label className="block text-[10px] font-medium text-fg-faint uppercase tracking-wide mb-1.5">
            Which manager is this report for?
          </label>
          <select
            value={selectedManagerId ?? ""}
            onChange={(e) => onManagerChange(e.target.value)}
            disabled={processing}
            className="w-full bg-surface border border-border rounded-lg px-3 py-1.5 text-xs text-fg-secondary focus:outline-none focus:border-accent/40 disabled:opacity-50"
          >
            <option value="">All managers (portfolio-wide)</option>
            {managers
              .filter((m) => m.metrics.total_units > 0 || m.property_count > 0)
              .map((m) => (
                <option key={m.id} value={m.name}>{m.name}</option>
              ))}
          </select>
          {selectedManagerId ? (
            <p className="text-[10px] text-fg-ghost mt-1">
              Properties in this report will be assigned to this manager
            </p>
          ) : (
            <p className="text-[10px] text-fg-ghost mt-1">
              Properties keep their existing manager assignments
            </p>
          )}
        </div>
      )}

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`relative rounded-xl border-2 border-dashed transition-all ${
          dragOver
            ? "border-accent bg-accent/5"
            : "border-border-subtle hover:border-fg-faint"
        } ${processing ? "opacity-50 pointer-events-none" : ""}`}
      >
        <label className="flex flex-col items-center justify-center gap-2 py-8 cursor-pointer">
          <svg className="w-8 h-8 text-fg-ghost" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.338-2.32 3.75 3.75 0 013.572 5.345A3 3 0 0118 19.5H6.75z" />
          </svg>
          <div className="text-center">
            <p className="text-xs font-medium text-fg-secondary">
              Drop files here or <span className="text-accent">browse</span>
            </p>
            <p className="text-[10px] text-fg-ghost mt-1">
              CSV, Excel, PDF, Word, text, or images
            </p>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPT}
            multiple
            className="hidden"
            onChange={handleFileInput}
          />
        </label>
      </div>

      {/* File list */}
      {hasEntries && (
        <div className="rounded-xl border border-border-subtle divide-y divide-border-subtle">
          <div className="px-4 py-2 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <p className="text-[10px] text-fg-faint font-medium uppercase tracking-wide">
                {processing
                  ? `Uploading ${entries.filter((e) => e.status === "uploading").length} of ${entries.length}...`
                  : `${entries.length} file${entries.length !== 1 ? "s" : ""} processed`}
              </p>
              {totalReviewItems > 0 && !processing && (
                <span className="text-[10px] font-medium text-error">
                  {totalReviewItems} need{totalReviewItems === 1 ? "s" : ""} review
                </span>
              )}
            </div>
            {allDone && (
              <button
                onClick={onClear}
                className="text-[10px] text-fg-faint hover:text-fg-secondary transition-colors"
              >
                Clear
              </button>
            )}
          </div>
          <div className="px-4 divide-y divide-border-subtle">
            {entries.map((entry) => (
              <FileRow key={entry.id} entry={entry} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
