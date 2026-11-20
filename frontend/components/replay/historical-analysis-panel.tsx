"use client";

import { decisionLabel, decisionTone } from "@/lib/decision-display";
import { formatReplayClock, replayQualityTone } from "@/lib/replay-display";
import type { FinalDecision, HistoricalAnalysisSnapshot } from "@/types/api";
import { cn } from "@/utils/cn";

interface HistoricalAnalysisPanelProps {
  analysis: HistoricalAnalysisSnapshot | null;
  enabled: boolean;
  busy?: boolean;
}

export function HistoricalAnalysisPanel({
  analysis,
  enabled,
  busy = false,
}: HistoricalAnalysisPanelProps) {
  if (!enabled) {
    return (
      <div className="rounded-lg border border-terminal-border bg-terminal-panel p-4 text-sm text-terminal-muted">
        Historical analysis is off. Enable it after loading data to reconstruct decisions at each
        replay timestamp.
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="rounded-lg border border-terminal-border bg-terminal-panel p-4 text-sm text-terminal-muted">
        {busy ? "Running historical analysis…" : "No analysis snapshot yet for this timestamp."}
      </div>
    );
  }

  const decision = analysis.decision as FinalDecision;
  const entry = analysis.entry_zone;

  return (
    <div className="space-y-3 rounded-lg border border-terminal-border bg-terminal-panel p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-sm font-semibold text-terminal-text">
            Historical Analysis
          </h2>
          <p className="mt-0.5 text-[11px] text-terminal-muted">
            What the system would have known at {formatReplayClock(analysis.replay_timestamp)}
          </p>
        </div>
        <span
          className={cn(
            "rounded border px-2 py-1 text-xs font-semibold uppercase tracking-wide",
            decisionTone(decision),
          )}
        >
          {decisionLabel(decision)}
        </span>
      </div>

      <p className="text-xs text-terminal-text/90">{analysis.decision_reason}</p>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <Stat label="Bullish" value={analysis.bullish_score.toFixed(1)} />
        <Stat label="Bearish" value={analysis.bearish_score.toFixed(1)} />
        <Stat label="Strength" value={analysis.confluence_strength ?? "—"} />
        <Stat label="Lifecycle" value={analysis.lifecycle_status} />
        <Stat
          label="Quality"
          value={
            <span className={cn(replayQualityTone(analysis.data_quality))}>
              {analysis.data_quality}
            </span>
          }
        />
        <Stat label="Ready" value={analysis.data_ready ? "yes" : "no"} />
      </div>

      {entry ? (
        <div className="rounded border border-terminal-border/70 bg-terminal-surface/60 p-3 text-xs">
          <p className="mb-1 text-[11px] uppercase tracking-[0.12em] text-terminal-muted">
            Hypothetical plan
          </p>
          <p className="text-terminal-text">
            Entry{" "}
            {typeof entry.entry_low === "number" && typeof entry.entry_high === "number"
              ? `${entry.entry_low} – ${entry.entry_high}`
              : "—"}
          </p>
          <p className="text-terminal-text">SL {analysis.stop_loss ?? "—"}</p>
          <p className="text-terminal-text">
            TP {analysis.take_profit_levels.length ? analysis.take_profit_levels.join(", ") : "—"}
          </p>
          <p className="text-terminal-text">
            R:R {analysis.risk_reward != null ? analysis.risk_reward.toFixed(2) : "—"}
          </p>
          <p className="mt-2 text-[11px] text-amber-300/90">
            {analysis.hypothetical_plan_disclaimer}
          </p>
        </div>
      ) : (
        <p className="text-[11px] text-terminal-muted">
          No eligible hypothetical plan at this timestamp ({analysis.trade_plan_status ?? "n/a"}).
        </p>
      )}

      {analysis.evidence_summary.length ? (
        <div>
          <p className="mb-1 text-[11px] uppercase tracking-[0.12em] text-terminal-muted">
            Evidence
          </p>
          <ul className="space-y-1 text-[11px] text-terminal-text/85">
            {analysis.evidence_summary.slice(0, 6).map((e) => (
              <li key={e} className="truncate">
                • {e}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {analysis.conflicts.length ? (
        <div>
          <p className="mb-1 text-[11px] uppercase tracking-[0.12em] text-amber-400">Conflicts</p>
          <ul className="space-y-1 text-[11px] text-amber-200/90">
            {analysis.conflicts.slice(0, 4).map((c) => (
              <li key={c}>• {c}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {analysis.analysis_error ? (
        <p className="text-xs text-terminal-short">{analysis.analysis_error}</p>
      ) : null}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded border border-terminal-border/50 bg-terminal-surface/40 px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-[0.12em] text-terminal-muted">{label}</div>
      <div className="mt-0.5 text-terminal-text">{value}</div>
    </div>
  );
}
