import type { ReactNode } from "react";
import { cn } from "@/utils/cn";

interface StatTileProps {
  label: string;
  value: string;
  hint?: string;
  tone?: "neutral" | "long" | "short" | "accent";
  icon?: ReactNode;
}

export function StatTile({ label, value, hint, tone = "neutral", icon }: StatTileProps) {
  return (
    <div className="rounded-lg border border-terminal-border bg-terminal-panel p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs uppercase tracking-[0.14em] text-terminal-muted">{label}</p>
        {icon}
      </div>
      <p
        className={cn(
          "mt-2 font-display text-2xl font-semibold tracking-tight",
          tone === "long" && "text-terminal-long",
          tone === "short" && "text-terminal-short",
          tone === "accent" && "text-terminal-accent",
          tone === "neutral" && "text-terminal-text",
        )}
      >
        {value}
      </p>
      {hint ? <p className="mt-1 text-xs text-terminal-muted">{hint}</p> : null}
    </div>
  );
}
