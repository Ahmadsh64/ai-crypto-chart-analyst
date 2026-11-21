"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Hexagon } from "lucide-react";
import { useAuth } from "@/components/providers/auth-provider";
import { NAV_GROUPS } from "@/lib/navigation";
import { cn } from "@/utils/cn";

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { configured, user, signOut } = useAuth();

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

      <nav className="flex-1 space-y-4 overflow-y-auto px-3 py-4">
        {NAV_GROUPS.map((group) => (
          <div key={group.id}>
            <p className="mb-1 px-3 text-[10px] font-medium uppercase tracking-[0.16em] text-terminal-muted">
              {group.label}
            </p>
            <div className="space-y-0.5">
              {group.items.map((item) => {
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
                      item.later && "opacity-70",
                      active
                        ? "bg-terminal-surface text-terminal-text"
                        : "text-terminal-muted hover:bg-terminal-surface/60 hover:text-terminal-text",
                    )}
                    title={item.description}
                  >
                    <Icon
                      className={cn(
                        "h-4 w-4 shrink-0",
                        active
                          ? "text-terminal-accent"
                          : "text-terminal-muted group-hover:text-terminal-text",
                      )}
                      strokeWidth={1.75}
                    />
                    <span className="min-w-0 flex-1 truncate">{item.label}</span>
                    {item.later ? (
                      <span className="shrink-0 text-[9px] uppercase tracking-wider text-terminal-muted">
                        Soon
                      </span>
                    ) : null}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="border-t border-terminal-border px-4 py-4 space-y-3">
        <p className="text-[11px] leading-relaxed text-terminal-muted">
          Analysis only. No live order execution.
        </p>
        {configured && user ? (
          <div className="space-y-2">
            <p className="truncate text-[11px] text-terminal-muted" title={user.email ?? undefined}>
              {user.email}
            </p>
            <button
              type="button"
              className="text-[11px] uppercase tracking-wider text-terminal-accent hover:underline"
              onClick={async () => {
                await signOut();
                router.replace("/login");
              }}
            >
              Sign out
            </button>
          </div>
        ) : null}
      </div>
    </aside>
  );
}
