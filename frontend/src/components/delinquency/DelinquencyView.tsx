"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { fmt$ } from "@/lib/format";
import { MetricCard } from "@/components/ui/MetricCard";
import { MetricStrip } from "@/components/ui/MetricStrip";
import { PageContainer } from "@/components/ui/PageContainer";
import { Badge } from "@/components/ui/Badge";
import { ManagerFilter } from "@/components/ui/ManagerFilter";
import { useApiQuery } from "@/hooks/useApiQuery";
import type { DelinquencyBoard } from "@/lib/types";

function InlineNoteCell({ tenantId, reportNote }: { tenantId: string; reportNote?: string | null }) {
  const [userNote, setUserNote] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [noteId, setNoteId] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    let cancelled = false;
    api.listEntityNotes("Tenant", tenantId)
      .then((r) => {
        if (cancelled) return;
        const first = r.notes.find((n) => n.provenance === "user_stated");
        setUserNote(first?.content || "");
        setNoteId(first?.id || null);
      })
      .catch(() => { if (!cancelled) setUserNote(""); });
    return () => { cancelled = true; };
  }, [tenantId]);

  const save = async () => {
    setSaving(true);
    try {
      if (noteId && draft) {
        await api.updateEntityNote(noteId, draft);
      } else if (noteId && !draft) {
        await api.deleteEntityNote(noteId);
        setNoteId(null);
      } else if (draft) {
        const created = await api.createEntityNote("Tenant", tenantId, draft);
        setNoteId(created.id);
      }
      setUserNote(draft);
      setEditing(false);
    } catch {
      /* keep editing */
    } finally {
      setSaving(false);
    }
  };

  if (userNote === null) return <span className="text-fg-ghost text-[10px]">...</span>;

  if (editing) {
    return (
      <div className="flex flex-col gap-1 min-w-[140px]">
        {reportNote && (
          <p className="text-[10px] text-fg-ghost italic mb-0.5" title="From report">{reportNote}</p>
        )}
        <textarea
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) save();
            if (e.key === "Escape") setEditing(false);
          }}
          rows={2}
          className="bg-surface border border-border rounded px-2 py-1 text-xs text-fg resize-none focus:outline-none focus:border-accent"
          autoFocus
        />
        <div className="flex gap-1">
          <button onClick={save} disabled={saving} className="text-[10px] text-accent hover:underline">
            {saving ? "..." : "Save"}
          </button>
          <button onClick={() => setEditing(false)} className="text-[10px] text-fg-ghost hover:underline">
            Cancel
          </button>
        </div>
      </div>
    );
  }

  const display = userNote || reportNote;
  return (
    <button
      onClick={() => { setDraft(userNote); setEditing(true); }}
      className="text-left text-xs max-w-[200px] truncate"
      title={display || "Click to add note"}
    >
      {reportNote && !userNote && (
        <span className="text-fg-ghost italic">{reportNote}</span>
      )}
      {userNote && (
        <span className="text-fg-muted">{userNote}</span>
      )}
      {!display && <span className="text-fg-ghost italic">+ note</span>}
    </button>
  );
}

export function DelinquencyView() {
  const [managerId, setManagerId] = useState("");
  const { data, loading } = useApiQuery<DelinquencyBoard>(
    () => api.delinquencyBoard(managerId || undefined),
    [managerId]
  );

  return (
    <PageContainer>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-fg">Delinquency</h1>
            <p className="text-sm text-fg-muted mt-1">
              Tenants with outstanding balances
            </p>
          </div>
          <ManagerFilter value={managerId} onChange={setManagerId} />
        </div>

        {data && (
          <MetricStrip className="lg:grid-cols-3">
            <MetricCard
              label="Delinquent Tenants"
              value={data.total_delinquent}
              alert={data.total_delinquent > 0}
            />
            <MetricCard
              label="Total Owed"
              value={fmt$(data.total_balance)}
              alert={data.total_balance > 0}
            />
            <MetricCard
              label="Avg Balance"
              value={data.total_delinquent > 0 ? fmt$(data.total_balance / data.total_delinquent) : "$0"}
            />
          </MetricStrip>
        )}

        {loading && (
          <div className="py-12 text-center text-sm text-fg-faint animate-pulse">Loading...</div>
        )}

        {!loading && data && data.tenants.length > 0 && (
          <div className="rounded-xl border border-border bg-surface overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">Tenant</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">Property</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">Unit</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">Status</th>
                    <th className="text-right px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">Balance</th>
                    <th className="text-right px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">0-30</th>
                    <th className="text-right px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">30+</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">Last Payment</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">Tags</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {data.tenants.map((t) => (
                    <tr key={t.tenant_id} className="border-b border-border-subtle hover:bg-surface-raised transition-colors">
                      <td className="px-4 py-2.5 text-fg font-medium">{t.tenant_name}</td>
                      <td className="px-4 py-2.5 text-fg-secondary text-xs">{t.property_name || "—"}</td>
                      <td className="px-4 py-2.5 text-fg-secondary font-mono text-xs">{t.unit_number || "—"}</td>
                      <td className="px-4 py-2.5">
                        <Badge variant={t.status === "evict" ? "red" : t.status === "notice" ? "amber" : "default"}>
                          {t.status}
                        </Badge>
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-error">{fmt$(t.balance_owed)}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-fg-secondary">{fmt$(t.balance_0_30)}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-warn">{fmt$(t.balance_30_plus)}</td>
                      <td className="px-4 py-2.5 text-fg-muted text-xs">{t.last_payment_date ?? "—"}</td>
                      <td className="px-4 py-2.5">
                        <div className="flex flex-wrap gap-1">
                          {t.tags.map((tag) => (
                            <Badge key={tag} variant="blue">{tag}</Badge>
                          ))}
                        </div>
                      </td>
                      <td className="px-4 py-2.5">
                        <InlineNoteCell tenantId={t.tenant_id} reportNote={t.delinquency_notes} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {!loading && data && data.tenants.length === 0 && (
          <div className="py-12 text-center text-sm text-fg-faint">
            No delinquent tenants found
          </div>
        )}
    </PageContainer>
  );
}
