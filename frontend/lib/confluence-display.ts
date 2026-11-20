import type { PreliminaryAssessment } from "@/types/api";

export function assessmentLabel(a: PreliminaryAssessment | string | undefined): string {
  switch (a) {
    case "bullish_confluence":
      return "Bullish confluence";
    case "bearish_confluence":
      return "Bearish confluence";
    case "mixed":
      return "Mixed";
    case "insufficient_evidence":
      return "Insufficient evidence";
    case "data_unavailable":
      return "Data unavailable";
    default:
      return "—";
  }
}

export function assessmentTone(a: PreliminaryAssessment | string | undefined): string {
  switch (a) {
    case "bullish_confluence":
      return "border-terminal-long/50 text-terminal-long bg-terminal-long/10";
    case "bearish_confluence":
      return "border-terminal-short/50 text-terminal-short bg-terminal-short/10";
    case "mixed":
      return "border-amber-500/40 text-amber-300 bg-amber-500/10";
    case "insufficient_evidence":
    case "data_unavailable":
      return "border-terminal-border text-terminal-muted bg-terminal-surface/50";
    default:
      return "border-terminal-border text-terminal-muted";
  }
}

export function categoryLabel(category: string): string {
  switch (category) {
    case "htf_context":
      return "4H context";
    case "market_structure":
      return "1H structure";
    case "liquidity":
      return "Liquidity";
    case "ob_fvg":
      return "OB / FVG";
    case "ltf_confirmation":
      return "5M confirm";
    default:
      return category;
  }
}
