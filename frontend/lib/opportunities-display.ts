/** Display helpers for Market Opportunities (Phase 5.5 / 5.5.1.1). */

import type { MarketOpportunity, OpportunityStatus } from "@/types/api";

export function opportunityStatusLabel(status: OpportunityStatus): string {
  switch (status) {
    case "READY":
      return "Ready";
    case "APPROACHING_ENTRY":
      return "Approaching entry";
    case "WAITING":
      return "Waiting confirmation";
    case "INVALIDATED":
      return "Invalidated";
    case "EXPIRED":
      return "Expired";
    case "DATA_UNAVAILABLE":
      return "Data unavailable";
    default:
      return status;
  }
}

/** Planned direction for filters/cards — never invents LONG/SHORT from confluence alone. */
export function plannedDirectionLabel(o: Pick<MarketOpportunity, "direction" | "decision">): string | null {
  if (o.direction === "LONG" || o.direction === "SHORT") return o.direction;
  return null;
}

export function isNonExecutableObservation(o: Pick<MarketOpportunity, "market_executable" | "actionable">): boolean {
  return o.market_executable === false;
}

export function opportunityStatusTone(status: OpportunityStatus): string {
  switch (status) {
    case "READY":
      return "border-terminal-long/50 bg-terminal-long/10 text-terminal-long";
    case "APPROACHING_ENTRY":
      return "border-terminal-accent/40 bg-terminal-accent/10 text-terminal-accent";
    case "WAITING":
      return "border-amber-400/40 bg-amber-400/5 text-amber-200";
    case "INVALIDATED":
    case "EXPIRED":
      return "border-terminal-short/40 bg-terminal-short/10 text-terminal-short";
    default:
      return "border-terminal-border text-terminal-muted";
  }
}

export function analyzerHref(args: {
  exchange: string;
  marketType: string;
  symbol: string;
  timeframe: string;
}): string {
  const sp = new URLSearchParams({
    exchange: args.exchange,
    marketType: args.marketType,
    symbol: args.symbol,
    timeframe: args.timeframe,
    from: "opportunities",
  });
  return `/chart-analyzer?${sp.toString()}`;
}
