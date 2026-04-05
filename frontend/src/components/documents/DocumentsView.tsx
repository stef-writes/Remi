"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Empty } from "@/components/ui/Empty";
import { UploadPanel } from "@/components/documents/UploadPanel";
import { useFileUpload } from "@/hooks/useFileUpload";
import type { DocumentMeta, DocumentKind, ManagerListItem, SignalSummary } from "@/lib/types";

const KIND_LABELS: Record<DocumentKind, string> = {
  tabular: "Report",
  text: "Document",
  image: "Image",
};

const KIND_COLORS: Record<DocumentKind, "blue" | "emerald" | "amber"> = {
  tabular: "blue",
  text: "emerald",
  image: "amber",
};

function FileIcon({ kind, className = "w-5 h-5" }: { kind: DocumentKind; className?: string }) {
  if (kind === "image") {
    return (
      <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0022.5 18.75V5.25A2.25 2.25 0 0020.25 3H3.75A2.25 2.25 0 001.5 5.25v13.5A2.25 2.25 0 003.75 21z" />
      </svg>
    );
  }
  if (kind === "text") {
    return (
      <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
      </svg>
    );
  }
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 01-1.125-1.125M3.375 19.5h7.5c.621 0 1.125-.504 1.125-1.125m-9.75 0V5.625m0 12.75v-1.5c0-.621.504-1.125 1.125-1.125m18.375 2.625V5.625m0 12.75c0 .621-.504 1.125-1.125 1.125m1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125m0 3.75h-7.5A1.125 1.125 0 0112 18.375m9.75-12.75c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125m19.5 0v1.5c0 .621-.504 1.125-1.125 1.125M2.25 5.625v1.5c0 .621.504 1.125 1.125 1.125m0 0h17.25m-17.25 0h7.5c.621 0 1.125.504 1.125 1.125M3.375 8.25c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125m17.25-3.75h-7.5c-.621 0-1.125.504-1.125 1.125m8.625-1.125c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125m-17.25 0h7.5m-7.5 0c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125M12 10.875v-1.5m0 1.5c0 .621-.504 1.125-1.125 1.125M12 10.875c0 .621.504 1.125 1.125 1.125m-2.25 0c.621 0 1.125.504 1.125 1.125M13.125 12h7.5m-7.5 0c-.621 0-1.125.504-1.125 1.125M20.625 12c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125m-17.25 0h7.5M12 14.625v-1.5m0 1.5c0 .621-.504 1.125-1.125 1.125M12 14.625c0 .621.504 1.125 1.125 1.125m-2.25 0c.621 0 1.125.504 1.125 1.125m0 0v.375" />
    </svg>
  );
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

type DetailDoc = DocumentMeta & { preview: Record<string, unknown>[] };

type Tab = "documents" | "signals" | "activity";

const SEVERITY_COLORS: Record<string, string> = {
  critical: "bg-error text-error-fg",
  high: "bg-warning text-warning-fg",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-surface-sunken text-fg-muted",
};

export function DocumentsView() {
  const [documents, setDocuments] = useState<DocumentMeta[]>([]);
  const [managers, setManagers] = useState<ManagerListItem[]>([]);
  const [allTags, setAllTags] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [kindFilter, setKindFilter] = useState<string>("");
  const [tagFilter, setTagFilter] = useState<string>("");
  const [selectedManager, setSelectedManager] = useState("");

  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<DetailDoc | null>(null);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [chunks, setChunks] = useState<{ index: number; text: string; page: number | null }[]>([]);

  const [loading, setLoading] = useState(true);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [showUpload, setShowUpload] = useState(false);

  const [activeTab, setActiveTab] = useState<Tab>("documents");
  const [signals, setSignals] = useState<SignalSummary[]>([]);
  const [signalsLoading, setSignalsLoading] = useState(false);
  const [events, setEvents] = useState<Array<Record<string, unknown>>>([]);
  const [eventsLoading, setEventsLoading] = useState(false);

  const [editingTags, setEditingTags] = useState(false);
  const [editTagValue, setEditTagValue] = useState("");

  const load = useCallback(async () => {
    try {
      const [docs, mgrs, tags] = await Promise.all([
        api.listDocuments({
          q: searchQuery || undefined,
          kind: kindFilter || undefined,
          tags: tagFilter || undefined,
        }).catch(() => []),
        api.listManagers().catch(() => []),
        api.listDocumentTags().catch(() => []),
      ]);
      setDocuments(docs);
      setManagers(mgrs);
      setAllTags(tags);
    } finally {
      setLoading(false);
    }
  }, [searchQuery, kindFilter, tagFilter]);

  useEffect(() => {
    setLoading(true);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => load(), 200);
    return () => clearTimeout(debounceRef.current);
  }, [load]);

  const upload = useFileUpload({
    manager: selectedManager || undefined,
    onAllComplete: load,
  });

  useEffect(() => {
    if (activeTab === "signals" && signals.length === 0) {
      setSignalsLoading(true);
      api.listSignals().then((r) => setSignals(r.signals)).catch(() => {}).finally(() => setSignalsLoading(false));
    }
    if (activeTab === "activity" && events.length === 0) {
      setEventsLoading(true);
      api.listEvents(30).then((r) => setEvents(r.changesets as unknown as Array<Record<string, unknown>>)).catch(() => {}).finally(() => setEventsLoading(false));
    }
  }, [activeTab, signals.length, events.length]);

  const selectDoc = async (id: string) => {
    setSelected(id);
    setRows([]);
    setChunks([]);
    setEditingTags(false);
    try {
      const d = await api.getDocument(id);
      setDetail(d);
      if (d.kind === "tabular") {
        const r = await api.queryRows(id, 100);
        setRows(r.rows);
      } else if (d.kind === "text") {
        const c = await api.queryChunks(id, 100);
        setChunks(c.chunks);
      }
    } catch {
      setDetail(null);
    }
  };

  const handleDelete = async (id: string) => {
    await api.deleteDocument(id);
    setDocuments((prev) => prev.filter((d) => d.id !== id));
    if (selected === id) {
      setSelected(null);
      setDetail(null);
      setRows([]);
      setChunks([]);
    }
  };

  const handleSaveTags = async () => {
    if (!detail) return;
    const newTags = editTagValue.split(",").map((t) => t.trim()).filter(Boolean);
    try {
      await api.updateDocumentTags(detail.id, newTags);
      setDetail({ ...detail, tags: newTags });
      setDocuments((prev) => prev.map((d) => d.id === detail.id ? { ...d, tags: newTags } : d));
      setEditingTags(false);
      const freshTags = await api.listDocumentTags().catch(() => []);
      setAllTags(freshTags);
    } catch (err) {
      console.warn("Failed to update tags:", err);
    }
  };

  const kindCounts = documents.reduce<Record<string, number>>((acc, d) => {
    acc[d.kind] = (acc[d.kind] || 0) + 1;
    return acc;
  }, {});

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: "documents", label: "Documents", count: documents.length },
    { key: "signals", label: "Signals", count: signals.length },
    { key: "activity", label: "Activity" },
  ];

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="shrink-0 border-b border-border-subtle px-4 sm:px-6 py-4 space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-bold text-fg tracking-tight">Knowledge Base</h1>
            <p className="text-[11px] text-fg-faint mt-0.5">
              Documents, signals, and activity across your portfolio
            </p>
          </div>

          <div className="flex items-center gap-2 sm:gap-3">
            <select
              value={selectedManager}
              onChange={(e) => setSelectedManager(e.target.value)}
              className="bg-surface border border-border rounded-lg px-3 py-1.5 text-xs text-fg-secondary focus:outline-none focus:border-fg-faint min-w-0"
            >
              <option value="">All managers</option>
              {managers.map((m) => (
                <option key={m.id} value={m.name}>{m.name}</option>
              ))}
            </select>

            <button
              onClick={() => setShowUpload((v) => !v)}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-accent text-accent-fg text-xs font-medium hover:opacity-90 transition-opacity shrink-0"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              <span className="hidden sm:inline">Upload</span>
              {upload.processing && (
                <span className="w-3 h-3 rounded-full border-2 border-accent-fg border-t-transparent animate-spin" />
              )}
            </button>
          </div>
        </div>

        {showUpload && (
          <UploadPanel
            entries={upload.entries}
            processing={upload.processing}
            onFiles={upload.addFiles}
            onClear={upload.clear}
          />
        )}

        {/* Tabs */}
        <div className="flex items-center gap-1 border-b border-border-subtle -mb-3 -mx-4 sm:-mx-6 px-4 sm:px-6 overflow-x-auto">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-3 py-2 text-xs font-medium border-b-2 transition-all -mb-px ${
                activeTab === tab.key
                  ? "border-accent text-fg"
                  : "border-transparent text-fg-muted hover:text-fg-secondary"
              }`}
            >
              {tab.label}
              {tab.count != null && tab.count > 0 && (
                <span className="ml-1.5 text-[10px] opacity-60">({tab.count})</span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Documents tab */}
      {activeTab === "documents" && (
        <>
          {/* Search + Filters */}
          <div className="shrink-0 px-4 sm:px-6 py-3 flex flex-wrap items-center gap-2 border-b border-border-subtle">
            <div className="relative flex-1 min-w-[180px] max-w-md">
              <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-fg-ghost" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
              </svg>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search documents..."
                className="w-full bg-surface border border-border rounded-lg pl-9 pr-3 py-1.5 text-xs text-fg placeholder-fg-ghost focus:outline-none focus:border-accent/40 transition-all"
              />
            </div>

            <div className="flex items-center gap-1">
              {(["", "tabular", "text", "image"] as const).map((k) => {
                const label = k === "" ? "All" : KIND_LABELS[k];
                const count = k === "" ? documents.length : (kindCounts[k] || 0);
                const active = kindFilter === k;
                return (
                  <button
                    key={k}
                    onClick={() => setKindFilter(k)}
                    className={`px-2.5 py-1 rounded-md text-[10px] font-medium transition-all ${
                      active
                        ? "bg-accent text-accent-fg"
                        : "bg-surface-raised text-fg-muted hover:text-fg-secondary"
                    }`}
                  >
                    {label} {count > 0 && <span className="opacity-60">({count})</span>}
                  </button>
                );
              })}
            </div>

            {allTags.length > 0 && (
              <select
                value={tagFilter}
                onChange={(e) => setTagFilter(e.target.value)}
                className="bg-surface border border-border rounded-lg px-2 py-1.5 text-[10px] text-fg-secondary focus:outline-none"
              >
                <option value="">All tags</option>
                {allTags.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            )}
          </div>

          {/* Content */}
          <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
            {/* Document grid */}
            <div className={`flex-1 overflow-y-auto p-4 ${detail ? "hidden lg:block" : ""}`}>
              {loading && <div className="p-8 text-center text-xs text-fg-faint animate-pulse">Loading...</div>}

              {!loading && documents.length === 0 && (
                <div className="flex items-center justify-center h-full">
                  <Empty
                    title="No documents"
                    description="Upload CSV, Excel, PDF, Word, or text files to build your knowledge base"
                  />
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {documents.map((doc) => (
                  <div
                    key={doc.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => selectDoc(doc.id)}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectDoc(doc.id); } }}
                    className={`rounded-xl border p-4 transition-all cursor-pointer group ${
                      selected === doc.id
                        ? "border-accent/40 bg-accent/5"
                        : "border-border hover:border-fg-faint hover:bg-surface-raised"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 text-fg-faint">
                        <FileIcon kind={doc.kind} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium text-fg truncate">{doc.filename}</p>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleDelete(doc.id); }}
                            className="opacity-0 group-hover:opacity-100 text-fg-faint hover:text-error transition-all shrink-0"
                            aria-label={`Delete ${doc.filename}`}
                          >
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          </button>
                        </div>
                        <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                          <Badge variant={KIND_COLORS[doc.kind]}>{KIND_LABELS[doc.kind]}</Badge>
                          {doc.kind === "tabular" && doc.report_type && doc.report_type !== "unknown" && (
                            <Badge variant="blue">{doc.report_type.replace(/_/g, " ")}</Badge>
                          )}
                          {doc.tags.map((t) => (
                            <span key={t} className="text-[9px] px-1.5 py-0.5 rounded bg-surface-sunken text-fg-faint">{t}</span>
                          ))}
                        </div>
                        <div className="flex items-center gap-3 mt-2 text-[10px] text-fg-faint">
                          {doc.kind === "tabular" && <span>{doc.row_count} rows</span>}
                          {doc.kind === "text" && (
                            <>
                              {doc.page_count > 0 && <span>{doc.page_count} pages</span>}
                              <span>{doc.chunk_count} passages</span>
                            </>
                          )}
                          {doc.size_bytes > 0 && <span>{formatBytes(doc.size_bytes)}</span>}
                          <span>{formatDate(doc.uploaded_at)}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Detail panel */}
            {detail && (
              <div className="w-full lg:w-[480px] shrink-0 border-t lg:border-t-0 lg:border-l border-border flex flex-col overflow-hidden">
                <div className="shrink-0 px-4 sm:px-5 py-4 border-b border-border-subtle">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => { setSelected(null); setDetail(null); setRows([]); setChunks([]); }}
                      className="lg:hidden shrink-0 w-7 h-7 rounded-lg flex items-center justify-center text-fg-muted hover:text-fg hover:bg-surface-sunken transition-colors"
                      aria-label="Back to documents"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
                      </svg>
                    </button>
                    <FileIcon kind={detail.kind} className="w-4 h-4 text-fg-muted shrink-0" />
                    <h2 className="text-sm font-bold text-fg truncate">{detail.filename}</h2>
                  </div>
                  <div className="flex items-center gap-2 mt-2 flex-wrap">
                    <Badge variant={KIND_COLORS[detail.kind]}>{KIND_LABELS[detail.kind]}</Badge>
                    {detail.kind === "tabular" && detail.report_type !== "unknown" && (
                      <Badge variant="blue">{detail.report_type.replace(/_/g, " ")}</Badge>
                    )}
                    {detail.size_bytes > 0 && (
                      <span className="text-[10px] text-fg-faint">{formatBytes(detail.size_bytes)}</span>
                    )}
                    <span className="text-[10px] text-fg-faint">{formatDate(detail.uploaded_at)}</span>
                  </div>

                  {/* Tags with inline edit */}
                  <div className="mt-2">
                    {editingTags ? (
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          value={editTagValue}
                          onChange={(e) => setEditTagValue(e.target.value)}
                          placeholder="tag1, tag2, tag3"
                          className="flex-1 bg-surface border border-border rounded px-2 py-1 text-[10px] text-fg focus:outline-none focus:border-accent/40"
                          onKeyDown={(e) => { if (e.key === "Enter") handleSaveTags(); if (e.key === "Escape") setEditingTags(false); }}
                          autoFocus
                        />
                        <button onClick={handleSaveTags} className="text-[10px] text-accent hover:underline">Save</button>
                        <button onClick={() => setEditingTags(false)} className="text-[10px] text-fg-faint hover:text-fg-secondary">Cancel</button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1 flex-wrap">
                        {detail.tags.length > 0 ? (
                          detail.tags.map((t) => (
                            <span key={t} className="text-[9px] px-1.5 py-0.5 rounded bg-surface-sunken text-fg-faint">{t}</span>
                          ))
                        ) : (
                          <span className="text-[9px] text-fg-ghost">No tags</span>
                        )}
                        <button
                          onClick={() => { setEditTagValue(detail.tags.join(", ")); setEditingTags(true); }}
                          className="text-[9px] text-accent/70 hover:text-accent ml-1"
                        >
                          edit
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex-1 overflow-auto">
                  {detail.kind === "tabular" && rows.length > 0 && (
                    <table className="w-full text-[11px]">
                      <thead className="sticky top-0 bg-surface z-10">
                        <tr>
                          <th className="text-left px-3 py-2 text-fg-faint font-mono border-b border-border-subtle">#</th>
                          {detail.columns.map((c) => (
                            <th key={c} className="text-left px-3 py-2 text-fg-faint font-mono border-b border-border-subtle whitespace-nowrap">{c}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row, i) => (
                          <tr key={i} className="hover:bg-surface-raised transition-colors">
                            <td className="px-3 py-1.5 text-fg-ghost border-b border-border-subtle">{i + 1}</td>
                            {detail.columns.map((c) => (
                              <td key={c} className="px-3 py-1.5 text-fg-secondary border-b border-border-subtle max-w-[200px] truncate">
                                {row[c] != null ? String(row[c]) : <span className="text-fg-ghost">&mdash;</span>}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}

                  {detail.kind === "text" && chunks.length > 0 && (
                    <div className="p-4 space-y-3">
                      {chunks.map((chunk) => (
                        <div key={chunk.index} className="rounded-lg border border-border-subtle p-3">
                          {chunk.page != null && (
                            <p className="text-[9px] text-fg-ghost uppercase tracking-wide font-medium mb-1.5">
                              Page {chunk.page + 1}
                            </p>
                          )}
                          <p className="text-xs text-fg-secondary leading-relaxed whitespace-pre-wrap">
                            {chunk.text}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}

                  {detail.kind === "image" && (
                    <div className="flex items-center justify-center h-full p-8">
                      <div className="text-center">
                        <FileIcon kind="image" className="w-12 h-12 text-fg-ghost mx-auto mb-3" />
                        <p className="text-xs text-fg-faint">Image preview not available</p>
                        <p className="text-[10px] text-fg-ghost mt-1">{detail.filename}</p>
                      </div>
                    </div>
                  )}

                  {detail.kind === "tabular" && rows.length === 0 && (
                    <div className="p-8 text-center text-xs text-fg-faint">No rows</div>
                  )}
                  {detail.kind === "text" && chunks.length === 0 && (
                    <div className="p-8 text-center text-xs text-fg-faint">No text content extracted</div>
                  )}
                </div>

                <div className="shrink-0 px-4 sm:px-5 py-3 border-t border-border-subtle">
                  <a
                    href={`/ask?q=${encodeURIComponent(`Tell me about the document "${detail.filename}"`)}`}
                    className="flex items-center justify-center gap-2 w-full px-3 py-2 rounded-lg border border-border text-xs text-fg-muted hover:text-fg-secondary hover:border-fg-faint transition-all"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
                    </svg>
                    Ask REMI about this document
                  </a>
                </div>
              </div>
            )}

            {!detail && !loading && documents.length > 0 && (
              <div className="hidden lg:flex w-[480px] shrink-0 border-l border-border items-center justify-center">
                <Empty title="Select a document" description="Choose a document to view its contents" />
              </div>
            )}
          </div>
        </>
      )}

      {/* Signals tab */}
      {activeTab === "signals" && (
        <div className="flex-1 overflow-y-auto p-6">
          {signalsLoading && <div className="p-8 text-center text-xs text-fg-faint animate-pulse">Loading signals...</div>}
          {!signalsLoading && signals.length === 0 && (
            <div className="flex items-center justify-center h-64">
              <Empty
                title="No signals detected"
                description="Signals appear when REMI detects notable situations in your portfolio data"
              />
            </div>
          )}
          {!signalsLoading && signals.length > 0 && (
            <div className="space-y-3 max-w-4xl">
              {signals.map((sig) => (
                <div key={sig.signal_id} className="rounded-xl border border-border p-4 hover:bg-surface-raised transition-colors">
                  <div className="flex items-start gap-3">
                    <span className={`mt-0.5 inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold ${SEVERITY_COLORS[sig.severity] ?? SEVERITY_COLORS.low}`}>
                      {sig.severity}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-fg">{sig.description}</p>
                      <div className="flex items-center gap-3 mt-1.5 text-[10px] text-fg-faint">
                        <span>{sig.signal_type.replace(/_/g, " ")}</span>
                        <span>&middot;</span>
                        <span>{sig.entity_name}</span>
                        <span>&middot;</span>
                        <span>{formatDate(sig.detected_at)}</span>
                      </div>
                    </div>
                    <a
                      href={`/ask?q=${encodeURIComponent(`Explain the ${sig.signal_type.replace(/_/g, " ")} signal for ${sig.entity_name}`)}`}
                      className="shrink-0 text-[10px] text-accent/70 hover:text-accent"
                    >
                      Ask REMI
                    </a>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Activity tab */}
      {activeTab === "activity" && (
        <div className="flex-1 overflow-y-auto p-6">
          {eventsLoading && <div className="p-8 text-center text-xs text-fg-faint animate-pulse">Loading activity...</div>}
          {!eventsLoading && events.length === 0 && (
            <div className="flex items-center justify-center h-64">
              <Empty title="No activity yet" description="Events will appear as data is ingested and entities change" />
            </div>
          )}
          {!eventsLoading && events.length > 0 && (
            <div className="space-y-2 max-w-4xl">
              {events.map((evt, i) => (
                <div key={(evt.changeset_id as string) ?? i} className="rounded-lg border border-border-subtle p-3 flex items-center gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-fg">
                      {String(evt.source ?? "")}
                      {evt.report_type ? <span className="text-fg-faint ml-2">{String(evt.report_type).replace(/_/g, " ")}</span> : null}
                    </p>
                    <div className="flex items-center gap-3 mt-1 text-[10px] text-fg-faint">
                      {(evt.created as number) > 0 && <span className="text-ok">+{evt.created as number} created</span>}
                      {(evt.updated as number) > 0 && <span className="text-accent">{evt.updated as number} updated</span>}
                      {(evt.removed as number) > 0 && <span className="text-error">{evt.removed as number} removed</span>}
                    </div>
                  </div>
                  <span className="text-[10px] text-fg-ghost shrink-0">
                    {evt.timestamp ? formatDate(evt.timestamp as string) : ""}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
