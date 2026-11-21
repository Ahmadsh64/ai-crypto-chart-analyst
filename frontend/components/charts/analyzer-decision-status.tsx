"use client";

import { decisionLabel, decisionTone } from "@/lib/decision-display";
import { decisionAllowsTradeLevels } from "@/lib/analyzer-dashboard-display";
import { cn } from "@/utils/cn";
import type { FinalDecision } from "@/types/api";

interface AnalyzerDecisionStatusProps {
  decision?: FinalDecision | null;
  reason?: string | null;
  loading?: boolean;
  emptyHint?: string;
}

export function AnalyzerDecisionStatus({
  decision,
  reason,
  loading,
  emptyHint = "Run Analyze or wait for the live decision engine.",
}: AnalyzerDecisionStatusProps) {
  const d = decision ?? null;
  const actionable = decisionAllowsTradeLevels(d);

  return (
    <section
      className="rounded-lg border border-terminal-border bg-terminal-panel p-4"
      data-testid="decision-status"
      aria-label="Decision status"
    >
      <p className="text-[11px] uppercase tracking-[0.16em] text-terminal-muted">
        Decision
      </p>
      {loading && !d ? (
        <p className="mt-3 text-sm text-terminal-muted">Loading decision…</p>
      ) : d ? (
        <>
          <div
            className={cn(
              "mt-3 inline-flex min-w-[7rem] items-center justify-center rounded-md border px-4 py-2 text-xl font-semibold tracking-wide",
              decisionTone(d),
            )}
            data-testid="decision-badge"
          >
            {decisionLabel(d)}
          </div>
          <p className="mt-3 text-sm text-terminal-text">
            {reason?.trim() || "No reason provided by the engine."}
          </p>
          {!actionable ? (
            <p className="mt-2 text-xs text-terminal-muted">
              No LONG/SHORT recommendation — entry and targets are not displayed.
            </p>
          ) : null}
          <p className="mt-2 text-[10px] text-terminal-muted">
            Deterministic Decision Engine only — Vision never overrides this output.
          </p>
        </>
      ) : (
        <p className="mt-3 text-sm text-terminal-muted">{emptyHint}</p>
      )}
    </section>
  );
}
