"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import type {
  MeetingBriefResponse,
  MeetingBriefListResponse,
  MeetingAgendaItem,
  EntityNoteResponse,
} from "@/lib/types";

/* ------------------------------------------------------------------ */
/* Formatting helpers                                                  */
/* ------------------------------------------------------------------ */

const SEVERITY_VARIANT: Record<string, "red" | "amber" | "blue"> = {
  high: "red",
  medium: "amber",
  low: "blue",
};

const OWNER_LABEL: Record<string, string> = {
  manager: "PM",
  director: "Director",
  both: "Joint",
};

function fmtTimestamp(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function fmtDateShort(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

/* ------------------------------------------------------------------ */
/* Timeline entry types                                                */
/* ------------------------------------------------------------------ */

type TimelineEntry =
  | { kind: "brief"; ts: string; data: MeetingBriefResponse }
  | { kind: "note"; ts: string; data: EntityNoteResponse };

function buildTimeline(
  briefs: MeetingBriefResponse[],
  notes: EntityNoteResponse[],
): TimelineEntry[] {
  const entries: TimelineEntry[] = [
    ...briefs.map((b) => ({ kind: "brief" as const, ts: b.generated_at, data: b })),
    ...notes.map((n) => ({ kind: "note" as const, ts: n.created_at ?? n.updated_at ?? "", data: n })),
  ];
  entries.sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime());
  return entries;
}

/* ------------------------------------------------------------------ */
/* Agenda card (compact)                                               */
/* ------------------------------------------------------------------ */

function AgendaCard({ item, index }: { item: MeetingAgendaItem; index: number }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg border border-border-subtle bg-surface-sunken/30 overflow-hidden">
      <button
        onClick={() => setExpanded((x) => !x)}
        className="w-full flex items-center gap-2 px-3.5 py-2.5 text-left hover:bg-surface-raised/50 transition-colors"
      >
        <span className="shrink-0 w-5 h-5 rounded-full bg-surface border border-border-subtle flex items-center justify-center text-[9px] font-bold text-fg-muted">
          {index + 1}
        </span>
        <span className="flex-1 text-xs font-medium text-fg">{item.topic}</span>
        <Badge variant={SEVERITY_VARIANT[item.severity] ?? "blue"}>{item.severity}</Badge>
        <svg
          className={`w-3 h-3 text-fg-muted transition-transform ${expanded ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
        </svg>
      </button>

      {expanded && (
        <div className="px-3.5 pb-3 space-y-2.5 border-t border-border-subtle">
          {item.talking_points.length > 0 && (
            <div className="pt-2.5">
              <ul className="space-y-1">
                {item.talking_points.map((tp, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-xs text-fg-secondary">
                    <span className="shrink-0 mt-1 w-1 h-1 rounded-full bg-accent/60" />
                    {tp}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {item.questions.length > 0 && (
            <div>
              {item.questions.map((q, i) => (
                <p key={i} className="text-xs text-fg-secondary italic flex items-start gap-1.5">
                  <span className="shrink-0 text-accent mt-0.5 text-[10px]">?</span>
                  {q}
                </p>
              ))}
            </div>
          )}

          {item.suggested_actions.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {item.suggested_actions.map((action, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1 text-[10px] bg-surface border border-border-subtle rounded px-2 py-1 text-fg-muted"
                >
                  <span className="font-medium text-fg">{action.title}</span>
                  <span className="text-fg-faint">{OWNER_LABEL[action.owner] ?? action.owner}</span>
                  <span className="text-fg-ghost">{action.timeframe}</span>
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Brief card (in timeline)                                            */
/* ------------------------------------------------------------------ */

function BriefCard({
  brief,
  currentHash,
}: {
  brief: MeetingBriefResponse;
  currentHash: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const b = brief.brief;
  const analysis = brief.analysis;
  const isStale = currentHash !== null && brief.snapshot_hash !== currentHash;

  return (
    <div className="rounded-xl border border-border bg-surface overflow-hidden">
      <button
        onClick={() => setExpanded((x) => !x)}
        className="w-full text-left px-4 py-3 hover:bg-surface-raised/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center shrink-0">
            <svg className="w-3.5 h-3.5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold text-fg">Meeting Brief</span>
              {brief.focus && <Badge variant="default">{brief.focus}</Badge>}
              {isStale ? (
                <span className="text-[9px] text-warn bg-warn-soft px-1 py-0.5 rounded">stale</span>
              ) : (
                <span className="text-[9px] text-ok bg-ok/10 px-1 py-0.5 rounded">current</span>
              )}
            </div>
            <p className="text-xs text-fg-muted mt-0.5 line-clamp-1">{b.summary}</p>
          </div>
          <svg
            className={`w-4 h-4 text-fg-muted shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
          </svg>
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-4 border-t border-border-subtle">
          {/* Summary */}
          <div className="pt-3">
            <p className="text-sm text-fg-secondary leading-relaxed whitespace-pre-line">{b.summary}</p>
          </div>

          {/* Positives */}
          {b.positives.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {b.positives.map((p, i) => (
                <span key={i} className="inline-flex items-center gap-1 text-xs text-ok bg-ok/5 border border-ok/20 rounded-lg px-2 py-1">
                  <span className="text-ok">+</span> {p}
                </span>
              ))}
            </div>
          )}

          {/* Agenda */}
          {b.agenda.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-[10px] font-semibold text-fg-muted uppercase tracking-wide">
                Agenda &middot; {b.agenda.length} items
                {b.follow_up_date && <span className="font-normal text-fg-faint"> &middot; Follow-up: {b.follow_up_date}</span>}
              </h4>
              {b.agenda.map((item, i) => (
                <AgendaCard key={i} item={item} index={i} />
              ))}
            </div>
          )}

          {/* Analysis themes */}
          {analysis?.themes && analysis.themes.length > 0 && (
            <div className="space-y-1.5">
              <h4 className="text-[10px] font-semibold text-fg-muted uppercase tracking-wide">Themes</h4>
              {analysis.themes.map((theme) => (
                <div key={theme.id} className="flex items-center gap-2 text-xs">
                  <Badge variant={SEVERITY_VARIANT[theme.severity] ?? "blue"}>{theme.severity}</Badge>
                  <span className="text-fg">{theme.title}</span>
                  <span className="text-fg-muted flex-1 truncate">{theme.summary}</span>
                  {theme.monthly_impact > 0 && (
                    <span className="text-warn font-mono shrink-0">-${theme.monthly_impact.toLocaleString()}/mo</span>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Token usage */}
          <p className="text-[10px] text-fg-ghost text-right font-mono">
            {brief.usage.prompt_tokens.toLocaleString()}+{brief.usage.completion_tokens.toLocaleString()} tokens &middot; {brief.snapshot_hash}
          </p>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Note card (in timeline)                                             */
/* ------------------------------------------------------------------ */

function NoteCard({
  note,
  onDelete,
}: {
  note: EntityNoteResponse;
  onDelete: (id: string) => void;
}) {
  const [confirming, setConfirming] = useState(false);

  return (
    <div className="rounded-xl border border-border-subtle bg-surface px-4 py-3 group">
      <div className="flex items-start gap-2">
        <div className="w-6 h-6 rounded-lg bg-surface-sunken border border-border-subtle flex items-center justify-center shrink-0 mt-0.5">
          <svg className="w-3.5 h-3.5 text-fg-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931z" />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-fg-secondary whitespace-pre-line">{note.content}</p>
          {note.created_by && (
            <span className="text-[10px] text-fg-ghost mt-1 inline-block">by {note.created_by}</span>
          )}
        </div>
        {confirming ? (
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={() => { onDelete(note.id); setConfirming(false); }}
              className="text-[10px] text-error hover:text-error/80 font-medium px-1.5 py-0.5 rounded border border-error/20 hover:bg-error-soft transition-all"
            >
              Delete
            </button>
            <button
              onClick={() => setConfirming(false)}
              className="text-[10px] text-fg-muted hover:text-fg px-1.5 py-0.5"
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            onClick={() => setConfirming(true)}
            className="shrink-0 opacity-0 group-hover:opacity-100 text-fg-ghost hover:text-fg-muted transition-all p-0.5"
            title="Delete note"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Add note input                                                      */
/* ------------------------------------------------------------------ */

function AddNote({
  managerId,
  onCreated,
}: {
  managerId: string;
  onCreated: () => void;
}) {
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const submit = useCallback(async () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    setSaving(true);
    try {
      await api.createEntityNote("PropertyManager", managerId, trimmed);
      setValue("");
      onCreated();
    } catch {
      // silent — the note will just stay in the input
    } finally {
      setSaving(false);
    }
  }, [managerId, value, onCreated]);

  return (
    <div className="rounded-xl border border-border bg-surface p-3">
      <textarea
        ref={inputRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Add a note about this manager..."
        rows={2}
        className="w-full bg-transparent text-sm text-fg placeholder:text-fg-ghost focus:outline-none resize-none"
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
        }}
      />
      <div className="flex items-center justify-between mt-1.5">
        <span className="text-[10px] text-fg-ghost">
          {navigator.platform?.includes("Mac") ? "⌘" : "Ctrl"}+Enter to save
        </span>
        <button
          onClick={submit}
          disabled={saving || !value.trim()}
          className="px-3 py-1 rounded-lg bg-surface-sunken border border-border text-xs font-medium text-fg-secondary hover:text-fg hover:border-fg-ghost transition-all disabled:opacity-30"
        >
          {saving ? "Saving..." : "Add Note"}
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Main component                                                      */
/* ------------------------------------------------------------------ */

export function ReviewPrepTab({ managerId }: { managerId: string }) {
  const [briefList, setBriefList] = useState<MeetingBriefListResponse | null>(null);
  const [notes, setNotes] = useState<EntityNoteResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [focus, setFocus] = useState("");

  const loadData = useCallback(async () => {
    try {
      const [bl, noteRes] = await Promise.all([
        api.listMeetingBriefs(managerId),
        api.listEntityNotes("PropertyManager", managerId),
      ]);
      setBriefList(bl);
      setNotes(noteRes.notes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [managerId]);

  useEffect(() => { loadData(); }, [loadData]);

  const generate = useCallback(async () => {
    setGenerating(true);
    setError(null);
    try {
      await api.generateMeetingBrief(managerId, focus || undefined);
      setFocus("");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate meeting brief");
    } finally {
      setGenerating(false);
    }
  }, [managerId, focus, loadData]);

  const handleDeleteNote = useCallback(async (noteId: string) => {
    try {
      await api.deleteEntityNote(noteId);
      setNotes((prev) => prev.filter((n) => n.id !== noteId));
    } catch {
      // optimistic removal failed — reload
      loadData();
    }
  }, [loadData]);

  const currentHash = briefList?.current_snapshot_hash ?? null;
  const briefs = briefList?.briefs ?? [];
  const timeline = buildTimeline(briefs, notes);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <span className="text-sm text-fg-faint animate-pulse">Loading...</span>
      </div>
    );
  }

  return (
    <div className="space-y-4 max-w-3xl">
      {/* Generate brief */}
      <div className="rounded-xl border border-border bg-surface p-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center shrink-0">
            <svg className="w-4 h-4 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-fg">Generate Meeting Brief</h3>
            <p className="text-[11px] text-fg-muted">AI-powered portfolio analysis with talking points and action items.</p>
          </div>
        </div>
        <div className="flex items-center gap-2 mt-2.5">
          <input
            type="text"
            value={focus}
            onChange={(e) => setFocus(e.target.value)}
            placeholder="Optional focus (e.g. delinquency, vacancies)"
            className="flex-1 bg-surface-sunken border border-border rounded-lg px-3 py-1.5 text-sm text-fg placeholder:text-fg-ghost focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent transition-all"
            onKeyDown={(e) => e.key === "Enter" && generate()}
          />
          <button
            onClick={generate}
            disabled={generating}
            className="shrink-0 px-3.5 py-1.5 rounded-lg bg-accent text-accent-fg text-sm font-medium hover:bg-accent-hover transition-colors disabled:opacity-40"
          >
            {generating ? "Generating..." : "Generate"}
          </button>
        </div>
        {error && <p className="text-xs text-error mt-2">{error}</p>}
        {generating && (
          <div className="flex items-center gap-2.5 mt-2.5">
            <div className="relative w-4 h-4">
              <div className="absolute inset-0 rounded-full border-2 border-accent/20" />
              <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-accent animate-spin" />
            </div>
            <span className="text-[11px] text-fg-muted">Analyzing portfolio... 15–30 seconds</span>
          </div>
        )}
      </div>

      {/* Add note */}
      <AddNote managerId={managerId} onCreated={loadData} />

      {/* Timeline */}
      {timeline.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-[10px] font-semibold text-fg-muted uppercase tracking-wide">
            Timeline
            <span className="font-normal text-fg-faint ml-1">
              &middot; {briefs.length} brief{briefs.length !== 1 ? "s" : ""}, {notes.length} note{notes.length !== 1 ? "s" : ""}
            </span>
          </h3>

          {timeline.map((entry) => {
            const dateLabel = entry.ts ? fmtDateShort(entry.ts) : "";
            const timeLabel = entry.ts ? fmtTimestamp(entry.ts) : "";

            return (
              <div key={entry.kind === "brief" ? entry.data.id : entry.data.id}>
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-[10px] text-fg-faint font-mono">{dateLabel}</span>
                  <span className="text-[10px] text-fg-ghost">{timeLabel}</span>
                </div>
                {entry.kind === "brief" ? (
                  <BriefCard brief={entry.data} currentHash={currentHash} />
                ) : (
                  <NoteCard note={entry.data} onDelete={handleDeleteNote} />
                )}
              </div>
            );
          })}
        </div>
      )}

      {timeline.length === 0 && (
        <p className="text-sm text-fg-faint text-center py-8">
          No briefs or notes yet. Generate a meeting brief or add a note to get started.
        </p>
      )}
    </div>
  );
}
