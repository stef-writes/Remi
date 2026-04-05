"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import * as Dialog from "@radix-ui/react-dialog";
import * as VisuallyHidden from "@radix-ui/react-visually-hidden";
import { api } from "@/lib/api";
import type { SearchHit } from "@/lib/types";

const QUESTION_PREFIXES = [
  "who", "what", "how", "which", "show", "find", "compare",
  "why", "where", "when", "list", "tell", "give", "are", "is",
];

function looksLikeQuestion(q: string): boolean {
  if (q.includes("?")) return true;
  const first = q.trim().split(/\s/)[0]?.toLowerCase() ?? "";
  return QUESTION_PREFIXES.includes(first);
}

function entityHref(hit: SearchHit): string {
  switch (hit.entity_type) {
    case "PropertyManager":
      return `/managers/${hit.entity_id}`;
    case "Property":
      return `/properties/${hit.entity_id}`;
    case "Unit": {
      const pid = hit.metadata.property_id as string | undefined;
      return pid ? `/properties/${pid}/units/${hit.entity_id}` : "/";
    }
    case "Tenant": {
      const pid = hit.metadata.property_id as string | undefined;
      return pid ? `/properties/${pid}` : "/";
    }
    default:
      return "/";
  }
}

const TYPE_ICONS: Record<string, string> = {
  PropertyManager: "M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z",
  Property: "M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M3 3h12m-.75 4.5H21m-3.75 4.5V21",
  Unit: "M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6z",
  Tenant: "M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z",
};

const TYPE_ORDER: Record<string, number> = {
  PropertyManager: 0,
  Property: 1,
  Tenant: 2,
  Unit: 3,
  MaintenanceRequest: 4,
  DocumentRow: 5,
};

function groupResults(results: SearchHit[]): [string, SearchHit[]][] {
  const groups = new Map<string, SearchHit[]>();
  for (const r of results) {
    const arr = groups.get(r.label) || [];
    arr.push(r);
    groups.set(r.label, arr);
  }
  return [...groups.entries()].sort(
    (a, b) => (TYPE_ORDER[a[1][0]?.entity_type] ?? 99) - (TYPE_ORDER[b[1][0]?.entity_type] ?? 99),
  );
}

const NAV_PAGES = [
  { label: "Home / Dashboard", href: "/", keywords: "home dashboard overview" },
  { label: "Managers", href: "/managers", keywords: "managers property pm" },
  { label: "Knowledge Base", href: "/documents", keywords: "documents upload files knowledge" },
  { label: "Delinquency", href: "/delinquency", keywords: "delinquent tenants collections owed" },
  { label: "Expiring Leases", href: "/leases", keywords: "leases expiring mtm month" },
  { label: "Vacancies", href: "/vacancies", keywords: "vacant units vacancy" },
  { label: "Ask REMI", href: "/ask", keywords: "ask ai chat question" },
];

export function CommandMenu({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchHit[]>([]);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const close = useCallback(() => {
    onOpenChange(false);
    setTimeout(() => { setQuery(""); setResults([]); }, 200);
  }, [onOpenChange]);

  useEffect(() => {
    if (!open) return;
    const q = query.trim();
    if (q.length < 2) {
      setResults([]);
      return;
    }
    setLoading(true);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await api.search(q, 8);
        setResults(res.results);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 200);
    return () => clearTimeout(debounceRef.current);
  }, [query, open]);

  function navigate(href: string) {
    close();
    router.push(href);
  }

  function askRemi() {
    if (!query.trim()) return;
    navigate(`/ask?q=${encodeURIComponent(query.trim())}`);
  }

  const grouped = groupResults(results);
  const hasQuery = query.trim().length >= 2;
  const showAskRemi = query.trim().length > 0;
  const isQuestion = looksLikeQuestion(query);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-fg/20 backdrop-blur-sm cmd-overlay" />
        <Dialog.Content
          className="fixed z-50 top-[min(20vh,120px)] left-1/2 -translate-x-1/2 w-[calc(100%-2rem)] max-w-xl cmd-dialog"
          aria-describedby={undefined}
        >
          <VisuallyHidden.Root>
            <Dialog.Title>Command Menu</Dialog.Title>
          </VisuallyHidden.Root>
          <Command
            label="Command Menu"
            shouldFilter={!hasQuery}
            loop
            className="rounded-2xl border border-border bg-surface shadow-2xl overflow-hidden"
          >
            <div className="flex items-center gap-3 px-4 border-b border-border-subtle">
              <svg className="w-4 h-4 text-fg-faint shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
              </svg>
              <Command.Input
                value={query}
                onValueChange={setQuery}
                placeholder="Search portfolio or ask a question..."
                className="flex-1 py-3.5 text-sm text-fg bg-transparent placeholder:text-fg-ghost outline-none"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && isQuestion && results.length === 0) {
                    e.preventDefault();
                    askRemi();
                  }
                }}
              />
              {loading && (
                <div className="w-4 h-4 border-2 border-fg-ghost border-t-accent rounded-full animate-spin shrink-0" />
              )}
              <kbd className="hidden sm:inline-flex items-center gap-0.5 rounded-md border border-border bg-surface-sunken px-1.5 py-0.5 text-[10px] text-fg-ghost font-mono">
                esc
              </kbd>
            </div>

            <Command.List className="max-h-[min(60vh,400px)] overflow-y-auto p-1.5">
              <Command.Empty className="px-4 py-8 text-center text-xs text-fg-faint">
                {loading ? "Searching..." : "No results found"}
              </Command.Empty>

              {/* Entity search results */}
              {hasQuery && grouped.map(([label, hits]) => (
                <Command.Group key={label} heading={label} className="cmd-group">
                  {hits.map((hit) => (
                    <Command.Item
                      key={hit.entity_id}
                      value={`${hit.title} ${hit.subtitle}`}
                      onSelect={() => navigate(entityHref(hit))}
                      className="cmd-item"
                    >
                      <svg className="w-4 h-4 text-fg-faint shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d={TYPE_ICONS[hit.entity_type] ?? TYPE_ICONS.Property} />
                      </svg>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-fg truncate">{hit.title}</p>
                        {hit.subtitle && (
                          <p className="text-[11px] text-fg-faint truncate">{hit.subtitle}</p>
                        )}
                      </div>
                      <svg className="w-3 h-3 text-fg-ghost shrink-0 opacity-0 group-data-[selected=true]/item:opacity-100" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
                      </svg>
                    </Command.Item>
                  ))}
                </Command.Group>
              ))}

              {/* Ask REMI action */}
              {showAskRemi && (
                <Command.Group heading="AI" className="cmd-group">
                  <Command.Item
                    value={`ask remi ${query}`}
                    onSelect={askRemi}
                    className="cmd-item"
                  >
                    <svg className="w-4 h-4 text-accent shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
                    </svg>
                    <span className="text-sm text-accent">Ask REMI: &ldquo;{query.trim()}&rdquo;</span>
                  </Command.Item>
                </Command.Group>
              )}

              {/* Page navigation (shown when no query) */}
              {!hasQuery && (
                <Command.Group heading="Navigate" className="cmd-group">
                  {NAV_PAGES.map((page) => (
                    <Command.Item
                      key={page.href}
                      value={`${page.label} ${page.keywords}`}
                      onSelect={() => navigate(page.href)}
                      className="cmd-item"
                    >
                      <svg className="w-4 h-4 text-fg-faint shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
                      </svg>
                      <span className="text-sm text-fg">{page.label}</span>
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
            </Command.List>

            {/* Footer */}
            <div className="flex items-center gap-4 px-4 py-2 border-t border-border-subtle text-[10px] text-fg-ghost">
              <span className="flex items-center gap-1">
                <kbd className="font-mono bg-surface-sunken border border-border rounded px-1 py-px">↑↓</kbd>
                navigate
              </span>
              <span className="flex items-center gap-1">
                <kbd className="font-mono bg-surface-sunken border border-border rounded px-1 py-px">⏎</kbd>
                select
              </span>
              <span className="flex items-center gap-1">
                <kbd className="font-mono bg-surface-sunken border border-border rounded px-1 py-px">esc</kbd>
                close
              </span>
            </div>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function useCommandMenu() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  return { open, setOpen };
}

export function CommandTrigger({ onClick, prominent = false }: { onClick: () => void; prominent?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-3 bg-surface border border-border text-fg-ghost transition-all hover:border-fg-faint hover:text-fg-muted ${
        prominent
          ? "rounded-2xl px-5 py-3.5 text-base max-w-2xl mx-auto"
          : "rounded-xl px-3 py-2 text-sm"
      }`}
    >
      <svg className={prominent ? "w-5 h-5" : "w-4 h-4"} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
      </svg>
      <span className="flex-1 text-left truncate">Search portfolio or ask a question...</span>
      <kbd className="hidden sm:inline-flex items-center gap-0.5 rounded-md border border-border bg-surface-sunken px-1.5 py-0.5 text-[10px] text-fg-ghost font-mono shrink-0">
        ⌘K
      </kbd>
    </button>
  );
}
