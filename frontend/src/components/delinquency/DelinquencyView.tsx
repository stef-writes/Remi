"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { fmt$ } from "@/lib/format";
import { MetricCard } from "@/components/ui/MetricCard";
import { MetricStrip } from "@/components/ui/MetricStrip";
import { PageContainer } from "@/components/ui/PageContainer";
import { Badge } from "@/components/ui/Badge";
import { ManagerFilter } from "@/components/ui/ManagerFilter";
import { useApiQuery } from "@/hooks/useApiQuery";
import type { DelinquencyBoard, EntityNoteResponse } from "@/lib/types";

interface NoteSeed {
  content: string;
  id: string | null;
}

function InlineNoteCell({
  tenantId,
  reportNote,
  seed,
  onMutate,
}: {
  tenantId: string;
  reportNote?: string | null;
  seed: NoteSeed | undefined;
  onMutate: () => void;
}) {
  const [userNote, setUserNote] = useState<string | null>(seed?.content ?? null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [noteId, setNoteId] = useState<string | null>(seed?.id ?? null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (seed !== undefined) {
      setUserNote(seed.content);
      setNoteId(seed.id);
    }
  }, [seed]);

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
      onMutate();
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

function useBatchNotes(tenantIds: string[]) {
  const [noteMap, setNoteMap] = useState<Record<string, NoteSeed>>({});
  const idsKey = tenantIds.join(",");

  const refresh = useCallback(() => {
    if (!tenantIds.length) return;
    api.batchEntityNotes("Tenant", tenantIds)
      .then((r) => {
        const map: Record<string, NoteSeed> = {};
        for (const [eid, notes] of Object.entries(r.notes_by_entity)) {
          const first = notes.find((n: EntityNoteResponse) => n.provenance === "user_stated");
          map[eid] = { content: first?.content || "", id: first?.id || null };
        }
        setNoteMap(map);
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idsKey]);

  useEffect(() => { refresh(); }, [refresh]);

  return { noteMap, refresh };
}

const STAGE_ORDER = ["current", "notice", "demand", "filing", "hearing", "evict", "judgment"] as const;
type Stage = typeof STAGE_ORDER[number];

const STAGE_LABELS: Record<Stage, string> = {
  current: "Current",
  notice: "Notice",
  demand: "Demand",
  filing: "Filing",
  hearing: "Hearing",
  evict: "Eviction",
  judgment: "Judgment",
};

const STAGE_VARIANTS: Record<Stage, "default" | "amber" | "red"> = {
  current: "default",
  notice: "amber",
  demand: "amber",
  filing: "red",
  hearing: "red",
  evict: "red",
  judgment: "red",
};

function collectionsStage(status: string): Stage {
  const s = status.toLowerCase().trim();
  if (STAGE_ORDER.includes(s as Stage)) return s as Stage;
  if (s.includes("evict")) return "evict";
  if (s.includes("notice")) return "notice";
  return "current";
}

function daysSincePayment(lastPayment: string | null): number | null {
  if (!lastPayment) return null;
  const d = new Date(lastPayment);
  if (isNaN(d.getTime())) return null;
  return Math.floor((Date.now() - d.getTime()) / 86_400_000);
}

export function DelinquencyView() {
  const [managerId, setManagerId] = useState("");
  const { data, loading } = useApiQuery<DelinquencyBoard>(
    () => api.delinquencyBoard(managerId || undefined),
    [managerId]
  );

  const tenantIds = data?.tenants.map((t) => t.tenant_id) ?? [];
  const { noteMap, refresh: refreshNotes } = useBatchNotes(tenantIds);

  return (
    <PageContainer>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
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
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">Stage</th>
                    <th className="text-right px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">Balance</th>
                    <th className="text-right px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">30+</th>
                    <th className="text-right px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">Days</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">Last Payment</th>
                    <th className="text-left px-4 py-2.5 text-[11px] font-semibold text-fg-muted uppercase tracking-wide">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {data.tenants.map((t) => {
                    const stage = collectionsStage(t.status);
                    const daysOverdue = daysSincePayment(t.last_payment_date);
                    const stuck = stage === "current" && (daysOverdue ?? 0) > 10;
                    return (
                      <tr key={t.tenant_id} className={`border-b border-border-subtle hover:bg-surface-raised transition-colors ${stuck ? "bg-error-soft/30" : ""}`}>
                        <td className="px-4 py-2.5 text-fg font-medium">{t.tenant_name}</td>
                        <td className="px-4 py-2.5 text-xs">
                          {t.property_id ? (
                            <Link href={`/properties/${t.property_id}`} className="text-fg-secondary hover:text-accent transition-colors">
                              {t.property_name || "—"}
                            </Link>
                          ) : (
                            <span className="text-fg-secondary">{t.property_name || "—"}</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-xs">
                          {t.property_id && t.unit_id ? (
                            <Link href={`/properties/${t.property_id}/units/${t.unit_id}`} className="text-fg-secondary hover:text-accent transition-colors">
                              {t.unit_number || "—"}
                            </Link>
                          ) : (
                            <span className="text-fg-secondary">{t.unit_number || "—"}</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5">
                          <Badge variant={STAGE_VARIANTS[stage]}>
                            {STAGE_LABELS[stage]}
                          </Badge>
                        </td>
                        <td className="px-4 py-2.5 text-right font-mono text-error">{fmt$(t.balance_owed)}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-warn">{fmt$(t.balance_30_plus)}</td>
                        <td className={`px-4 py-2.5 text-right font-mono ${(daysOverdue ?? 0) > 30 ? "text-error font-semibold" : "text-fg-secondary"}`}>
                          {daysOverdue != null ? daysOverdue : "—"}
                        </td>
                        <td className="px-4 py-2.5 text-fg-muted text-xs">{t.last_payment_date ?? "—"}</td>
                        <td className="px-4 py-2.5">
                          <InlineNoteCell
                            tenantId={t.tenant_id}
                            reportNote={t.delinquency_notes}
                            seed={noteMap[t.tenant_id]}
                            onMutate={refreshNotes}
                          />
                        </td>
                      </tr>
                    );
                  })}
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
