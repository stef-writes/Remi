"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode } from "react";
import { StatusDot } from "@/components/ui/StatusDot";
import { useAppOSEvents } from "@/hooks/useAppOSEvents";

const NAV_PRIMARY = [
  {
    href: "/",
    label: "Managers",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
      </svg>
    ),
  },
  {
    href: "/documents",
    label: "Upload",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
      </svg>
    ),
  },
];

const NAV_SECONDARY = [
  {
    href: "/ask",
    label: "Ask REMI",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
      </svg>
    ),
  },
];

function NavLink({ href, label, icon, active }: { href: string; label: string; icon: ReactNode; active: boolean }) {
  return (
    <Link
      href={href}
      className={`
        flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all
        ${active ? "bg-zinc-800/70 text-zinc-100" : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/30"}
      `}
    >
      {icon}
      <span className="font-medium">{label}</span>
    </Link>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { connected } = useAppOSEvents();

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" || pathname.startsWith("/managers") : pathname.startsWith(href);

  return (
    <div className="h-screen flex">
      <nav className="w-56 shrink-0 border-r border-zinc-800/60 bg-zinc-950 flex flex-col">
        <div className="px-5 py-5 border-b border-zinc-800/40">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center">
              <span className="text-white text-xs font-black">R</span>
            </div>
            <div>
              <h1 className="text-sm font-bold text-zinc-100 tracking-tight">REMI</h1>
              <p className="text-[9px] text-zinc-600 -mt-0.5">Property Intelligence</p>
            </div>
          </div>
        </div>

        <div className="flex-1 py-3 px-3 space-y-0.5">
          {NAV_PRIMARY.map((item) => (
            <NavLink key={item.href} {...item} active={isActive(item.href)} />
          ))}
        </div>

        <div className="px-3 pb-3 space-y-0.5 border-t border-zinc-800/40 pt-3">
          {NAV_SECONDARY.map((item) => (
            <NavLink key={item.href} {...item} active={isActive(item.href)} />
          ))}
        </div>

        <div className="px-5 py-3 border-t border-zinc-800/40 flex items-center gap-2">
          <StatusDot status={connected ? "connected" : "disconnected"} size={6} />
          <span className="text-[10px] text-zinc-600">
            {connected ? "Connected" : "Offline"}
          </span>
        </div>
      </nav>

      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  );
}
