/**
 * Phase 5.2.8 — Pure helpers mapping SimulatedTrade execution events to chart
 * markers and planned price lines. Backend simulation remains the source of truth.
 *
 * Clock rule: only events/levels grounded at replay clock T are visible.
 * Chart X uses candle open time (prefer event.candle_open_time).
 */

import type { UTCTimestamp } from "lightweight-charts";
import type {
  CostSnapshot,
  SimulatedTrade,
  SimulationExecutionEvent,
  TradeCostSummary,
  TradeLifecycleStatus,
} from "@/types/api";
import { toUtcTimestamp } from "@/lib/structure-chart-overlays";

export type TradeVisualMarkerKind =
  | "entry_long"
  | "entry_short"
  | "tp"
  | "sl"
  | "exit_other";

export type TradePriceLineKind = "entry" | "sl" | "tp";

export interface TradeChartToggleState {
  entryMarkers: boolean;
  exitMarkers: boolean;
  partialExits: boolean;
  entryLine: boolean;
  stopLossLine: boolean;
  takeProfitLines: boolean;
}

export const DEFAULT_TRADE_CHART_TOGGLES: TradeChartToggleState = {
  entryMarkers: true,
  exitMarkers: true,
  partialExits: true,
  entryLine: true,
  stopLossLine: true,
  takeProfitLines: true,
};

export interface TradeChartMarker {
  id: string;
  tradeId: string;
  eventId: string;
  kind: TradeVisualMarkerKind;
  time: UTCTimestamp;
  position: "atPriceTop" | "atPriceBottom" | "atPriceMiddle";
  shape: "circle" | "square" | "arrowUp" | "arrowDown";
  color: string;
  text: string;
  price: number;
  tpIndex?: number;
  timestampIso: string;
}

export interface TradeChartPriceLine {
  id: string;
  tradeId: string;
  kind: TradePriceLineKind;
  price: number;
  title: string;
  color: string;
  lineWidth: number;
  lineStyle: 0 | 1 | 2 | 3 | 4; // Solid | Dotted | Dashed | LargeDashed | SparseDotted
  tpIndex?: number;
}

export type VisibleTradeStatus = "OPEN" | "PARTIALLY CLOSED" | "CLOSED" | "PENDING";

export interface VisibleTradeAtClock {
  trade: SimulatedTrade;
  status: VisibleTradeStatus;
  events: SimulationExecutionEvent[];
  entryEvent: SimulationExecutionEvent | null;
  exitEvents: SimulationExecutionEvent[];
}

export interface TradeDetailsModel {
  tradeId: string;
  direction: "LONG" | "SHORT";
  entryPrice: number | null;
  entryTimestamp: string | null;
  exitPrice: number | null;
  exitType: string | null;
  executedQuantity: number | null;
  remainingQuantity: number | null;
  status: VisibleTradeStatus;
  realizedPnl: string | number | null;
}

export interface BuildTradeVisualsInput {
  trades: SimulatedTrade[];
  replayTimestamp: string | null;
  toggles?: Partial<TradeChartToggleState>;
  /** Optional costs for realized P&L in details (never invented). */
  costs?: CostSnapshot | null;
  selectedEventId?: string | null;
}

const LONG_ENTRY = "#22c55e";
const SHORT_ENTRY = "#ef4444";
const TP_COLOR = "#38bdf8";
const SL_COLOR = "#f97316";
const EXIT_OTHER = "#a78bfa";
const ENTRY_LINE = "#94a3b8";

function clockMs(replayTimestamp: string | null): number {
  if (!replayTimestamp) return Number.POSITIVE_INFINITY;
  const ms = Date.parse(replayTimestamp);
  return Number.isFinite(ms) ? ms : Number.POSITIVE_INFINITY;
}

function eventMs(ev: SimulationExecutionEvent): number {
  const ms = Date.parse(ev.timestamp);
  return Number.isFinite(ms) ? ms : Number.NEGATIVE_INFINITY;
}

/** Stable dedupe of events by event_id (first occurrence wins). */
export function dedupeEventsById(
  events: SimulationExecutionEvent[],
): SimulationExecutionEvent[] {
  const seen = new Set<string>();
  const out: SimulationExecutionEvent[] = [];
  for (const ev of events) {
    if (!ev.event_id) continue;
    if (seen.has(ev.event_id)) continue;
    seen.add(ev.event_id);
    out.push(ev);
  }
  return out;
}

/** Events at or before the replay clock. */
export function filterEventsAtOrBeforeClock(
  events: SimulationExecutionEvent[],
  replayTimestamp: string | null,
): SimulationExecutionEvent[] {
  const t = clockMs(replayTimestamp);
  return dedupeEventsById(events).filter((ev) => eventMs(ev) <= t);
}

function chartTimeForEvent(ev: SimulationExecutionEvent): UTCTimestamp | null {
  const iso = ev.candle_open_time || ev.timestamp;
  if (!iso) return null;
  try {
    return toUtcTimestamp(iso);
  } catch {
    return null;
  }
}

function isFillPrice(price: number | null | undefined): price is number {
  return typeof price === "number" && Number.isFinite(price);
}

function tpLabel(tpIndex: number | null | undefined): string {
  if (tpIndex == null || !Number.isFinite(tpIndex)) return "TP";
  return `TP${Math.trunc(tpIndex) + 1}`;
}

function isStopLossExit(ev: SimulationExecutionEvent): boolean {
  if (ev.event_type !== "trade_closed" && ev.event_type !== "trade_ambiguous") return false;
  const reason = (ev.reason ?? "").toLowerCase();
  return reason.includes("stop");
}

function isTpExit(ev: SimulationExecutionEvent): boolean {
  return (
    ev.event_type === "trade_partially_closed" ||
    (ev.event_type === "trade_closed" && !isStopLossExit(ev) && (ev.tp_index != null || /tp\d/i.test(ev.reason ?? "")))
  );
}

function deriveStatus(events: SimulationExecutionEvent[]): VisibleTradeStatus {
  const types = new Set(events.map((e) => e.event_type));
  if (types.has("trade_closed")) return "CLOSED";
  if (types.has("trade_partially_closed")) return "PARTIALLY CLOSED";
  if (types.has("trade_opened")) return "OPEN";
  if (types.has("trade_pending")) return "PENDING";
  return "PENDING";
}

/**
 * Trades known at clock T (decision <= T), excluding rejected/cancelled.
 * Event lists are filtered to timestamp <= T.
 */
export function visibleTradesAtClock(
  trades: SimulatedTrade[],
  replayTimestamp: string | null,
): VisibleTradeAtClock[] {
  const t = clockMs(replayTimestamp);
  const out: VisibleTradeAtClock[] = [];
  for (const trade of trades) {
    if (trade.lifecycle_status === "rejected" || trade.lifecycle_status === "cancelled") {
      continue;
    }
    const decisionMs = Date.parse(trade.decision_timestamp);
    if (!Number.isFinite(decisionMs) || decisionMs > t) continue;

    const events = filterEventsAtOrBeforeClock(trade.execution_events ?? [], replayTimestamp);
    // Hide cancelled/rejected that only show via past events if status was filtered above.
    const status = deriveStatus(events);
    const entryEvent =
      events.find((e) => e.event_type === "trade_opened" && isFillPrice(e.price)) ?? null;
    const exitEvents = events.filter(
      (e) =>
        e.event_type === "trade_partially_closed" ||
        e.event_type === "trade_closed" ||
        (e.event_type === "trade_ambiguous" && isFillPrice(e.price)),
    );
    out.push({ trade, status, events, entryEvent, exitEvents });
  }
  return out;
}

export function mapEntryMarker(
  trade: SimulatedTrade,
  entryEvent: SimulationExecutionEvent,
): TradeChartMarker | null {
  if (entryEvent.event_type !== "trade_opened") return null;
  if (!isFillPrice(entryEvent.price)) return null;
  const time = chartTimeForEvent(entryEvent);
  if (time == null) return null;
  const long = trade.direction === "LONG";
  return {
    id: entryEvent.event_id,
    tradeId: trade.trade_id,
    eventId: entryEvent.event_id,
    kind: long ? "entry_long" : "entry_short",
    time,
    position: long ? "atPriceBottom" : "atPriceTop",
    shape: long ? "arrowUp" : "arrowDown",
    color: long ? LONG_ENTRY : SHORT_ENTRY,
    text: long ? "LONG" : "SHORT",
    price: entryEvent.price,
    timestampIso: entryEvent.timestamp,
  };
}

export function mapExitMarker(
  trade: SimulatedTrade,
  exitEvent: SimulationExecutionEvent,
): TradeChartMarker | null {
  if (!isFillPrice(exitEvent.price)) return null;
  const time = chartTimeForEvent(exitEvent);
  if (time == null) return null;

  if (isStopLossExit(exitEvent)) {
    return {
      id: exitEvent.event_id,
      tradeId: trade.trade_id,
      eventId: exitEvent.event_id,
      kind: "sl",
      time,
      position: trade.direction === "LONG" ? "atPriceTop" : "atPriceBottom",
      shape: "arrowDown",
      color: SL_COLOR,
      text: "SL",
      price: exitEvent.price,
      timestampIso: exitEvent.timestamp,
    };
  }

  if (isTpExit(exitEvent) || exitEvent.event_type === "trade_partially_closed") {
    const label = tpLabel(exitEvent.tp_index);
    return {
      id: exitEvent.event_id,
      tradeId: trade.trade_id,
      eventId: exitEvent.event_id,
      kind: "tp",
      time,
      position: trade.direction === "LONG" ? "atPriceTop" : "atPriceBottom",
      shape: "circle",
      color: TP_COLOR,
      text: label,
      price: exitEvent.price,
      tpIndex: exitEvent.tp_index ?? undefined,
      timestampIso: exitEvent.timestamp,
    };
  }

  if (exitEvent.event_type === "trade_closed" || exitEvent.event_type === "trade_ambiguous") {
    return {
      id: exitEvent.event_id,
      tradeId: trade.trade_id,
      eventId: exitEvent.event_id,
      kind: "exit_other",
      time,
      position: "atPriceMiddle",
      shape: "square",
      color: EXIT_OTHER,
      text: "EXIT",
      price: exitEvent.price,
      timestampIso: exitEvent.timestamp,
    };
  }

  return null;
}

/**
 * Planned levels (not executed fills). Visible once the trade is known at clock
 * and has an entry fill (or pending with a limit) — never invents missing TPs.
 */
export function mapTradePriceLines(
  visible: VisibleTradeAtClock,
  toggles: TradeChartToggleState,
): TradeChartPriceLine[] {
  const { trade, entryEvent, status } = visible;
  if (status === "PENDING" && !entryEvent) {
    // Pending: show planned levels from known plan fields only.
  } else if (!entryEvent && status !== "PENDING") {
    return [];
  }

  const shortId = trade.trade_id.replace(/^st_/, "").slice(0, 6);
  const lines: TradeChartPriceLine[] = [];

  const entryPrice =
    entryEvent && isFillPrice(entryEvent.price)
      ? entryEvent.price
      : isFillPrice(trade.entry_price)
        ? trade.entry_price
        : isFillPrice(trade.entry_limit_price)
          ? trade.entry_limit_price
          : null;

  if (toggles.entryLine && entryPrice != null) {
    lines.push({
      id: `pl:${trade.trade_id}:entry`,
      tradeId: trade.trade_id,
      kind: "entry",
      price: entryPrice,
      title: `Entry · ${shortId}`,
      color: ENTRY_LINE,
      lineWidth: 1,
      lineStyle: 2,
    });
  }

  if (toggles.stopLossLine && Number.isFinite(trade.current_stop_loss)) {
    lines.push({
      id: `pl:${trade.trade_id}:sl`,
      tradeId: trade.trade_id,
      kind: "sl",
      price: trade.current_stop_loss,
      title: `SL · ${shortId}`,
      color: SL_COLOR,
      lineWidth: 1,
      lineStyle: 1,
    });
  }

  if (toggles.takeProfitLines) {
    trade.take_profit_levels.forEach((price, i) => {
      if (!Number.isFinite(price)) return;
      lines.push({
        id: `pl:${trade.trade_id}:tp:${i}`,
        tradeId: trade.trade_id,
        kind: "tp",
        price,
        title: `TP${i + 1} · ${shortId}`,
        color: TP_COLOR,
        lineWidth: 1,
        lineStyle: 2,
        tpIndex: i,
      });
    });
  }

  return lines;
}

export function buildTradeChartMarkers(
  visible: VisibleTradeAtClock[],
  toggles: TradeChartToggleState,
): TradeChartMarker[] {
  const markers: TradeChartMarker[] = [];
  const seen = new Set<string>();

  for (const row of visible) {
    if (toggles.entryMarkers && row.entryEvent) {
      const m = mapEntryMarker(row.trade, row.entryEvent);
      if (m && !seen.has(m.id)) {
        seen.add(m.id);
        markers.push(m);
      }
    }

    for (const ev of row.exitEvents) {
      const isPartial = ev.event_type === "trade_partially_closed";
      if (isPartial && !toggles.partialExits) continue;
      if (!isPartial && !toggles.exitMarkers) continue;
      // Partials also count as exit markers when exitMarkers is on; gated by partialExits.
      if (!isPartial && toggles.exitMarkers === false) continue;

      const m = mapExitMarker(row.trade, ev);
      if (m && !seen.has(m.id)) {
        seen.add(m.id);
        markers.push(m);
      }
    }
  }

  return markers;
}

export function buildTradeChartPriceLines(
  visible: VisibleTradeAtClock[],
  toggles: TradeChartToggleState,
): TradeChartPriceLine[] {
  const lines: TradeChartPriceLine[] = [];
  const seen = new Set<string>();
  for (const row of visible) {
    // Show plan lines once decision is known; require entry fill OR pending with limit.
    const hasPlan =
      row.entryEvent != null ||
      row.status === "PENDING" ||
      row.status === "OPEN" ||
      row.status === "PARTIALLY CLOSED" ||
      row.status === "CLOSED";
    if (!hasPlan) continue;
    for (const line of mapTradePriceLines(row, toggles)) {
      if (seen.has(line.id)) continue;
      seen.add(line.id);
      lines.push(line);
    }
  }
  return lines;
}

export function findCostForTrade(
  costs: CostSnapshot | null | undefined,
  tradeId: string,
): TradeCostSummary | null {
  if (!costs?.trades?.length) return null;
  return costs.trades.find((t) => t.trade_id === tradeId) ?? null;
}

export function buildTradeDetails(
  visible: VisibleTradeAtClock,
  costs: CostSnapshot | null | undefined,
  selectedEventId?: string | null,
): TradeDetailsModel {
  const { trade, status, entryEvent, exitEvents } = visible;
  const selected =
    (selectedEventId
      ? exitEvents.find((e) => e.event_id === selectedEventId) ??
        (entryEvent?.event_id === selectedEventId ? entryEvent : null)
      : null) ?? null;

  const lastExit = exitEvents.length ? exitEvents[exitEvents.length - 1]! : null;
  const focusExit = selected && selected.event_type !== "trade_opened" ? selected : lastExit;

  let exitType: string | null = null;
  if (focusExit) {
    if (isStopLossExit(focusExit)) exitType = "Stop Loss";
    else if (isTpExit(focusExit)) exitType = tpLabel(focusExit.tp_index);
    else if (focusExit.event_type === "trade_closed") exitType = "Exit";
    else if (focusExit.event_type === "trade_ambiguous") exitType = "Ambiguous";
  }

  // Realized P&L only when trade is fully closed at this clock and costs supply it.
  let realizedPnl: string | number | null = null;
  if (status === "CLOSED") {
    const cost = findCostForTrade(costs, trade.trade_id);
    if (cost && cost.net_realized_pnl != null) realizedPnl = cost.net_realized_pnl;
  }

  const remainingFromEvent =
    focusExit?.remaining_quantity ??
    entryEvent?.remaining_quantity ??
    (status === "CLOSED" ? 0 : trade.remaining_quantity);

  return {
    tradeId: trade.trade_id,
    direction: trade.direction,
    entryPrice: entryEvent && isFillPrice(entryEvent.price) ? entryEvent.price : trade.entry_price ?? null,
    entryTimestamp: entryEvent?.timestamp ?? trade.entry_timestamp ?? null,
    exitPrice: focusExit && isFillPrice(focusExit.price) ? focusExit.price : null,
    exitType: status === "OPEN" || status === "PENDING" ? null : exitType,
    executedQuantity:
      focusExit && focusExit.quantity != null
        ? focusExit.quantity
        : entryEvent?.quantity ?? trade.executed_quantity,
    remainingQuantity: remainingFromEvent,
    status,
    realizedPnl,
  };
}

export function buildTradeVisuals(input: BuildTradeVisualsInput): {
  markers: TradeChartMarker[];
  priceLines: TradeChartPriceLine[];
  visible: VisibleTradeAtClock[];
  details: TradeDetailsModel | null;
} {
  const toggles: TradeChartToggleState = {
    ...DEFAULT_TRADE_CHART_TOGGLES,
    ...input.toggles,
  };
  const visible = visibleTradesAtClock(input.trades, input.replayTimestamp);
  const markers = buildTradeChartMarkers(visible, toggles);
  const priceLines = buildTradeChartPriceLines(visible, toggles);

  let details: TradeDetailsModel | null = null;
  if (input.selectedEventId) {
    const row =
      visible.find(
        (v) =>
          v.entryEvent?.event_id === input.selectedEventId ||
          v.exitEvents.some((e) => e.event_id === input.selectedEventId) ||
          v.trade.trade_id === input.selectedEventId,
      ) ?? null;
    if (row) details = buildTradeDetails(row, input.costs, input.selectedEventId);
  }

  return { markers, priceLines, visible, details };
}

/** Lifecycle status string for UI from filtered events (not raw trade.lifecycle_status). */
export function historicalStatusLabel(status: VisibleTradeStatus): string {
  return status;
}

export function statusFromLifecycle(raw: TradeLifecycleStatus, atClockClosed: boolean): VisibleTradeStatus {
  if (atClockClosed) return "CLOSED";
  if (raw === "partially_closed") return "PARTIALLY CLOSED";
  if (raw === "open") return "OPEN";
  if (raw === "pending_entry") return "PENDING";
  if (raw === "closed_tp" || raw === "closed_sl" || raw === "closed_expired") return "CLOSED";
  return "PENDING";
}
