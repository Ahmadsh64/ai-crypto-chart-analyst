import type { PlanStatus } from "@/types/api";

export function planStatusLabel(status?: PlanStatus | null): string {
  switch (status) {
    case "eligible":
      return "Eligible";
    case "blocked":
      return "Blocked";
    case "invalid":
      return "Invalid";
    default:
      return "Unavailable";
  }
}

export function planStatusTone(status?: PlanStatus | null): string {
  switch (status) {
    case "eligible":
      return "border-terminal-long/50 text-terminal-long";
    case "invalid":
      return "border-amber-400/50 text-amber-300";
    default:
      return "border-terminal-border text-terminal-muted";
  }
}
