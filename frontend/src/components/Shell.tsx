"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { useAppOSEvents } from "@/hooks/useAppOSEvents";
import { CommandMenu, useCommandMenu } from "@/components/ui/CommandMenu";

const NAV_PRIMARY = [
  {
    href: "/",
    label: "Home",
    icon: (
      <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
      </svg>
    ),
  },
  {
    href: "/managers",
    label: "Managers",
    icon: (
      <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z" />
      </svg>
    ),
  },
  {
    href: "/documents",
    label: "Knowledge Base",
    icon: (
      <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
      </svg>
    ),
  },
];

const NAV_SECONDARY = [
  {
    href: "/ask",
    label: "Ask REMI",
    icon: (
      <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
      </svg>
    ),
  },
];

function NavLink({
  href, label, icon, active, onClick,
}: {
  href: string; label: string; icon: ReactNode; active: boolean; onClick?: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onClick}
      className={`
        flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] transition-all
        ${active ? "bg-surface-sunken text-fg font-medium" : "text-fg-muted hover:text-fg-secondary hover:bg-surface-raised"}
      `}
    >
      {icon}
      <span>{label}</span>
    </Link>
  );
}

function HamburgerButton({ open, onClick }: { open: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="md:hidden flex items-center justify-center w-9 h-9 rounded-lg text-fg-muted hover:text-fg hover:bg-surface-raised transition-colors"
      aria-label={open ? "Close menu" : "Open menu"}
    >
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        {open ? (
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        ) : (
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
        )}
      </svg>
    </button>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { connected } = useAppOSEvents();
  const [mobileOpen, setMobileOpen] = useState(false);
  const cmd = useCommandMenu();

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    if (href === "/managers")
      return pathname.startsWith("/managers") || pathname.startsWith("/properties");
    return pathname.startsWith(href);
  };

  const closeMobile = () => setMobileOpen(false);

  const sidebar = (
    <>
      <div className="px-4 py-4 border-b border-border-subtle">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-accent flex items-center justify-center">
            <span className="text-accent-fg text-[11px] font-bold tracking-tight">R</span>
          </div>
          <div className="min-w-0">
            <h1 className="text-sm font-semibold text-fg tracking-tight">REMI</h1>
            <p className="text-[9px] text-fg-faint -mt-0.5 italic truncate">your portfolio, clarified</p>
          </div>
        </div>
      </div>

      {/* Search trigger in sidebar */}
      <div className="px-2 pt-2">
        <button
          onClick={() => { closeMobile(); cmd.setOpen(true); }}
          className="w-full flex items-center gap-2 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-[11px] text-fg-ghost hover:text-fg-muted hover:border-fg-faint transition-all"
        >
          <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
          </svg>
          <span className="flex-1 text-left truncate">Search...</span>
          <kbd className="font-mono text-[9px] opacity-60">⌘K</kbd>
        </button>
      </div>

      <div className="flex-1 py-2 px-2 space-y-0.5 overflow-y-auto">
        {NAV_PRIMARY.map((item) => (
          <NavLink key={item.href} {...item} active={isActive(item.href)} onClick={closeMobile} />
        ))}
      </div>

      <div className="px-2 pb-2 space-y-0.5 border-t border-border-subtle pt-2">
        {NAV_SECONDARY.map((item) => (
          <NavLink key={item.href} {...item} active={isActive(item.href)} onClick={closeMobile} />
        ))}
      </div>

      <div className="px-4 py-3 border-t border-border-subtle flex items-center gap-2">
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${connected ? "bg-ok" : "bg-error"}`} />
        <span className="text-[10px] text-fg-faint">
          {connected ? "Live" : "Offline"}
        </span>
      </div>
    </>
  );

  return (
    <div className="h-screen flex overflow-hidden">
      {/* Desktop sidebar */}
      <nav className="hidden md:flex w-52 shrink-0 border-r border-border bg-surface-raised flex-col">
        {sidebar}
      </nav>

      {/* Mobile overlay + sidebar */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-fg/20 drawer-overlay" onClick={closeMobile} />
          <nav className="absolute left-0 top-0 bottom-0 w-64 bg-surface-raised border-r border-border flex flex-col drawer-panel" style={{ animationName: "drawerSlideLeft" }}>
            {sidebar}
          </nav>
        </div>
      )}

      {/* Main area */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        {/* Mobile top bar */}
        <div className="md:hidden shrink-0 flex items-center gap-2 px-3 py-2 border-b border-border-subtle bg-surface">
          <HamburgerButton open={mobileOpen} onClick={() => setMobileOpen(!mobileOpen)} />
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-6 h-6 rounded-md bg-accent flex items-center justify-center shrink-0">
              <span className="text-accent-fg text-[9px] font-bold">R</span>
            </div>
            <span className="text-sm font-semibold text-fg truncate">REMI</span>
          </div>
          <button
            onClick={() => cmd.setOpen(true)}
            className="ml-auto w-8 h-8 rounded-lg flex items-center justify-center text-fg-muted hover:text-fg hover:bg-surface-raised transition-colors"
            aria-label="Search"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
            </svg>
          </button>
          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${connected ? "bg-ok" : "bg-error"}`} />
        </div>

        <main className="flex-1 overflow-hidden">{children}</main>
      </div>

      <CommandMenu open={cmd.open} onOpenChange={cmd.setOpen} />
    </div>
  );
}
