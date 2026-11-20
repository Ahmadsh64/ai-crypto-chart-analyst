"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Hexagon } from "lucide-react";
import { NAV_ITEMS } from "@/lib/navigation";
import { cn } from "@/utils/cn";

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r border-terminal-border bg-terminal-panel">
      <div className="flex items-center gap-3 border-b border-terminal-border px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-md bg-terminal-accent/15 text-terminal-accent">
          <Hexagon className="h-5 w-5" strokeWidth={1.75} />
        </div>
        <div className="min-w-0">
          <p className="truncate font-display text-sm font-semibold tracking-wide text-terminal-text">
            AI CRYPTO
          </p>
          <p className="truncate text-[11px] uppercase tracking-[0.18em] text-terminal-muted">
            Chart Analyst
          </p>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
        {NAV_ITEMS.map((item) => {
          const active =
            pathname === item.href ||
            (item.href !== "/dashboard" && pathname.startsWith(item.href));
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group flex items-center gap-3 rounded-md px-3 py-2.5 text-sm transition-colors",
                active
                  ? "bg-terminal-surface text-terminal-text"
                  : "text-terminal-muted hover:bg-terminal-surface/60 hover:text-terminal-text",
              )}
            >
              <Icon
                className={cn(
                  "h-4 w-4 shrink-0",
                  active ? "text-terminal-accent" : "text-terminal-muted group-hover:text-terminal-text",
                )}
                strokeWidth={1.75}
              />
              <span className="truncate">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-terminal-border px-4 py-4">
        <p className="text-[11px] leading-relaxed text-terminal-muted">
          Analysis only. No live order execution.
        </p>
      </div>
    </aside>
  );
}
