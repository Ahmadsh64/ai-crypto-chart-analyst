/** Display helpers for Analysis History (Phase 6.0.3.1). */

import type { AnalysisHistoryDetail, FinalDecision } from "@/types/api";

export const HISTORY_DECISION_OPTIONS: Array<FinalDecision | ""> = [
  "",
  "LONG",
  "SHORT",
  "WAIT",
  "NO TRADE",
];

export const HISTORY_PAGE_SIZE = 20;

export function formatHistoryTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function consistencyTone(status: string | null | undefined): string {
  switch ((status ?? "").toUpperCase()) {
    case "ALIGNED":
      return "border-terminal-long/50 bg-terminal-long/10 text-terminal-long";
    case "DUAL_FETCH_DIVERGED":
      return "border-terminal-short/50 bg-terminal-short/10 text-terminal-short";
    case "DECISION_ONLY":
    case "PLAN_ONLY":
      return "border-amber-400/50 bg-amber-400/5 text-amber-200";
    case "INSUFFICIENT_PROVENANCE":
      return "border-terminal-border bg-terminal-surface text-terminal-muted";
    default:
      return "border-terminal-border text-terminal-muted";
  }
}

export function consistencyLabel(status: string | null | undefined): string {
  const s = (status ?? "").toUpperCase();
  if (!s) return "—";
  if (s === "DUAL_FETCH_DIVERGED") return "Diverged";
  if (s === "DECISION_ONLY") return "Decision only";
  if (s === "PLAN_ONLY") return "Plan only";
  if (s === "INSUFFICIENT_PROVENANCE") return "Incomplete provenance";
  if (s === "ALIGNED") return "Aligned";
  return s;
}

export function isIncompleteConsistency(status: string | null | undefined): boolean {
  const s = (status ?? "").toUpperCase();
  return (
    s === "DUAL_FETCH_DIVERGED" ||
    s === "DECISION_ONLY" ||
    s === "PLAN_ONLY" ||
    s === "INSUFFICIENT_PROVENANCE"
  );
}

/** Planned analytical levels from stored Analyze — never treated as fills. */
export interface PlannedLevelsView {
  entry: string | null;
  entryLow: string | null;
  entryHigh: string | null;
  stopLoss: string | null;
  takeProfits: string[];
  primaryRr: string | null;
  note: string;
}

export function extractPlannedLevels(detail: AnalysisHistoryDetail): PlannedLevelsView {
  const tps = (detail.take_profit_prices ?? []).filter(
    (v): v is string => typeof v === "string" && v.trim().length > 0,
  );
  return {
    entry: detail.entry_reference_price ?? null,
    entryLow: detail.entry_low ?? null,
    entryHigh: detail.entry_high ?? null,
    stopLoss: detail.stop_loss_price ?? null,
    takeProfits: tps,
    primaryRr: detail.primary_rr ?? null,
    note:
      detail.levels_note ||
      "Stored planned Entry/SL/TP are analytical levels from Analyze time — not exchange fills.",
  };
}

export function hasAnyPlannedLevel(levels: PlannedLevelsView): boolean {
  return Boolean(
    levels.entry ||
      levels.entryLow ||
      levels.entryHigh ||
      levels.stopLoss ||
      levels.takeProfits.length > 0,
  );
}

export function historyErrorMessage(err: unknown): string {
  if (err && typeof err === "object" && "message" in err) {
    const msg = (err as { message?: unknown }).message;
    if (typeof msg === "string" && msg.trim()) return msg;
  }
  if (err instanceof Error && err.message) return err.message;
  return "Failed to load analysis history.";
}

export function historyPageCount(total: number, pageSize: number): number {
  if (pageSize <= 0) return 0;
  return Math.max(1, Math.ceil(Math.max(0, total) / pageSize));
}
