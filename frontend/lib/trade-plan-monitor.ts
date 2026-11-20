/**
 * Phase 5.3.1 — Presentation-only metrics for live trade-plan monitoring.
 *
 * Distance, directional price progress, proximity, candle touches, and visual
 * alerts. Does NOT recalculate Entry/SL/TP, confluence, decisions, or R:R.
 * Never infers exchange fills or trade execution.
 */

import type { WsConnectionStatus } from "@/services/market-websocket";
import type {
  FinalDecision,
  PlanDirection,
} from "@/types/api";
import type { TradePlanVisualSource } from "@/lib/trade-plan-chart-visuals";
import type { TradeChartPriceLine } from "@/lib/trade-chart-visuals";

export type MonitorSide = "long" | "short";

export type MarketFreshness =
  | "LIVE"
  | "DELAYED"
  | "STALE"
  | "DISCONNECTED"
  | "RECONNECTING"
  | "UNAVAILABLE";

export type EntryDistanceStatus =
  | "ABOVE PLANNED ENTRY"
  | "BELOW PLANNED ENTRY"
  | "AT PLANNED ENTRY"
  | "INSIDE ENTRY ZONE"
  | "UNAVAILABLE";

export type SlProximityStatus =
  | "SAFE DISTANCE"
  | "APPROACHING SL"
  | "NEAR SL"
  | "VERY NEAR SL"
  | "PRICE AT SL LEVEL"
  | "PRICE BEYOND SL LEVEL"
  | "UNAVAILABLE";

export type TpProximityStatus =
  | "FAR"
  | "APPROACHING"
  | "NEAR TARGET"
  | "PRICE AT TARGET LEVEL"
  | "PRICE BEYOND TARGET LEVEL"
  | "UNAVAILABLE";

export type TpProgressLabel =
  | "PRICE PROGRESS"
  | "PRICE ABOVE TARGET LEVEL"
  | "PRICE BELOW TARGET LEVEL"
  | "UNAVAILABLE";

export type TouchStatus =
  | "POSSIBLE TOUCH — FORMING CANDLE"
  | "PRICE LEVEL TOUCHED — CLOSED CANDLE"
  | "TOUCH DATA UNAVAILABLE"
  | "NO TOUCH";

export type MonitorAlertType =
  | "ENTRY APPROACHING"
  | "TP1 APPROACHING"
  | "TP2 APPROACHING"
  | "TP3 APPROACHING"
  | "SL WARNING";

export type PlanLevelKind = "entry" | "sl" | "tp1" | "tp2" | "tp3";

export interface ProximityThresholds {
  /** Fraction of risk/reward span → APPROACHING (default 0.5). */
  approachingFraction: number;
  /** Fraction → NEAR (default 0.25). */
  nearFraction: number;
  /** Fraction → VERY NEAR / stronger near (default 0.10). */
  veryNearFraction: number;
  /** Absolute epsilon for "at level". */
  atLevelAbs: number;
  /** Relative epsilon vs level price for "at level". */
  atLevelRel: number;
}

export const DEFAULT_PROXIMITY_THRESHOLDS: ProximityThresholds = {
  approachingFraction: 0.5,
  nearFraction: 0.25,
  veryNearFraction: 0.1,
  atLevelAbs: 1e-8,
  atLevelRel: 1e-6,
};

export const FRESHNESS_DELAYED_MS = 5_000;
export const FRESHNESS_STALE_MS = 30_000;

export interface MonitorCandle {
  timestamp: string;
  high: number;
  low: number;
  isClosed: boolean;
}

export interface EntryDistanceModel {
  currentPrice: number | null;
  entryPrice: number | null;
  absoluteDistance: number | null;
  percentDistance: number | null;
  status: EntryDistanceStatus;
  insideEntryZone: boolean | null;
  entryLow: number | null;
  entryHigh: number | null;
  plannedLabel: boolean;
}

export interface TpProgressModel {
  index: number;
  label: string;
  targetPrice: number;
  progressPct: number | null;
  progressLabel: TpProgressLabel;
  beyondTarget: boolean;
}

export interface SlMonitorModel {
  stopLossPrice: number | null;
  currentPrice: number | null;
  absoluteDistance: number | null;
  percentDistance: number | null;
  status: SlProximityStatus;
  warningText: string | null;
}

export interface TpProximityModel {
  index: number;
  label: string;
  targetPrice: number;
  absoluteDistance: number | null;
  percentDistance: number | null;
  status: TpProximityStatus;
}

export interface LevelTouchModel {
  levelKind: PlanLevelKind;
  levelPrice: number;
  status: TouchStatus;
  candleTimestamp: string | null;
  candleClosed: boolean | null;
}

export interface MonitorAlert {
  id: string;
  type: MonitorAlertType;
  levelKind: PlanLevelKind;
  message: string;
}

export interface TradePlanMonitorModel {
  active: boolean;
  side: MonitorSide | null;
  decision: FinalDecision | null;
  freshness: MarketFreshness;
  currentPrice: number | null;
  entryDistance: EntryDistanceModel;
  tpProgress: TpProgressModel[];
  stopLoss: SlMonitorModel;
  tpProximity: TpProximityModel[];
  touches: LevelTouchModel[];
  alerts: MonitorAlert[];
  disclaimer: string;
}

function finite(n: unknown): number | null {
  if (typeof n !== "number" || !Number.isFinite(n)) return null;
  return n;
}

export function resolveMonitorSide(
  decision: FinalDecision | null | undefined,
  direction: PlanDirection | null | undefined,
): MonitorSide | null {
  if (decision === "LONG") return "long";
  if (decision === "SHORT") return "short";
  if (direction === "bullish") return "long";
  if (direction === "bearish") return "short";
  return null;
}

export function pricesNearlyEqual(
  a: number,
  b: number,
  thresholds: ProximityThresholds = DEFAULT_PROXIMITY_THRESHOLDS,
): boolean {
  const diff = Math.abs(a - b);
  const scale = Math.max(Math.abs(a), Math.abs(b), 1);
  return diff <= thresholds.atLevelAbs || diff <= scale * thresholds.atLevelRel;
}

export function resolveMarketFreshness(args: {
  connectionStatus: WsConnectionStatus | null | undefined;
  processedAt: string | null | undefined;
  hasPrice: boolean;
  source?: "websocket" | "rest-fallback" | null;
  nowMs?: number;
}): MarketFreshness {
  const status = args.connectionStatus ?? "disconnected";
  if (!args.hasPrice) return "UNAVAILABLE";
  if (status === "disconnected") return "DISCONNECTED";
  if (status === "connecting" || status === "reconnecting") return "RECONNECTING";
  if (status === "stale") return "STALE";

  const now = args.nowMs ?? Date.now();
  const processed = args.processedAt ? Date.parse(args.processedAt) : NaN;
  if (!Number.isFinite(processed)) {
    return args.source === "websocket" && status === "connected" ? "LIVE" : "DELAYED";
  }
  const age = now - processed;
  if (age >= FRESHNESS_STALE_MS) return "STALE";
  if (age >= FRESHNESS_DELAYED_MS || args.source === "rest-fallback") return "DELAYED";
  if (status === "connected" && args.source === "websocket") return "LIVE";
  return "DELAYED";
}

export function freshnessAllowsAlerts(freshness: MarketFreshness): boolean {
  return freshness === "LIVE" || freshness === "DELAYED";
}

export function computeEntryDistance(args: {
  currentPrice: number | null;
  entryPrice: number | null;
  entryLow?: number | null;
  entryHigh?: number | null;
  priceInsideZone?: boolean | null;
  decision?: FinalDecision | null;
}): EntryDistanceModel {
  const currentPrice = finite(args.currentPrice);
  const entryPrice = finite(args.entryPrice);
  const entryLow = finite(args.entryLow);
  const entryHigh = finite(args.entryHigh);
  const plannedLabel = args.decision === "WAIT" || args.decision == null;

  if (currentPrice == null || entryPrice == null || entryPrice === 0) {
    return {
      currentPrice,
      entryPrice,
      absoluteDistance: null,
      percentDistance: null,
      status: "UNAVAILABLE",
      insideEntryZone: args.priceInsideZone ?? null,
      entryLow,
      entryHigh,
      plannedLabel,
    };
  }

  const absoluteDistance = currentPrice - entryPrice;
  const percentDistance = (absoluteDistance / entryPrice) * 100;

  let insideEntryZone: boolean | null = args.priceInsideZone ?? null;
  if (insideEntryZone == null && entryLow != null && entryHigh != null) {
    const lo = Math.min(entryLow, entryHigh);
    const hi = Math.max(entryLow, entryHigh);
    insideEntryZone = currentPrice >= lo && currentPrice <= hi;
  }

  let status: EntryDistanceStatus;
  if (insideEntryZone) status = "INSIDE ENTRY ZONE";
  else if (pricesNearlyEqual(currentPrice, entryPrice)) status = "AT PLANNED ENTRY";
  else if (currentPrice > entryPrice) status = "ABOVE PLANNED ENTRY";
  else status = "BELOW PLANNED ENTRY";

  return {
    currentPrice,
    entryPrice,
    absoluteDistance,
    percentDistance,
    status,
    insideEntryZone,
    entryLow,
    entryHigh,
    plannedLabel,
  };
}

export function computeTpProgress(args: {
  side: MonitorSide | null;
  currentPrice: number | null;
  entryPrice: number | null;
  targetPrice: number | null;
  index: number;
  label?: string;
}): TpProgressModel {
  const index = args.index;
  const label = args.label ?? `TP${index}`;
  const targetPrice = finite(args.targetPrice);
  const currentPrice = finite(args.currentPrice);
  const entryPrice = finite(args.entryPrice);

  if (
    args.side == null ||
    currentPrice == null ||
    entryPrice == null ||
    targetPrice == null
  ) {
    return {
      index,
      label,
      targetPrice: targetPrice ?? Number.NaN,
      progressPct: null,
      progressLabel: "UNAVAILABLE",
      beyondTarget: false,
    };
  }

  const denom =
    args.side === "long" ? targetPrice - entryPrice : entryPrice - targetPrice;
  if (denom === 0 || !Number.isFinite(denom)) {
    return {
      index,
      label,
      targetPrice,
      progressPct: null,
      progressLabel: "UNAVAILABLE",
      beyondTarget: false,
    };
  }

  const numer =
    args.side === "long" ? currentPrice - entryPrice : entryPrice - currentPrice;
  const progressPct = (numer / denom) * 100;

  let beyondTarget = false;
  let progressLabel: TpProgressLabel = "PRICE PROGRESS";
  if (args.side === "long" && currentPrice > targetPrice && !pricesNearlyEqual(currentPrice, targetPrice)) {
    beyondTarget = true;
    progressLabel = "PRICE ABOVE TARGET LEVEL";
  } else if (
    args.side === "short" &&
    currentPrice < targetPrice &&
    !pricesNearlyEqual(currentPrice, targetPrice)
  ) {
    beyondTarget = true;
    progressLabel = "PRICE BELOW TARGET LEVEL";
  } else if (pricesNearlyEqual(currentPrice, targetPrice)) {
    beyondTarget = true;
    progressLabel =
      args.side === "long" ? "PRICE ABOVE TARGET LEVEL" : "PRICE BELOW TARGET LEVEL";
  }

  return {
    index,
    label,
    targetPrice,
    progressPct,
    progressLabel,
    beyondTarget,
  };
}

function proximityBucket(
  distanceToLevel: number,
  span: number,
  thresholds: ProximityThresholds,
): "at" | "veryNear" | "near" | "approaching" | "far" {
  if (distanceToLevel <= 0 || !Number.isFinite(distanceToLevel)) return "at";
  if (!(span > 0) || !Number.isFinite(span)) return "far";
  const ratio = distanceToLevel / span;
  if (ratio <= thresholds.veryNearFraction) return "veryNear";
  if (ratio <= thresholds.nearFraction) return "near";
  if (ratio <= thresholds.approachingFraction) return "approaching";
  return "far";
}

export function computeSlMonitor(args: {
  side: MonitorSide | null;
  currentPrice: number | null;
  entryPrice: number | null;
  stopLossPrice: number | null;
  thresholds?: ProximityThresholds;
}): SlMonitorModel {
  const thresholds = args.thresholds ?? DEFAULT_PROXIMITY_THRESHOLDS;
  const currentPrice = finite(args.currentPrice);
  const entryPrice = finite(args.entryPrice);
  const stopLossPrice = finite(args.stopLossPrice);

  if (currentPrice == null || stopLossPrice == null || args.side == null) {
    return {
      stopLossPrice,
      currentPrice,
      absoluteDistance: null,
      percentDistance: null,
      status: "UNAVAILABLE",
      warningText: null,
    };
  }

  const absoluteDistance = Math.abs(currentPrice - stopLossPrice);
  const percentDistance =
    stopLossPrice !== 0 ? (absoluteDistance / Math.abs(stopLossPrice)) * 100 : null;

  const beyond =
    args.side === "long"
      ? currentPrice < stopLossPrice && !pricesNearlyEqual(currentPrice, stopLossPrice)
      : currentPrice > stopLossPrice && !pricesNearlyEqual(currentPrice, stopLossPrice);

  if (beyond) {
    return {
      stopLossPrice,
      currentPrice,
      absoluteDistance,
      percentDistance,
      status: "PRICE BEYOND SL LEVEL",
      warningText:
        "PRICE CROSSED PLANNED STOP LOSS LEVEL — EXECUTION NOT VERIFIED",
    };
  }

  if (pricesNearlyEqual(currentPrice, stopLossPrice, thresholds)) {
    return {
      stopLossPrice,
      currentPrice,
      absoluteDistance,
      percentDistance,
      status: "PRICE AT SL LEVEL",
      warningText:
        "PRICE CROSSED PLANNED STOP LOSS LEVEL — EXECUTION NOT VERIFIED",
    };
  }

  const riskSpan =
    entryPrice != null ? Math.abs(entryPrice - stopLossPrice) : null;
  if (riskSpan == null || riskSpan === 0) {
    return {
      stopLossPrice,
      currentPrice,
      absoluteDistance,
      percentDistance,
      status: "SAFE DISTANCE",
      warningText: null,
    };
  }

  const bucket = proximityBucket(absoluteDistance, riskSpan, thresholds);
  const status: SlProximityStatus =
    bucket === "veryNear" || bucket === "near"
      ? bucket === "veryNear"
        ? "VERY NEAR SL"
        : "NEAR SL"
      : bucket === "approaching"
        ? "APPROACHING SL"
        : "SAFE DISTANCE";

  return {
    stopLossPrice,
    currentPrice,
    absoluteDistance,
    percentDistance,
    status,
    warningText: null,
  };
}

export function computeTpProximity(args: {
  side: MonitorSide | null;
  currentPrice: number | null;
  entryPrice: number | null;
  targetPrice: number | null;
  index: number;
  label?: string;
  thresholds?: ProximityThresholds;
}): TpProximityModel {
  const thresholds = args.thresholds ?? DEFAULT_PROXIMITY_THRESHOLDS;
  const index = args.index;
  const label = args.label ?? `TP${index}`;
  const currentPrice = finite(args.currentPrice);
  const entryPrice = finite(args.entryPrice);
  const targetPrice = finite(args.targetPrice);

  if (currentPrice == null || targetPrice == null || args.side == null) {
    return {
      index,
      label,
      targetPrice: targetPrice ?? Number.NaN,
      absoluteDistance: null,
      percentDistance: null,
      status: "UNAVAILABLE",
    };
  }

  const absoluteDistance = Math.abs(currentPrice - targetPrice);
  const percentDistance =
    targetPrice !== 0 ? (absoluteDistance / Math.abs(targetPrice)) * 100 : null;

  const beyond =
    args.side === "long"
      ? currentPrice > targetPrice && !pricesNearlyEqual(currentPrice, targetPrice)
      : currentPrice < targetPrice && !pricesNearlyEqual(currentPrice, targetPrice);

  if (beyond) {
    return {
      index,
      label,
      targetPrice,
      absoluteDistance,
      percentDistance,
      status: "PRICE BEYOND TARGET LEVEL",
    };
  }
  if (pricesNearlyEqual(currentPrice, targetPrice, thresholds)) {
    return {
      index,
      label,
      targetPrice,
      absoluteDistance,
      percentDistance,
      status: "PRICE AT TARGET LEVEL",
    };
  }

  const rewardSpan =
    entryPrice != null ? Math.abs(targetPrice - entryPrice) : null;
  if (rewardSpan == null || rewardSpan === 0) {
    return {
      index,
      label,
      targetPrice,
      absoluteDistance,
      percentDistance,
      status: "FAR",
    };
  }

  const bucket = proximityBucket(absoluteDistance, rewardSpan, thresholds);
  const status: TpProximityStatus =
    bucket === "veryNear" || bucket === "near"
      ? "NEAR TARGET"
      : bucket === "approaching"
        ? "APPROACHING"
        : "FAR";

  return {
    index,
    label,
    targetPrice,
    absoluteDistance,
    percentDistance,
    status,
  };
}

/** A candle touches a level when low <= level <= high (direction-independent). */
export function candleTouchesLevel(
  candle: Pick<MonitorCandle, "high" | "low"> | null | undefined,
  levelPrice: number | null,
): boolean {
  const level = finite(levelPrice);
  if (!candle || level == null) return false;
  const high = finite(candle.high);
  const low = finite(candle.low);
  if (high == null || low == null) return false;
  const hi = Math.max(high, low);
  const lo = Math.min(high, low);
  return lo <= level && level <= hi;
}

export function detectLevelTouch(args: {
  levelKind: PlanLevelKind;
  levelPrice: number | null;
  /** Prefer forming live candle first, then latest closed from history. */
  formingCandle?: MonitorCandle | null;
  closedCandles?: MonitorCandle[] | null;
  /** Optional now — refuse candles with timestamp in the future. */
  nowMs?: number;
}): LevelTouchModel {
  const level = finite(args.levelPrice);
  if (level == null) {
    return {
      levelKind: args.levelKind,
      levelPrice: Number.NaN,
      status: "TOUCH DATA UNAVAILABLE",
      candleTimestamp: null,
      candleClosed: null,
    };
  }

  const now = args.nowMs ?? Date.now();
  const forming = args.formingCandle;
  if (forming) {
    const ts = Date.parse(forming.timestamp);
    if (Number.isFinite(ts) && ts <= now && candleTouchesLevel(forming, level)) {
      if (!forming.isClosed) {
        return {
          levelKind: args.levelKind,
          levelPrice: level,
          status: "POSSIBLE TOUCH — FORMING CANDLE",
          candleTimestamp: forming.timestamp,
          candleClosed: false,
        };
      }
      return {
        levelKind: args.levelKind,
        levelPrice: level,
        status: "PRICE LEVEL TOUCHED — CLOSED CANDLE",
        candleTimestamp: forming.timestamp,
        candleClosed: true,
      };
    }
  }

  const closed = args.closedCandles ?? [];
  // Scan newest → oldest; first closed touch wins (no duplicate spam).
  for (let i = closed.length - 1; i >= 0; i--) {
    const c = closed[i]!;
    if (!c.isClosed) continue;
    const ts = Date.parse(c.timestamp);
    if (!Number.isFinite(ts) || ts > now) continue;
    if (candleTouchesLevel(c, level)) {
      return {
        levelKind: args.levelKind,
        levelPrice: level,
        status: "PRICE LEVEL TOUCHED — CLOSED CANDLE",
        candleTimestamp: c.timestamp,
        candleClosed: true,
      };
    }
  }

  if (!forming && closed.length === 0) {
    return {
      levelKind: args.levelKind,
      levelPrice: level,
      status: "TOUCH DATA UNAVAILABLE",
      candleTimestamp: null,
      candleClosed: null,
    };
  }

  return {
    levelKind: args.levelKind,
    levelPrice: level,
    status: "NO TOUCH",
    candleTimestamp: null,
    candleClosed: null,
  };
}

/**
 * Deduplicate touch events by level + candle timestamp so the same touch
 * does not produce repeated UI events.
 */
export function touchEventKey(touch: LevelTouchModel): string | null {
  if (
    touch.status !== "POSSIBLE TOUCH — FORMING CANDLE" &&
    touch.status !== "PRICE LEVEL TOUCHED — CLOSED CANDLE"
  ) {
    return null;
  }
  return `${touch.levelKind}|${touch.levelPrice}|${touch.candleTimestamp ?? ""}|${touch.status}`;
}

export function filterNewTouchKeys(
  touches: LevelTouchModel[],
  seenKeys: ReadonlySet<string>,
): { newKeys: string[]; nextSeen: Set<string> } {
  const nextSeen = new Set(seenKeys);
  const newKeys: string[] = [];
  for (const t of touches) {
    const key = touchEventKey(t);
    if (!key) continue;
    if (nextSeen.has(key)) continue;
    nextSeen.add(key);
    newKeys.push(key);
  }
  return { newKeys, nextSeen };
}

export function buildMonitorAlerts(args: {
  planId: string | null;
  symbol: string;
  side: MonitorSide | null;
  freshness: MarketFreshness;
  entryDistance: EntryDistanceModel;
  stopLoss: SlMonitorModel;
  tpProximity: TpProximityModel[];
}): MonitorAlert[] {
  if (!freshnessAllowsAlerts(args.freshness) || args.side == null) return [];
  const plan = args.planId ?? "plan";
  const sym = args.symbol.toUpperCase();
  const out: MonitorAlert[] = [];

  const entryStatus = args.entryDistance.status;
  if (
    entryStatus === "AT PLANNED ENTRY" ||
    entryStatus === "INSIDE ENTRY ZONE" ||
    (args.entryDistance.absoluteDistance != null &&
      args.entryDistance.entryPrice != null &&
      Math.abs(args.entryDistance.absoluteDistance) <=
        Math.abs(args.entryDistance.entryPrice) * DEFAULT_PROXIMITY_THRESHOLDS.approachingFraction * 0.02)
  ) {
    // Prefer SL/TP proximity for approaching; entry approaching when near entry by % of price
  }

  // Entry approaching: absolute distance within 0.5% of entry (compact UI threshold)
  if (
    args.entryDistance.entryPrice != null &&
    args.entryDistance.absoluteDistance != null &&
    entryStatus !== "UNAVAILABLE"
  ) {
    const nearEntry =
      Math.abs(args.entryDistance.absoluteDistance) <=
      Math.abs(args.entryDistance.entryPrice) * 0.005;
    if (nearEntry || entryStatus === "AT PLANNED ENTRY" || entryStatus === "INSIDE ENTRY ZONE") {
      out.push({
        id: `${plan}|${sym}|entry|ENTRY APPROACHING`,
        type: "ENTRY APPROACHING",
        levelKind: "entry",
        message: "ENTRY APPROACHING",
      });
    }
  }

  if (
    args.stopLoss.status === "APPROACHING SL" ||
    args.stopLoss.status === "NEAR SL" ||
    args.stopLoss.status === "VERY NEAR SL" ||
    args.stopLoss.status === "PRICE AT SL LEVEL" ||
    args.stopLoss.status === "PRICE BEYOND SL LEVEL"
  ) {
    out.push({
      id: `${plan}|${sym}|sl|SL WARNING`,
      type: "SL WARNING",
      levelKind: "sl",
      message: "SL WARNING",
    });
  }

  for (const tp of args.tpProximity) {
    if (
      tp.status === "APPROACHING" ||
      tp.status === "NEAR TARGET" ||
      tp.status === "PRICE AT TARGET LEVEL" ||
      tp.status === "PRICE BEYOND TARGET LEVEL"
    ) {
      const type = (
        tp.index === 1 ? "TP1 APPROACHING" : tp.index === 2 ? "TP2 APPROACHING" : "TP3 APPROACHING"
      ) as MonitorAlertType;
      if (tp.index < 1 || tp.index > 3) continue;
      out.push({
        id: `${plan}|${sym}|tp${tp.index}|${type}`,
        type,
        levelKind: (`tp${tp.index}` as PlanLevelKind),
        message: type,
      });
    }
  }

  return out;
}

/** Keep first occurrence of each alert id; merge with previously fired set. */
export function dedupeMonitorAlerts(
  alerts: MonitorAlert[],
  firedIds: ReadonlySet<string>,
): { visible: MonitorAlert[]; nextFired: Set<string> } {
  const nextFired = new Set(firedIds);
  const visible: MonitorAlert[] = [];
  const seen = new Set<string>();
  for (const a of alerts) {
    if (seen.has(a.id)) continue;
    seen.add(a.id);
    if (nextFired.has(a.id)) continue;
    nextFired.add(a.id);
    visible.push(a);
  }
  return { visible, nextFired };
}

export function clearMonitorForInactivePlan(): TradePlanMonitorModel {
  return {
    active: false,
    side: null,
    decision: null,
    freshness: "UNAVAILABLE",
    currentPrice: null,
    entryDistance: {
      currentPrice: null,
      entryPrice: null,
      absoluteDistance: null,
      percentDistance: null,
      status: "UNAVAILABLE",
      insideEntryZone: null,
      entryLow: null,
      entryHigh: null,
      plannedLabel: true,
    },
    tpProgress: [],
    stopLoss: {
      stopLossPrice: null,
      currentPrice: null,
      absoluteDistance: null,
      percentDistance: null,
      status: "UNAVAILABLE",
      warningText: null,
    },
    tpProximity: [],
    touches: [],
    alerts: [],
    disclaimer:
      "PRICE PROGRESS and proximity are presentation metrics from market price vs planned levels — not realized profit, fills, or guaranteed outcomes.",
  };
}

export function buildTradePlanMonitor(args: {
  source: TradePlanVisualSource | null;
  currentPrice: number | null;
  freshness: MarketFreshness;
  formingCandle?: MonitorCandle | null;
  closedCandles?: MonitorCandle[] | null;
  thresholds?: ProximityThresholds;
  /** When false (NO TRADE / invalid), clear metrics. */
  planActive?: boolean;
}): TradePlanMonitorModel {
  const base = clearMonitorForInactivePlan();
  const source = args.source;
  if (!source || args.planActive === false) {
    return {
      ...base,
      decision: source?.decision ?? null,
      freshness: args.freshness,
      currentPrice: finite(args.currentPrice),
    };
  }

  if (source.decision === "NO TRADE") {
    return {
      ...base,
      decision: "NO TRADE",
      freshness: args.freshness,
      currentPrice: finite(args.currentPrice),
    };
  }

  const side = resolveMonitorSide(source.decision, source.direction);
  const currentPrice = finite(args.currentPrice);
  const entryDistance = computeEntryDistance({
    currentPrice,
    entryPrice: source.entryPrice,
    entryLow: source.entryLow ?? null,
    entryHigh: source.entryHigh ?? null,
    priceInsideZone: source.priceInsideZone ?? null,
    decision: source.decision,
  });

  const tpProgress = source.takeProfits.map((tp) =>
    computeTpProgress({
      side,
      currentPrice,
      entryPrice: source.entryPrice,
      targetPrice: tp.price,
      index: tp.index,
      label: tp.label,
    }),
  );

  const stopLoss = computeSlMonitor({
    side,
    currentPrice,
    entryPrice: source.entryPrice,
    stopLossPrice: source.stopLossPrice,
    thresholds: args.thresholds,
  });

  const tpProximity = source.takeProfits.map((tp) =>
    computeTpProximity({
      side,
      currentPrice,
      entryPrice: source.entryPrice,
      targetPrice: tp.price,
      index: tp.index,
      label: tp.label,
      thresholds: args.thresholds,
    }),
  );

  const touches: LevelTouchModel[] = [];
  if (source.entryPrice != null) {
    touches.push(
      detectLevelTouch({
        levelKind: "entry",
        levelPrice: source.entryPrice,
        formingCandle: args.formingCandle,
        closedCandles: args.closedCandles,
      }),
    );
  }
  if (source.stopLossPrice != null) {
    touches.push(
      detectLevelTouch({
        levelKind: "sl",
        levelPrice: source.stopLossPrice,
        formingCandle: args.formingCandle,
        closedCandles: args.closedCandles,
      }),
    );
  }
  for (const tp of source.takeProfits) {
    if (tp.index < 1 || tp.index > 3) continue;
    touches.push(
      detectLevelTouch({
        levelKind: `tp${tp.index}` as PlanLevelKind,
        levelPrice: tp.price,
        formingCandle: args.formingCandle,
        closedCandles: args.closedCandles,
      }),
    );
  }

  const rawAlerts = buildMonitorAlerts({
    planId: source.planId,
    symbol: source.symbol,
    side,
    freshness: args.freshness,
    entryDistance,
    stopLoss,
    tpProximity,
  });

  return {
    active: true,
    side,
    decision: source.decision,
    freshness: args.freshness,
    currentPrice,
    entryDistance,
    tpProgress,
    stopLoss,
    tpProximity,
    touches,
    alerts: rawAlerts,
    disclaimer: base.disclaimer,
  };
}

export function planLevelLineId(
  planRef: string,
  kind: PlanLevelKind,
): string {
  if (kind === "entry") return `plan:${planRef}:entry`;
  if (kind === "sl") return `plan:${planRef}:sl`;
  return `plan:${planRef}:${kind}`;
}

/** Highlight selected / approaching lines without duplicating ids. */
export function applyPlanLineHighlights(
  lines: TradeChartPriceLine[],
  opts: {
    selectedLineId?: string | null;
    approachingLineIds?: ReadonlySet<string> | string[];
  },
): TradeChartPriceLine[] {
  const approaching = new Set(
    opts.approachingLineIds instanceof Set
      ? opts.approachingLineIds
      : (opts.approachingLineIds ?? []),
  );
  const selected = opts.selectedLineId ?? null;
  return lines.map((line) => {
    const isSelected = selected != null && line.id === selected;
    const isApproaching = approaching.has(line.id);
    if (!isSelected && !isApproaching) return line;
    return {
      ...line,
      lineWidth: (isSelected ? 4 : 3) as 1 | 2 | 3 | 4,
      // Keep dashed planned style; brighten slightly for approach.
      color: isSelected ? line.color : line.color,
      title: isSelected ? `▸ ${line.title}` : line.title,
    };
  });
}

export function approachingLineIdsFromMonitor(
  monitor: TradePlanMonitorModel,
  planRef: string,
): Set<string> {
  const ids = new Set<string>();
  if (!monitor.active) return ids;
  for (const a of monitor.alerts) {
    ids.add(planLevelLineId(planRef, a.levelKind));
  }
  return ids;
}
