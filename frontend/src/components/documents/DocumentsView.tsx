"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Empty } from "@/components/ui/Empty";
import type { DocumentMeta, ManagerListItem, NeedsManagerResponse } from "@/lib/types";

// Lease expiration files self-tag each row — manager selection is optional for them.
// All other report types (rent roll, delinquency) must have a manager selected.
const SELF_TAGGING_TYPES = ["lease_expiration"];

export function DocumentsView() {
  const [documents, setDocuments] = useState<DocumentMeta[]>([]);
  const [managers, setManagers] = useState<ManagerListItem[]>([]);
  const [needsMgr, setNeedsMgr] = useState<NeedsManagerResponse | null>(null);
  const [selectedManager, setSelectedManager] = useState("");
  const [managerError, setManagerError] = useState<string | null>(null);
  const [autoAssigning, setAutoAssigning] = useState(false);
  const [autoAssignMsg, setAutoAssignMsg] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<(DocumentMeta & { preview: Record<string, unknown>[] }) | null>(null);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const [docs, mgrs, nm] = await Promise.all([
        api.listDocuments().catch(() => []),
        api.listManagers().catch(() => []),
        api.needsManager().catch(() => null),
      ]);
      setDocuments(docs);
      setManagers(mgrs);
      setNeedsMgr(nm);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // We don't know the report type until the server parses it.
    // Require a manager selection unless one is already chosen.
    // Lease expiration files self-tag, so we allow uploading without a manager,
    // but we still recommend it. We enforce the requirement client-side after
    // the first failed upload by checking the returned report_type.
    if (!selectedManager) {
      setManagerError("Select a property manager before uploading. Lease expiration files will use their built-in Tags, all other reports require a manager.");
      if (fileRef.current) fileRef.current.value = "";
      return;
    }

    setManagerError(null);
    setUploading(true);
    setUploadMsg(null);

    try {
      const result = await api.uploadDocument(file, selectedManager);
      const isSelfTagging = SELF_TAGGING_TYPES.includes(result.report_type);
      const mgrNote = isSelfTagging
        ? " (per-row tags used; manager selection acted as fallback)"
        : ` → ${selectedManager}`;
      setUploadMsg(
        `${result.filename}: ${result.row_count} rows · ${result.report_type.replace(/_/g, " ")} · ${result.knowledge.entities_extracted} entities extracted${mgrNote}`
      );
      await load();
    } catch (err) {
      setUploadMsg(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleAutoAssign = async () => {
    setAutoAssigning(true);
    setAutoAssignMsg(null);
    try {
      const result = await api.autoAssign();
      setAutoAssignMsg(result.message);
      await load();
    } catch (err) {
      setAutoAssignMsg(err instanceof Error ? err.message : "Auto-assign failed");
    } finally {
      setAutoAssigning(false);
    }
  };

  const selectDoc = async (id: string) => {
    setSelected(id);
    try {
      const [d, r] = await Promise.all([api.getDocument(id), api.queryRows(id, 100)]);
      setDetail(d);
      setRows(r.rows);
    } catch {
      setDetail(null);
      setRows([]);
    }
  };

  const handleDelete = async (id: string) => {
    await api.deleteDocument(id);
    setDocuments((prev) => prev.filter((d) => d.id !== id));
    if (selected === id) {
      setSelected(null);
      setDetail(null);
      setRows([]);
    }
  };

  const hasUnassigned = needsMgr && needsMgr.total > 0;

  return (
    <div className="h-full flex">
      {/* Sidebar */}
      <div className="w-72 shrink-0 border-r border-zinc-800/60 flex flex-col">
        <div className="p-4 border-b border-zinc-800/40 space-y-3">
          <h1 className="text-sm font-semibold text-zinc-300">Upload Reports</h1>

          {/* Manager selector — required */}
          <div>
            <label className="text-[10px] text-zinc-600 uppercase tracking-wide font-medium block mb-1">
              Property Manager <span className="text-red-500">*</span>
            </label>
            <select
              value={selectedManager}
              onChange={(e) => { setSelectedManager(e.target.value); setManagerError(null); }}
              className={`w-full bg-zinc-900 border rounded-lg px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-zinc-500 ${
                managerError ? "border-red-500/60" : "border-zinc-700"
              }`}
            >
              <option value="">Select a manager…</option>
              {managers.map((m) => (
                <option key={m.id} value={m.name}>
                  {m.name}
                </option>
              ))}
            </select>
            {managerError ? (
              <p className="text-[9px] text-red-400 mt-1 leading-relaxed">{managerError}</p>
            ) : (
              <p className="text-[9px] text-zinc-700 mt-1">
                Lease expiration files will also use their built-in Tags column
              </p>
            )}
          </div>

          {/* Upload button */}
          <label
            className={`flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg border border-dashed border-zinc-700 cursor-pointer hover:border-zinc-500 hover:bg-zinc-800/30 transition-all text-xs text-zinc-500 hover:text-zinc-300 ${uploading ? "opacity-50 pointer-events-none" : ""}`}
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
            </svg>
            {uploading ? "Uploading..." : "Upload CSV / Excel"}
            <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={handleUpload} />
          </label>

          {/* Upload result */}
          {uploadMsg && (
            <p className={`text-[10px] leading-relaxed ${uploadMsg.includes("fail") || uploadMsg.includes("error") ? "text-red-400" : "text-emerald-400"}`}>
              {uploadMsg}
            </p>
          )}

          {/* Auto-assign panel — shown when unassigned properties exist */}
          {hasUnassigned && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2.5 space-y-2">
              <div>
                <p className="text-[10px] text-amber-400 font-medium">
                  {needsMgr.total} {needsMgr.total === 1 ? "property" : "properties"} unassigned
                </p>
                <p className="text-[9px] text-amber-400/60 mt-0.5 leading-relaxed">
                  Detected manager tags in the knowledge store. Click to auto-assign.
                </p>
              </div>

              <button
                onClick={handleAutoAssign}
                disabled={autoAssigning}
                className="w-full px-3 py-1.5 rounded-md bg-amber-500/20 border border-amber-500/40 text-[10px] text-amber-300 font-medium hover:bg-amber-500/30 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {autoAssigning ? "Assigning…" : "Auto-assign from tags"}
              </button>

              {autoAssignMsg && (
                <p className={`text-[9px] leading-relaxed ${autoAssignMsg.includes("fail") || autoAssignMsg.includes("error") ? "text-red-400" : "text-emerald-400"}`}>
                  {autoAssignMsg}
                </p>
              )}
            </div>
          )}
        </div>

        {/* Document list */}
        <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
          <div className="px-2 py-1.5">
            <p className="text-[10px] text-zinc-600 uppercase tracking-wide font-medium">
              Uploaded Documents
            </p>
          </div>

          {loading && <div className="p-4 text-xs text-zinc-600 animate-pulse">Loading...</div>}

          {!loading && documents.length === 0 && (
            <Empty title="No documents" description="Upload a CSV or Excel file to get started" />
          )}

          {documents.map((doc) => (
            <button
              key={doc.id}
              onClick={() => selectDoc(doc.id)}
              className={`w-full text-left rounded-lg px-3 py-2.5 transition-all group ${
                selected === doc.id ? "bg-zinc-800/60" : "hover:bg-zinc-800/30"
              }`}
            >
              <div className="flex items-center gap-2">
                <span className="text-xs text-zinc-300 truncate flex-1">{doc.filename}</span>
                <button
                  onClick={(e) => { e.stopPropagation(); handleDelete(doc.id); }}
                  className="opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-red-400 transition-all"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                <p className="text-[10px] text-zinc-600">{doc.row_count} rows</p>
                {doc.report_type && doc.report_type !== "unknown" && (
                  <Badge variant="blue">{doc.report_type.replace(/_/g, " ")}</Badge>
                )}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Main content: data preview */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {!detail && (
          <div className="flex-1 flex items-center justify-center">
            <Empty title="Select a document" description="Choose a document to browse its data" />
          </div>
        )}

        {detail && (
          <>
            <div className="shrink-0 px-6 py-4 border-b border-zinc-800/40">
              <h2 className="text-sm font-bold text-zinc-200">{detail.filename}</h2>
              <div className="flex items-center gap-3 mt-1">
                <span className="text-[10px] text-zinc-600">{detail.row_count} rows</span>
                <div className="flex flex-wrap gap-1">
                  {detail.columns.map((c) => (
                    <Badge key={c} variant="blue">{c}</Badge>
                  ))}
                </div>
              </div>
            </div>

            <div className="flex-1 overflow-auto">
              {rows.length > 0 ? (
                <table className="w-full text-[11px]">
                  <thead className="sticky top-0 bg-zinc-950 z-10">
                    <tr>
                      <th className="text-left px-3 py-2 text-zinc-600 font-mono border-b border-zinc-800/40">#</th>
                      {detail.columns.map((c) => (
                        <th key={c} className="text-left px-3 py-2 text-zinc-600 font-mono border-b border-zinc-800/40 whitespace-nowrap">{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, i) => (
                      <tr key={i} className="hover:bg-zinc-800/20 transition-colors">
                        <td className="px-3 py-1.5 text-zinc-700 border-b border-zinc-800/20">{i + 1}</td>
                        {detail.columns.map((c) => (
                          <td key={c} className="px-3 py-1.5 text-zinc-400 border-b border-zinc-800/20 max-w-[200px] truncate">
                            {row[c] != null ? String(row[c]) : <span className="text-zinc-800">&mdash;</span>}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="p-8 text-center text-xs text-zinc-600">No rows</div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
