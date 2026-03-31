"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { Badge } from "@/components/ui/Badge";
import type { ActionItemResponse, ManagerNoteResponse } from "@/lib/types";

const PRIORITY_VARIANT: Record<string, "red" | "amber" | "blue" | "cyan"> = {
  urgent: "red",
  high: "red",
  medium: "amber",
  low: "blue",
};

const STATUS_VARIANT: Record<string, "cyan" | "amber" | "emerald"> = {
  open: "cyan",
  in_progress: "amber",
  done: "emerald",
};

const NEXT_STATUS: Record<string, "open" | "in_progress" | "done"> = {
  open: "in_progress",
  in_progress: "done",
  done: "open",
};

function fmtTimestamp(s: string) {
  return new Date(s).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/* ------------------------------------------------------------------ */
/* Action Items                                                        */
/* ------------------------------------------------------------------ */

function ActionItemRow({
  item,
  onToggle,
  onDelete,
}: {
  item: ActionItemResponse;
  onToggle: (item: ActionItemResponse) => void;
  onDelete: (id: string) => void;
}) {
  const isOverdue =
    item.due_date &&
    item.status !== "done" &&
    new Date(item.due_date) < new Date();

  return (
    <div className="group flex items-center gap-3 px-4 py-2.5 border-b border-border-subtle hover:bg-surface-raised transition-colors">
      <button
        onClick={() => onToggle(item)}
        className="shrink-0 flex items-center justify-center w-5 h-5 rounded border border-border-subtle hover:border-accent transition-colors"
        title={`Click to mark ${NEXT_STATUS[item.status]}`}
      >
        {item.status === "done" && (
          <svg
            className="w-3 h-3 text-ok"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={3}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M5 13l4 4L19 7"
            />
          </svg>
        )}
        {item.status === "in_progress" && (
          <span className="block w-2 h-2 rounded-full bg-amber-400" />
        )}
      </button>

      <div className="flex-1 min-w-0">
        <span
          className={`text-sm ${
            item.status === "done"
              ? "text-fg-faint line-through"
              : "text-fg"
          }`}
        >
          {item.title}
        </span>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <Badge variant={PRIORITY_VARIANT[item.priority] ?? "blue"}>
          {item.priority}
        </Badge>
        <Badge variant={STATUS_VARIANT[item.status] ?? "cyan"}>
          {item.status.replace("_", " ")}
        </Badge>
        {item.due_date && (
          <span
            className={`text-[10px] font-mono ${
              isOverdue ? "text-error font-bold" : "text-fg-muted"
            }`}
          >
            {fmtDate(item.due_date)}
          </span>
        )}
      </div>

      <button
        onClick={() => onDelete(item.id)}
        className="shrink-0 opacity-0 group-hover:opacity-100 w-5 h-5 flex items-center justify-center rounded text-fg-faint hover:text-error hover:bg-error-soft transition-all"
        title="Delete"
      >
        <svg
          className="w-3 h-3"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M6 18L18 6M6 6l12 12"
          />
        </svg>
      </button>
    </div>
  );
}

function AddItemForm({
  onAdd,
}: {
  onAdd: (title: string, priority: string, dueDate: string) => void;
}) {
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState("medium");
  const [dueDate, setDueDate] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || submitting) return;
    setSubmitting(true);
    try {
      await onAdd(title.trim(), priority, dueDate || "");
      setTitle("");
      setPriority("medium");
      setDueDate("");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2 px-4 py-3">
      <input
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="New action item..."
        className="flex-1 min-w-0 bg-surface-sunken border border-border-subtle rounded-lg px-3 py-1.5 text-sm text-fg placeholder:text-fg-faint focus:outline-none focus:border-accent transition-colors"
      />
      <select
        value={priority}
        onChange={(e) => setPriority(e.target.value)}
        className="bg-surface-sunken border border-border-subtle rounded-lg px-2 py-1.5 text-xs text-fg-secondary focus:outline-none focus:border-accent transition-colors"
      >
        <option value="low">Low</option>
        <option value="medium">Medium</option>
        <option value="high">High</option>
        <option value="urgent">Urgent</option>
      </select>
      <input
        type="date"
        value={dueDate}
        onChange={(e) => setDueDate(e.target.value)}
        className="bg-surface-sunken border border-border-subtle rounded-lg px-2 py-1.5 text-xs text-fg-secondary focus:outline-none focus:border-accent transition-colors [color-scheme:dark]"
      />
      <button
        type="submit"
        disabled={!title.trim() || submitting}
        className="shrink-0 px-3 py-1.5 rounded-lg bg-accent text-white text-xs font-medium hover:bg-accent/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        Add
      </button>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/* Notes                                                               */
/* ------------------------------------------------------------------ */

function NoteRow({
  note,
  onUpdate,
  onDelete,
}: {
  note: ManagerNoteResponse;
  onUpdate: (id: string, content: string) => void;
  onDelete: (id: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(note.content);

  const save = () => {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== note.content) {
      onUpdate(note.id, trimmed);
    }
    setEditing(false);
  };

  const cancel = () => {
    setDraft(note.content);
    setEditing(false);
  };

  return (
    <div className="group px-4 py-3 border-b border-border-subtle hover:bg-surface-raised transition-colors">
      {editing ? (
        <div className="space-y-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="w-full bg-surface-sunken border border-border-subtle rounded-lg px-3 py-2 text-sm text-fg placeholder:text-fg-faint focus:outline-none focus:border-accent transition-colors resize-y min-h-[60px]"
            rows={3}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) save();
              if (e.key === "Escape") cancel();
            }}
          />
          <div className="flex items-center gap-2">
            <button
              onClick={save}
              className="px-2.5 py-1 rounded-md bg-accent text-white text-[10px] font-medium hover:bg-accent/90 transition-colors"
            >
              Save
            </button>
            <button
              onClick={cancel}
              className="px-2.5 py-1 rounded-md text-[10px] font-medium text-fg-muted hover:text-fg-secondary transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-sm text-fg whitespace-pre-wrap break-words">
              {note.content}
            </p>
            <p className="text-[10px] text-fg-faint mt-1">
              {fmtTimestamp(note.created_at)}
              {note.updated_at !== note.created_at && (
                <span className="ml-1">(edited)</span>
              )}
            </p>
          </div>
          <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={() => setEditing(true)}
              className="w-6 h-6 flex items-center justify-center rounded text-fg-faint hover:text-fg-secondary hover:bg-surface-sunken transition-all"
              title="Edit"
            >
              <svg
                className="w-3 h-3"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                />
              </svg>
            </button>
            <button
              onClick={() => onDelete(note.id)}
              className="w-6 h-6 flex items-center justify-center rounded text-fg-faint hover:text-error hover:bg-error-soft transition-all"
              title="Delete"
            >
              <svg
                className="w-3 h-3"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function AddNoteForm({ onAdd }: { onAdd: (content: string) => void }) {
  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim() || submitting) return;
    setSubmitting(true);
    try {
      await onAdd(content.trim());
      setContent("");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="px-4 py-3 space-y-2">
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="Add a note..."
        className="w-full bg-surface-sunken border border-border-subtle rounded-lg px-3 py-2 text-sm text-fg placeholder:text-fg-faint focus:outline-none focus:border-accent transition-colors resize-y min-h-[48px]"
        rows={2}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            handleSubmit(e);
          }
        }}
      />
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-fg-faint">
          Cmd+Enter to save
        </span>
        <button
          type="submit"
          disabled={!content.trim() || submitting}
          className="px-3 py-1.5 rounded-lg bg-accent text-white text-xs font-medium hover:bg-accent/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          Add Note
        </button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/* Main                                                                */
/* ------------------------------------------------------------------ */

export function ReviewPrepTab({ managerId }: { managerId: string }) {
  const [items, setItems] = useState<ActionItemResponse[]>([]);
  const [notes, setNotes] = useState<ManagerNoteResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [actionRes, noteRes] = await Promise.all([
        api.listActionItems({ manager_id: managerId }),
        api.listManagerNotes(managerId),
      ]);
      setItems(actionRes.items);
      setNotes(noteRes.notes);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [managerId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  /* --- Action item handlers --- */

  const handleAddItem = useCallback(
    async (title: string, priority: string, dueDate: string) => {
      const created = await api.createActionItem({
        title,
        priority,
        manager_id: managerId,
        due_date: dueDate || undefined,
      });
      setItems((prev) => [created, ...prev]);
    },
    [managerId],
  );

  const handleToggleStatus = useCallback(async (item: ActionItemResponse) => {
    const next = NEXT_STATUS[item.status] ?? "open";
    const updated = await api.updateActionItem(item.id, { status: next });
    setItems((prev) => prev.map((i) => (i.id === updated.id ? updated : i)));
  }, []);

  const handleDeleteItem = useCallback(async (id: string) => {
    await api.deleteActionItem(id);
    setItems((prev) => prev.filter((i) => i.id !== id));
  }, []);

  /* --- Note handlers --- */

  const handleAddNote = useCallback(
    async (content: string) => {
      const created = await api.createManagerNote(managerId, content);
      setNotes((prev) => [created, ...prev]);
    },
    [managerId],
  );

  const handleUpdateNote = useCallback(async (id: string, content: string) => {
    const updated = await api.updateManagerNote(id, content);
    setNotes((prev) => prev.map((n) => (n.id === updated.id ? updated : n)));
  }, []);

  const handleDeleteNote = useCallback(async (id: string) => {
    await api.deleteManagerNote(id);
    setNotes((prev) => prev.filter((n) => n.id !== id));
  }, []);

  /* --- Render --- */

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <span className="text-sm text-fg-faint animate-pulse">Loading...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-16">
        <span className="text-sm text-error">{error}</span>
      </div>
    );
  }

  const openCount = items.filter((i) => i.status === "open").length;
  const inProgressCount = items.filter((i) => i.status === "in_progress").length;
  const doneCount = items.filter((i) => i.status === "done").length;

  return (
    <div className="space-y-6">
      {/* Action Items */}
      <section className="rounded-xl border border-border bg-surface overflow-hidden">
        <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between">
          <h2 className="text-xs font-semibold text-fg-secondary uppercase tracking-wide">
            Action Items
          </h2>
          <div className="flex items-center gap-2">
            {openCount > 0 && <Badge variant="cyan">{openCount} open</Badge>}
            {inProgressCount > 0 && (
              <Badge variant="amber">{inProgressCount} in progress</Badge>
            )}
            {doneCount > 0 && (
              <Badge variant="emerald">{doneCount} done</Badge>
            )}
          </div>
        </div>

        <AddItemForm onAdd={handleAddItem} />

        <div className="max-h-[400px] overflow-y-auto">
          {items.length === 0 ? (
            <p className="text-sm text-fg-faint text-center py-8">
              No action items yet
            </p>
          ) : (
            items.map((item) => (
              <ActionItemRow
                key={item.id}
                item={item}
                onToggle={handleToggleStatus}
                onDelete={handleDeleteItem}
              />
            ))
          )}
        </div>
      </section>

      {/* Notes */}
      <section className="rounded-xl border border-border bg-surface overflow-hidden">
        <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between">
          <h2 className="text-xs font-semibold text-fg-secondary uppercase tracking-wide">
            Notes
          </h2>
          {notes.length > 0 && (
            <span className="text-[10px] text-fg-faint">
              {notes.length} {notes.length === 1 ? "note" : "notes"}
            </span>
          )}
        </div>

        <AddNoteForm onAdd={handleAddNote} />

        <div className="max-h-[400px] overflow-y-auto">
          {notes.length === 0 ? (
            <p className="text-sm text-fg-faint text-center py-8">
              No notes yet
            </p>
          ) : (
            notes.map((note) => (
              <NoteRow
                key={note.id}
                note={note}
                onUpdate={handleUpdateNote}
                onDelete={handleDeleteNote}
              />
            ))
          )}
        </div>
      </section>
    </div>
  );
}
