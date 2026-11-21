/**
 * Pure display helpers for the AI Market Analyzer dashboard.
 * Never invents trade levels — only shapes engine-provided values.
 */

import type {
  DecisionResponse,
  FinalDecision,
  TradePlanResponse,
  TradePlanTarget,
} from "@/types/api";
import type { WsConnectionStatus } from "@/services/market-websocket";

export type LiveConnectionBadge =
  | "live"
  | "rest"
  | "stale"
  | "disconnected"
  | "connecting"
  | "error";

export interface DisplayLevel {
  label: string;
  price: number | null;
  available: boolean;
  detail?: string | null;
}

export interface AnalyzerTradeLevelsModel {
  decision: FinalDecision | null;
  showTradeLevels: boolean;
  livePrice: number | null;
  entry: DisplayLevel;
  entryZone: { low: number | null; high: number | null } | null;
  entryStatus: string | null;
  stopLoss: DisplayLevel;
  invalidation: DisplayLevel;
  takeProfits: [DisplayLevel, DisplayLevel, DisplayLevel];
  primaryRr: number | null;
  plannedNotExecutedNote: string;
}

export function pairBaseName(symbol: string | null | undefined): string {
  if (!symbol) return "—";
  const base = symbol.split("/")[0]?.trim();
  return base || symbol;
}

export function formatPairLabel(symbol: string | null | undefined): string {
  if (!symbol) return "—";
  return symbol.includes("/") ? symbol : symbol;
}

/** Live badge only when stream is connected and data is not stale. */
export function resolveConnectionBadge(
  connectionStatus: WsConnectionStatus | null | undefined,
  hasLiveTicker: boolean,
): LiveConnectionBadge {
  const status = connectionStatus ?? "disconnected";
  if (status === "stale") return "stale";
  if (status === "disconnected") return "disconnected";
  if (status === "connecting" || status === "reconnecting") return "connecting";
  if (status === "connected" && hasLiveTicker) return "live";
  if (status === "connected") return "rest";
  return "disconnected";
}

export function connectionBadgeLabel(badge: LiveConnectionBadge): string {
  switch (badge) {
    case "live":
      return "Live";
    case "rest":
      return "REST seed";
    case "stale":
      return "Stale";
    case "disconnected":
      return "Disconnected";
    case "connecting":
      return "Connecting";
    case "error":
      return "Error";
    default:
      return "Unavailable";
  }
}

/** Normalize API string decisions into FinalDecision without inventing trades. */
export function asFinalDecision(
  value: string | FinalDecision | null | undefined,
): FinalDecision | null {
  if (value === "LONG" || value === "SHORT" || value === "WAIT" || value === "NO TRADE") {
    return value;
  }
  return null;
}

/** True only for actionable directional decisions that may carry entry/SL/TP. */
export function decisionAllowsTradeLevels(decision: FinalDecision | null | undefined): boolean {
  return decision === "LONG" || decision === "SHORT";
}

function unavailable(label: string, detail?: string | null): DisplayLevel {
  return { label, price: null, available: false, detail: detail ?? null };
}

function level(label: string, price: number | null | undefined, detail?: string | null): DisplayLevel {
  if (price == null || !Number.isFinite(price)) {
    return unavailable(label, detail ?? "Unavailable");
  }
  return { label, price, available: true, detail: detail ?? null };
}

function tpSlots(targets: TradePlanTarget[], fallbackPrices: number[]): [DisplayLevel, DisplayLevel, DisplayLevel] {
  const byIndex = new Map<number, TradePlanTarget>();
  for (const t of targets) {
    if (t.index >= 1 && t.index <= 3) byIndex.set(t.index, t);
  }
  const slots: DisplayLevel[] = [];
  for (let i = 1; i <= 3; i++) {
    const fromPlan = byIndex.get(i);
    if (fromPlan) {
      slots.push(
        level(fromPlan.label || `TP${i}`, fromPlan.price, `R:R ${fromPlan.risk_reward_ratio}`),
      );
      continue;
    }
    const fb = fallbackPrices[i - 1];
    if (fb != null && Number.isFinite(fb)) {
      slots.push(level(`TP${i}`, fb));
    } else {
      slots.push(unavailable(`TP${i}`, "Not provided by engine"));
    }
  }
  return slots as [DisplayLevel, DisplayLevel, DisplayLevel];
}

/**
 * Build trade-level display model from deterministic engine outputs only.
 * WAIT / NO TRADE → no fabricated entry or targets.
 */
export function buildAnalyzerTradeLevels(args: {
  decision?: DecisionResponse | null;
  tradePlan?: TradePlanResponse | null;
  snapshotDecision?: FinalDecision | null;
  snapshotEntryRef?: number | null;
  snapshotEntryLow?: number | null;
  snapshotEntryHigh?: number | null;
  snapshotStop?: number | null;
  snapshotTps?: number[] | null;
  snapshotPrimaryRr?: number | null;
  livePrice?: number | null;
}): AnalyzerTradeLevelsModel {
  const decision =
    args.decision?.decision ?? args.snapshotDecision ?? null;
  const showTradeLevels = decisionAllowsTradeLevels(decision);

  const entryStatus =
    args.decision?.entry_confirmation?.status ??
    (args.tradePlan?.entry?.price_inside_zone != null
      ? args.tradePlan.entry.price_inside_zone
        ? "inside_zone"
        : "outside_zone"
      : null) ??
    args.tradePlan?.plan_status ??
    null;

  const plannedNote =
    "Planned analytical levels from the deterministic engine — not executed fills.";

  if (!showTradeLevels) {
    const reason =
      decision === "WAIT" || decision === "NO TRADE"
        ? `${decision}: no entry or targets shown`
        : "No actionable decision yet";
    return {
      decision,
      showTradeLevels: false,
      livePrice: args.livePrice ?? args.decision?.data_quality?.current_price ?? null,
      entry: unavailable("Entry", reason),
      entryZone: null,
      entryStatus: entryStatus,
      stopLoss: unavailable("Stop Loss", reason),
      invalidation: unavailable("Exit / Invalidation", reason),
      takeProfits: [
        unavailable("TP1", reason),
        unavailable("TP2", reason),
        unavailable("TP3", reason),
      ],
      primaryRr: null,
      plannedNotExecutedNote: plannedNote,
    };
  }

  const planEntry = args.tradePlan?.entry;
  const entryRef =
    planEntry?.entry_reference_price ??
    args.snapshotEntryRef ??
    (typeof args.decision?.entry_zone_summary?.entry_reference_price === "number"
      ? (args.decision.entry_zone_summary.entry_reference_price as number)
      : null);
  const entryLow =
    planEntry?.entry_low ??
    args.snapshotEntryLow ??
    (typeof args.decision?.entry_zone_summary?.entry_low === "number"
      ? (args.decision.entry_zone_summary.entry_low as number)
      : null);
  const entryHigh =
    planEntry?.entry_high ??
    args.snapshotEntryHigh ??
    (typeof args.decision?.entry_zone_summary?.entry_high === "number"
      ? (args.decision.entry_zone_summary.entry_high as number)
      : null);

  const stop =
    args.tradePlan?.stop_loss?.stop_loss_price ??
    args.snapshotStop ??
    args.decision?.stop_loss_price ??
    null;

  const invalidationPrice = stop;
  const invalidationDetail =
    args.tradePlan?.stop_loss?.invalidation_explanation ??
    (args.tradePlan?.invalidation_conditions?.[0] ?? null);

  const targets = args.tradePlan?.take_profit_targets ?? [];
  const fallbackTps =
    args.snapshotTps?.length
      ? args.snapshotTps
      : args.decision?.take_profit_prices ?? [];

  const hasZone =
    entryLow != null &&
    entryHigh != null &&
    Number.isFinite(entryLow) &&
    Number.isFinite(entryHigh) &&
    entryLow !== entryHigh;

  return {
    decision,
    showTradeLevels: true,
    livePrice:
      args.livePrice ??
      args.tradePlan?.data_quality?.current_price ??
      args.decision?.data_quality?.current_price ??
      null,
    entry: level(
      hasZone ? "Entry zone (ref)" : "Entry price",
      entryRef,
      planEntry?.entry_type ?? null,
    ),
    entryZone: hasZone ? { low: entryLow, high: entryHigh } : null,
    entryStatus,
    stopLoss: level(
      "Stop Loss",
      stop,
      args.tradePlan?.stop_loss?.stop_loss_source ?? null,
    ),
    invalidation: level("Exit / Invalidation", invalidationPrice, invalidationDetail),
    takeProfits: tpSlots(targets, fallbackTps),
    primaryRr:
      args.tradePlan?.risk?.primary_rr ??
      args.snapshotPrimaryRr ??
      args.decision?.primary_rr ??
      null,
    plannedNotExecutedNote: plannedNote,
  };
}
