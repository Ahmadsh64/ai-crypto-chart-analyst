import type { FinalDecision } from "@/types/api";

export function decisionLabel(decision?: FinalDecision | null): string {
  return decision ?? "—";
}

export function decisionTone(decision?: FinalDecision | null): string {
  switch (decision) {
    case "LONG":
      return "border-terminal-long/60 bg-terminal-long/10 text-terminal-long";
    case "SHORT":
      return "border-terminal-short/60 bg-terminal-short/10 text-terminal-short";
    case "WAIT":
      return "border-amber-400/50 bg-amber-400/5 text-amber-200";
    case "NO TRADE":
      return "border-terminal-border bg-terminal-surface text-terminal-muted";
    default:
      return "border-terminal-border text-terminal-muted";
  }
}
