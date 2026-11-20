/**
 * Phase 5.3 — Pure helpers mapping Decision + Trade Plan backend payloads to
 * planned chart price lines and risk/reward zones.
 *
 * Visualization only. Does not invent trading levels or execution fills.
 * Planned levels must never look like executed historical trade markers.
 */

import type { UTCTimestamp } from "lightweight-charts";
import type { TradeChartPriceLine } from "@/lib/trade-chart-visuals";
import type { ZoneDrawSpec } from "@/lib/zone-primitive";
import type {
  DecisionResponse,
  ExchangeId,
  FinalDecision,
  MarketType,
  PlanDirection,
  PlanStatus,
  TradePlanResponse,
  TradePlanTarget,
} from "@/types/api";
import type { LiveDecision, LiveTradePlan } from "@/stores/live-market-store";

export type PlanChartStatus =
  | "WAITING FOR CONFIRMATION"
  | "LONG SETUP CONFIRMED"
  | "SHORT SETUP CONFIRMED"
  | "NO TRADE"
  | "PLAN UNAVAILABLE";

export interface TradePlanChartToggleState {
  entry: boolean;
  stopLoss: boolean;
  tp1: boolean;
  tp2: boolean;
  tp3: boolean;
  riskRewardZones: boolean;
  /** Master switch — when false, hide every plan level/zone. */
  allLevels: boolean;
}

export const DEFAULT_TRADE_PLAN_CHART_TOGGLES: TradePlanChartToggleState = {
  entry: true,
  stopLoss: true,
  tp1: true,
  tp2: true,
  tp3: true,
  riskRewardZones: true,
  allLevels: true,
};

export interface PlanTakeProfitLevel {
  index: number;
  label: string;
  price: number;
}

/** Normalized levels from Trade Plan / Decision (backend remains source of truth). */
export interface TradePlanVisualSource {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  planId: string | null;
  decisionId: string | null;
  decision: FinalDecision | null;
  direction: PlanDirection | null;
  planStatus: PlanStatus | null;
  validationValid: boolean | null;
  entryPrice: number | null;
  /** Backend entry zone bounds when supplied (Phase 5.3.1 monitor). */
  entryLow: number | null;
  entryHigh: number | null;
  priceInsideZone: boolean | null;
  stopLossPrice: number | null;
  takeProfits: PlanTakeProfitLevel[];
  primaryRr: number | null;
  analysisTimestamp: string | null;
  spotRestriction: string | null;
  marketKey: string;
}

export interface TradePlanLegendModel {
  status: PlanChartStatus;
  decision: FinalDecision | null;
  direction: PlanDirection | null;
  entry: number | null;
  stopLoss: number | null;
  tp1: number | null;
  tp2: number | null;
  tp3: number | null;
  primaryRr: number | null;
  planId: string | null;
  decisionId: string | null;
  plannedOnly: true;
}

export interface BuildTradePlanChartVisualsInput {
  source: TradePlanVisualSource | null;
  toggles?: Partial<TradePlanChartToggleState>;
  /** Candle time range for risk/reward zone X extent (UTC seconds). */
  zoneStart?: UTCTimestamp | null;
  zoneEnd?: UTCTimestamp | null;
  /** Accepted market key — mismatched source clears visuals. */
  expectedMarketKey?: string | null;
  /** Last accepted analysis timestamp — older payloads are ignored. */
  acceptedAnalysisTimestamp?: string | null;
}

export interface TradePlanChartVisuals {
  status: PlanChartStatus;
  legend: TradePlanLegendModel;
  priceLines: TradeChartPriceLine[];
  zones: ZoneDrawSpec[];
  /** True when this source was applied (not stale / cleared). */
  applied: boolean;
  /** Timestamp that should become the new accepted watermark when applied. */
  analysisTimestamp: string | null;
}

const ENTRY_COLOR = "#eab308";
const SL_COLOR = "#ef4444";
const TP_COLORS = ["#22c55e", "#4ade80", "#86efac"] as const;
const RISK_FILL = "rgba(239, 68, 68, 0.14)";
const RISK_STROKE = "rgba(239, 68, 68, 0.55)";
const REWARD_FILL = "rgba(34, 197, 94, 0.12)";
const REWARD_STROKE = "rgba(34, 197, 94, 0.45)";

const LINE_DASHED = 2 as const;

function finitePrice(n: unknown): number | null {
  if (typeof n !== "number" || !Number.isFinite(n)) return null;
  return n;
}

function fmtPrice(n: number): string {
  if (Math.abs(n) >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (Math.abs(n) >= 1) return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
  return n.toLocaleString(undefined, { maximumFractionDigits: 8 });
}

export function marketSelectionKey(
  exchange: ExchangeId,
  marketType: MarketType,
  symbol: string,
): string {
  return `${exchange}:${marketType}:${symbol.toUpperCase()}`;
}

export function analysisTimestampMs(iso: string | null | undefined): number {
  if (!iso) return Number.NEGATIVE_INFINITY;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : Number.NEGATIVE_INFINITY;
}

/**
 * Reject outdated payloads for the same market. Different market keys always accept
 * (caller must clear previous visuals first).
 */
export function shouldAcceptPlanVisualUpdate(
  incoming: { marketKey: string; analysisTimestamp: string | null },
  accepted: { marketKey: string; analysisTimestamp: string | null } | null,
): boolean {
  if (!accepted) return true;
  if (incoming.marketKey !== accepted.marketKey) return true;
  // Missing stamps still apply (toggle refresh / incomplete payloads).
  if (!incoming.analysisTimestamp || !accepted.analysisTimestamp) return true;
  const next = analysisTimestampMs(incoming.analysisTimestamp);
  const prev = analysisTimestampMs(accepted.analysisTimestamp);
  // Equal timestamps allowed (idempotent replace); strictly older rejected.
  return next >= prev;
}

export function setAllTradePlanLevelsVisible(
  visible: boolean,
): TradePlanChartToggleState {
  return {
    entry: visible,
    stopLoss: visible,
    tp1: visible,
    tp2: visible,
    tp3: visible,
    riskRewardZones: visible,
    allLevels: visible,
  };
}

function mapTargets(
  targets: TradePlanTarget[] | undefined | null,
  prices: number[] | undefined | null,
): PlanTakeProfitLevel[] {
  const out: PlanTakeProfitLevel[] = [];
  const seen = new Set<number>();

  if (targets?.length) {
    for (const t of targets) {
      const price = finitePrice(t.price);
      if (price == null) continue;
      const index = Number.isFinite(t.index) ? t.index : out.length + 1;
      if (seen.has(index)) continue;
      seen.add(index);
      out.push({
        index,
        label: t.label?.trim() || `TP${index}`,
        price,
      });
    }
  } else if (prices?.length) {
    prices.forEach((p, i) => {
      const price = finitePrice(p);
      if (price == null) return;
      const index = i + 1;
      out.push({ index, label: `TP${index}`, price });
    });
  }

  out.sort((a, b) => a.index - b.index);
  return out;
}

function entryFromZoneSummary(summary: Record<string, unknown> | null | undefined): number | null {
  if (!summary) return null;
  return finitePrice(summary.entry_reference_price);
}

function preferNewerTimestamp(a: string | null | undefined, b: string | null | undefined): string | null {
  const am = analysisTimestampMs(a);
  const bm = analysisTimestampMs(b);
  if (am === Number.NEGATIVE_INFINITY && bm === Number.NEGATIVE_INFINITY) return null;
  return am >= bm ? (a ?? null) : (b ?? null);
}

/**
 * Merge live + REST Decision / Trade Plan into one visual source.
 * Live wins when present for the same selection.
 */
export function resolveTradePlanVisualSource(args: {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  restPlan?: TradePlanResponse | null;
  livePlan?: LiveTradePlan | null;
  restDecision?: DecisionResponse | null;
  liveDecision?: LiveDecision | null;
}): TradePlanVisualSource {
  const { exchange, marketType, symbol } = args;
  const marketKey = marketSelectionKey(exchange, marketType, symbol);

  const livePlan =
    args.livePlan &&
    args.livePlan.exchange === exchange &&
    args.livePlan.marketType === marketType &&
    args.livePlan.symbol.toUpperCase() === symbol.toUpperCase()
      ? args.livePlan
      : null;
  const liveDecision =
    args.liveDecision &&
    args.liveDecision.exchange === exchange &&
    args.liveDecision.marketType === marketType &&
    args.liveDecision.symbol.toUpperCase() === symbol.toUpperCase()
      ? args.liveDecision
      : null;

  const restPlan =
    args.restPlan &&
    args.restPlan.exchange === exchange &&
    args.restPlan.market_type === marketType &&
    args.restPlan.symbol.toUpperCase() === symbol.toUpperCase()
      ? args.restPlan
      : null;
  const restDecision =
    args.restDecision &&
    args.restDecision.exchange === exchange &&
    args.restDecision.market_type === marketType &&
    args.restDecision.symbol.toUpperCase() === symbol.toUpperCase()
      ? args.restDecision
      : null;

  const decision = liveDecision?.decision ?? restDecision?.decision ?? null;
  const planStatus = livePlan?.planStatus ?? restPlan?.plan_status ?? null;
  const validationValid =
    livePlan?.validation?.is_valid ?? restPlan?.validation?.is_valid ?? null;

  const entryPrice =
    finitePrice(livePlan?.entry?.entry_reference_price) ??
    finitePrice(restPlan?.entry?.entry_reference_price) ??
    entryFromZoneSummary(liveDecision?.entryZoneSummary) ??
    entryFromZoneSummary(restDecision?.entry_zone_summary);

  const entryLow =
    finitePrice(livePlan?.entry?.entry_low) ??
    finitePrice(restPlan?.entry?.entry_low) ??
    finitePrice(liveDecision?.entryZoneSummary?.entry_low) ??
    finitePrice(restDecision?.entry_zone_summary?.entry_low);

  const entryHigh =
    finitePrice(livePlan?.entry?.entry_high) ??
    finitePrice(restPlan?.entry?.entry_high) ??
    finitePrice(liveDecision?.entryZoneSummary?.entry_high) ??
    finitePrice(restDecision?.entry_zone_summary?.entry_high);

  const priceInsideZone =
    livePlan?.entry?.price_inside_zone ??
    restPlan?.entry?.price_inside_zone ??
    (typeof liveDecision?.priceInsideEntryZone === "boolean"
      ? liveDecision.priceInsideEntryZone
      : null) ??
    (typeof restDecision?.price_inside_entry_zone === "boolean"
      ? restDecision.price_inside_entry_zone
      : null);

  const stopLossPrice =
    finitePrice(livePlan?.stopLoss?.stop_loss_price) ??
    finitePrice(restPlan?.stop_loss?.stop_loss_price) ??
    finitePrice(liveDecision?.stopLossPrice) ??
    finitePrice(restDecision?.stop_loss_price);

  const takeProfits = mapTargets(
    livePlan?.takeProfitTargets ?? restPlan?.take_profit_targets,
    liveDecision?.takeProfitPrices ?? restDecision?.take_profit_prices,
  );

  const primaryRr =
    finitePrice(livePlan?.risk?.primary_rr) ??
    finitePrice(restPlan?.risk?.primary_rr) ??
    finitePrice(liveDecision?.primaryRr) ??
    finitePrice(restDecision?.primary_rr);

  const analysisTimestamp = preferNewerTimestamp(
    preferNewerTimestamp(liveDecision?.analysisTimestamp, restDecision?.analysis_timestamp),
    preferNewerTimestamp(livePlan?.analysisTimestamp, restPlan?.analysis_timestamp),
  );

  return {
    exchange,
    marketType,
    symbol,
    planId: livePlan?.planId ?? restPlan?.plan_id ?? null,
    decisionId: liveDecision?.decisionId ?? restDecision?.decision_id ?? null,
    decision,
    direction:
      liveDecision?.direction ??
      restDecision?.direction ??
      livePlan?.direction ??
      restPlan?.direction ??
      null,
    planStatus,
    validationValid,
    entryPrice,
    entryLow,
    entryHigh,
    priceInsideZone,
    stopLossPrice,
    takeProfits,
    primaryRr,
    analysisTimestamp,
    spotRestriction:
      liveDecision?.spotRestriction ??
      restDecision?.spot_restriction ??
      livePlan?.spotShortWarning ??
      restPlan?.spot_short_warning ??
      null,
    marketKey,
  };
}

export function resolvePlanChartStatus(source: TradePlanVisualSource | null): PlanChartStatus {
  if (!source || source.decision == null) return "PLAN UNAVAILABLE";
  if (source.decision === "NO TRADE") return "NO TRADE";

  const hasLevels =
    source.entryPrice != null ||
    source.stopLossPrice != null ||
    source.takeProfits.length > 0;

  if (!hasLevels) return "PLAN UNAVAILABLE";
  if (source.planStatus === "blocked" || source.planStatus === "invalid") {
    return "PLAN UNAVAILABLE";
  }
  if (source.validationValid === false) return "PLAN UNAVAILABLE";

  if (source.decision === "WAIT") return "WAITING FOR CONFIRMATION";
  if (source.decision === "LONG") return "LONG SETUP CONFIRMED";
  if (source.decision === "SHORT") return "SHORT SETUP CONFIRMED";
  return "PLAN UNAVAILABLE";
}

function canShowLevels(source: TradePlanVisualSource, status: PlanChartStatus): boolean {
  if (
    status === "NO TRADE" ||
    status === "PLAN UNAVAILABLE"
  ) {
    return false;
  }
  return (
    source.decision === "WAIT" ||
    source.decision === "LONG" ||
    source.decision === "SHORT"
  );
}

function emptyLegend(status: PlanChartStatus): TradePlanLegendModel {
  return {
    status,
    decision: status === "NO TRADE" ? "NO TRADE" : null,
    direction: null,
    entry: null,
    stopLoss: null,
    tp1: null,
    tp2: null,
    tp3: null,
    primaryRr: null,
    planId: null,
    decisionId: null,
    plannedOnly: true,
  };
}

function dedupePriceLines(lines: TradeChartPriceLine[]): TradeChartPriceLine[] {
  const seen = new Set<string>();
  const out: TradeChartPriceLine[] = [];
  for (const line of lines) {
    if (seen.has(line.id)) continue;
    seen.add(line.id);
    out.push(line);
  }
  return out;
}

/**
 * Convert a valid backend plan into planned price lines + optional RR zones.
 * Never emits execution markers.
 */
export function buildTradePlanChartVisuals(
  input: BuildTradePlanChartVisualsInput,
): TradePlanChartVisuals {
  const toggles: TradePlanChartToggleState = {
    ...DEFAULT_TRADE_PLAN_CHART_TOGGLES,
    ...input.toggles,
  };

  const clear = (status: PlanChartStatus): TradePlanChartVisuals => ({
    status,
    legend: emptyLegend(status),
    priceLines: [],
    zones: [],
    applied: true,
    analysisTimestamp: input.source?.analysisTimestamp ?? null,
  });

  const source = input.source;
  if (!source) return clear("PLAN UNAVAILABLE");

  if (
    input.expectedMarketKey &&
    source.marketKey !== input.expectedMarketKey
  ) {
    return {
      ...clear("PLAN UNAVAILABLE"),
      applied: true,
      analysisTimestamp: null,
    };
  }

  if (
    input.acceptedAnalysisTimestamp != null &&
    !shouldAcceptPlanVisualUpdate(
      { marketKey: source.marketKey, analysisTimestamp: source.analysisTimestamp },
      {
        marketKey: input.expectedMarketKey ?? source.marketKey,
        analysisTimestamp: input.acceptedAnalysisTimestamp,
      },
    )
  ) {
    return {
      status: resolvePlanChartStatus(source),
      legend: emptyLegend("PLAN UNAVAILABLE"),
      priceLines: [],
      zones: [],
      applied: false,
      analysisTimestamp: input.acceptedAnalysisTimestamp,
    };
  }

  const status = resolvePlanChartStatus(source);
  if (!canShowLevels(source, status) || !toggles.allLevels) {
    return {
      status,
      legend: {
        ...emptyLegend(status),
        decision: source.decision,
        direction: source.direction,
        planId: source.planId,
        decisionId: source.decisionId,
        primaryRr: status === "NO TRADE" || status === "PLAN UNAVAILABLE" ? null : source.primaryRr,
        entry: null,
        stopLoss: null,
        tp1: null,
        tp2: null,
        tp3: null,
      },
      priceLines: [],
      zones: [],
      applied: true,
      analysisTimestamp: source.analysisTimestamp,
    };
  }

  const plannedPrefix = status === "WAITING FOR CONFIRMATION";
  const planRef = source.planId ?? source.decisionId ?? "plan";
  const lines: TradeChartPriceLine[] = [];

  if (toggles.entry && source.entryPrice != null) {
    const label = plannedPrefix ? "PLANNED ENTRY" : "ENTRY";
    lines.push({
      id: `plan:${planRef}:entry`,
      tradeId: planRef,
      kind: "entry",
      price: source.entryPrice,
      title: `${label} — ${fmtPrice(source.entryPrice)}`,
      color: ENTRY_COLOR,
      lineWidth: 2,
      lineStyle: LINE_DASHED,
    });
  }

  if (toggles.stopLoss && source.stopLossPrice != null) {
    const label = plannedPrefix ? "PLANNED STOP LOSS" : "STOP LOSS";
    lines.push({
      id: `plan:${planRef}:sl`,
      tradeId: planRef,
      kind: "sl",
      price: source.stopLossPrice,
      title: `${label} — ${fmtPrice(source.stopLossPrice)}`,
      color: SL_COLOR,
      lineWidth: 2,
      lineStyle: LINE_DASHED,
    });
  }

  const tpToggle = [toggles.tp1, toggles.tp2, toggles.tp3] as const;
  for (const tp of source.takeProfits) {
    const slot = tp.index >= 1 && tp.index <= 3 ? tp.index - 1 : -1;
    if (slot < 0 || !tpToggle[slot]) continue;
    const label = plannedPrefix ? `PLANNED ${tp.label}` : tp.label;
    lines.push({
      id: `plan:${planRef}:tp${tp.index}`,
      tradeId: planRef,
      kind: "tp",
      price: tp.price,
      title: `${label} — ${fmtPrice(tp.price)}`,
      color: TP_COLORS[Math.min(slot, TP_COLORS.length - 1)]!,
      lineWidth: 2,
      lineStyle: LINE_DASHED,
      tpIndex: tp.index,
    });
  }

  const zones: ZoneDrawSpec[] = [];
  const zStart = input.zoneStart;
  const zEnd = input.zoneEnd;
  if (
    toggles.riskRewardZones &&
    zStart != null &&
    zEnd != null &&
    zEnd >= zStart &&
    source.entryPrice != null
  ) {
    if (source.stopLossPrice != null) {
      const hi = Math.max(source.entryPrice, source.stopLossPrice);
      const lo = Math.min(source.entryPrice, source.stopLossPrice);
      if (hi > lo) {
        zones.push({
          id: `plan:${planRef}:risk`,
          start: zStart,
          end: zEnd,
          priceHigh: hi,
          priceLow: lo,
          fillColor: RISK_FILL,
          strokeColor: RISK_STROKE,
          dashed: true,
        });
      }
    }

    const visibleTpPrices = source.takeProfits
      .filter((tp) => {
        const slot = tp.index >= 1 && tp.index <= 3 ? tp.index - 1 : -1;
        return slot >= 0 && tpToggle[slot];
      })
      .map((tp) => tp.price);

    if (visibleTpPrices.length) {
      const extreme =
        source.direction === "bearish"
          ? Math.min(...visibleTpPrices)
          : Math.max(...visibleTpPrices);
      const hi = Math.max(source.entryPrice, extreme);
      const lo = Math.min(source.entryPrice, extreme);
      if (hi > lo) {
        zones.push({
          id: `plan:${planRef}:reward`,
          start: zStart,
          end: zEnd,
          priceHigh: hi,
          priceLow: lo,
          fillColor: REWARD_FILL,
          strokeColor: REWARD_STROKE,
          dashed: true,
        });
      }
    }
  }

  const tpByIndex = (i: number) =>
    source.takeProfits.find((t) => t.index === i)?.price ?? null;

  return {
    status,
    legend: {
      status,
      decision: source.decision,
      direction: source.direction,
      entry: toggles.entry ? source.entryPrice : null,
      stopLoss: toggles.stopLoss ? source.stopLossPrice : null,
      tp1: toggles.tp1 ? tpByIndex(1) : null,
      tp2: toggles.tp2 ? tpByIndex(2) : null,
      tp3: toggles.tp3 ? tpByIndex(3) : null,
      primaryRr: source.primaryRr,
      planId: source.planId,
      decisionId: source.decisionId,
      plannedOnly: true,
    },
    priceLines: dedupePriceLines(lines),
    zones,
    applied: true,
    analysisTimestamp: source.analysisTimestamp,
  };
}
