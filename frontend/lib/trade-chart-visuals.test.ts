import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { SimulatedTrade, SimulationExecutionEvent } from "@/types/api";
import {
  DEFAULT_TRADE_CHART_TOGGLES,
  buildTradeChartMarkers,
  buildTradeChartPriceLines,
  buildTradeDetails,
  buildTradeVisuals,
  dedupeEventsById,
  filterEventsAtOrBeforeClock,
  mapEntryMarker,
  mapExitMarker,
  visibleTradesAtClock,
} from "@/lib/trade-chart-visuals";

function ev(
  partial: Partial<SimulationExecutionEvent> &
    Pick<SimulationExecutionEvent, "event_id" | "event_type" | "timestamp">,
): SimulationExecutionEvent {
  return {
    price: null,
    quantity: null,
    remaining_quantity: null,
    tp_index: null,
    reason: null,
    ambiguity_policy_applied: null,
    candle_open_time: null,
    metadata: {},
    ...partial,
  };
}

function trade(partial: Partial<SimulatedTrade> = {}): SimulatedTrade {
  return {
    trade_id: "st_abcd1234",
    signal_key: "k",
    replay_session_id: "rp",
    exchange: "binance",
    symbol: "BTC/USDT",
    market_type: "spot",
    direction: "LONG",
    decision: "LONG",
    decision_timestamp: "2024-01-01T12:00:00.000Z",
    decision_event_index: 0,
    lifecycle_status: "open",
    initial_stop_loss: 95,
    current_stop_loss: 95,
    take_profit_levels: [105, 110, 115],
    tp_allocations: [0.4, 0.3, 0.3],
    tp_filled: [false, false, false],
    original_quantity: 1,
    remaining_quantity: 1,
    executed_quantity: 1,
    quantity_closed_tp: 0,
    quantity_closed_sl: 0,
    quantity_closed_expired: 0,
    ambiguity_warnings: [],
    realized_pnl_placeholder: null,
    execution_events: [],
    config_version: "v1",
    created_at: "2024-01-01T12:00:00.000Z",
    updated_at: "2024-01-01T12:05:00.000Z",
    entry_limit_price: 100,
    entry_price: 100,
    entry_timestamp: "2024-01-01T12:04:59.999Z",
    ...partial,
  };
}

const openEvt = ev({
  event_id: "se_open1",
  event_type: "trade_opened",
  timestamp: "2024-01-01T12:04:59.999Z",
  candle_open_time: "2024-01-01T12:00:00.000Z",
  price: 100,
  quantity: 1,
  remaining_quantity: 1,
  reason: "Limit entry filled.",
});

const tp1 = ev({
  event_id: "se_tp1",
  event_type: "trade_partially_closed",
  timestamp: "2024-01-01T12:14:59.999Z",
  candle_open_time: "2024-01-01T12:10:00.000Z",
  price: 105,
  quantity: 0.4,
  remaining_quantity: 0.6,
  tp_index: 0,
  reason: "TP1 partial close.",
});

const tp2 = ev({
  event_id: "se_tp2",
  event_type: "trade_partially_closed",
  timestamp: "2024-01-01T12:24:59.999Z",
  candle_open_time: "2024-01-01T12:20:00.000Z",
  price: 110,
  quantity: 0.3,
  remaining_quantity: 0.3,
  tp_index: 1,
  reason: "TP2 partial close.",
});

const tp3 = ev({
  event_id: "se_tp3",
  event_type: "trade_closed",
  timestamp: "2024-01-01T12:34:59.999Z",
  candle_open_time: "2024-01-01T12:30:00.000Z",
  price: 115,
  quantity: 0.3,
  remaining_quantity: 0,
  tp_index: 2,
  reason: "TP3 final close.",
});

const sl = ev({
  event_id: "se_sl1",
  event_type: "trade_closed",
  timestamp: "2024-01-01T12:19:59.999Z",
  candle_open_time: "2024-01-01T12:15:00.000Z",
  price: 95,
  quantity: 1,
  remaining_quantity: 0,
  reason: "Stop loss filled.",
});

describe("trade chart visuals (Phase 5.2.8)", () => {
  it("maps LONG entry marker from fill event", () => {
    const m = mapEntryMarker(trade({ direction: "LONG" }), openEvt);
    assert.ok(m);
    assert.equal(m!.kind, "entry_long");
    assert.equal(m!.text, "LONG");
    assert.equal(m!.shape, "arrowUp");
    assert.equal(m!.price, 100);
    assert.equal(m!.time, Math.floor(Date.parse("2024-01-01T12:00:00.000Z") / 1000));
  });

  it("maps SHORT entry marker from fill event", () => {
    const m = mapEntryMarker(trade({ direction: "SHORT" }), openEvt);
    assert.ok(m);
    assert.equal(m!.kind, "entry_short");
    assert.equal(m!.text, "SHORT");
    assert.equal(m!.shape, "arrowDown");
  });

  it("does not invent entry marker without fill price", () => {
    const pending = ev({
      event_id: "se_pend",
      event_type: "trade_pending",
      timestamp: "2024-01-01T12:00:00.000Z",
      price: 100,
    });
    assert.equal(mapEntryMarker(trade(), pending), null);
  });

  it("maps TP1/TP2/TP3 markers separately", () => {
    const t = trade({
      lifecycle_status: "closed_tp",
      execution_events: [openEvt, tp1, tp2, tp3],
    });
    const visible = visibleTradesAtClock([t], "2024-01-01T12:40:00.000Z");
    const markers = buildTradeChartMarkers(visible, DEFAULT_TRADE_CHART_TOGGLES);
    const labels = markers.filter((m) => m.kind === "tp" || m.kind === "exit_other").map((m) => m.text);
    assert.deepEqual(labels, ["TP1", "TP2", "TP3"]);
    assert.equal(markers.filter((m) => m.kind === "entry_long").length, 1);
  });

  it("maps stop-loss marker from executed SL event", () => {
    const m = mapExitMarker(trade(), sl);
    assert.ok(m);
    assert.equal(m!.kind, "sl");
    assert.equal(m!.text, "SL");
    assert.equal(m!.price, 95);
  });

  it("filters events by replay clock timestamp", () => {
    const events = [openEvt, tp1, tp2, tp3];
    const mid = filterEventsAtOrBeforeClock(events, "2024-01-01T12:16:00.000Z");
    assert.deepEqual(
      mid.map((e) => e.event_id),
      ["se_open1", "se_tp1"],
    );
  });

  it("hides future exit markers at earlier clock", () => {
    const t = trade({
      lifecycle_status: "closed_tp",
      execution_events: [openEvt, tp1, tp2, tp3],
    });
    const visible = visibleTradesAtClock([t], "2024-01-01T12:16:00.000Z");
    const markers = buildTradeChartMarkers(visible, DEFAULT_TRADE_CHART_TOGGLES);
    assert.equal(markers.some((m) => m.text === "TP2"), false);
    assert.equal(markers.some((m) => m.text === "TP3"), false);
    assert.equal(markers.some((m) => m.text === "TP1"), true);
  });

  it("represents open trade at intermediate clock", () => {
    const t = trade({
      lifecycle_status: "closed_tp",
      execution_events: [openEvt, tp1, tp2, tp3],
      exit_timestamp: tp3.timestamp,
    });
    const visible = visibleTradesAtClock([t], "2024-01-01T12:10:00.000Z");
    assert.equal(visible.length, 1);
    assert.equal(visible[0]!.status, "OPEN");
    const details = buildTradeDetails(visible[0]!, null);
    assert.equal(details.status, "OPEN");
    assert.equal(details.exitPrice, null);
    assert.equal(details.realizedPnl, null);
  });

  it("backward seek removes future markers", () => {
    const t = trade({
      lifecycle_status: "closed_tp",
      execution_events: [openEvt, tp1, tp2, tp3],
    });
    const late = buildTradeVisuals({
      trades: [t],
      replayTimestamp: "2024-01-01T12:40:00.000Z",
    });
    const early = buildTradeVisuals({
      trades: [t],
      replayTimestamp: "2024-01-01T12:05:00.000Z",
    });
    assert.ok(late.markers.length > early.markers.length);
    assert.equal(early.markers.every((m) => Date.parse(m.timestampIso) <= Date.parse("2024-01-01T12:05:00.000Z")), true);
    assert.equal(early.markers.some((m) => m.text.startsWith("TP")), false);
  });

  it("forward seek restores markers deterministically without duplicates", () => {
    const t = trade({
      lifecycle_status: "closed_tp",
      execution_events: [openEvt, tp1, tp2, tp3, tp1, openEvt],
    });
    const a = buildTradeVisuals({
      trades: [t],
      replayTimestamp: "2024-01-01T12:40:00.000Z",
    });
    const b = buildTradeVisuals({
      trades: [t],
      replayTimestamp: "2024-01-01T12:40:00.000Z",
    });
    assert.deepEqual(
      a.markers.map((m) => m.id),
      b.markers.map((m) => m.id),
    );
    const ids = a.markers.map((m) => m.id);
    assert.equal(ids.length, new Set(ids).size);
  });

  it("deduplicates repeated event ids", () => {
    const duped = dedupeEventsById([openEvt, openEvt, tp1, tp1]);
    assert.equal(duped.length, 2);
  });

  it("handles missing optional fields without inventing exits", () => {
    const bare = trade({
      entry_price: null,
      entry_timestamp: null,
      take_profit_levels: [],
      execution_events: [
        ev({
          event_id: "se_open2",
          event_type: "trade_opened",
          timestamp: "2024-01-01T12:04:59.999Z",
          candle_open_time: "2024-01-01T12:00:00.000Z",
          price: 101,
          quantity: 1,
        }),
      ],
    });
    const { markers, priceLines } = buildTradeVisuals({
      trades: [bare],
      replayTimestamp: "2024-01-01T12:10:00.000Z",
    });
    assert.equal(markers.length, 1);
    assert.equal(markers[0]!.price, 101);
    assert.equal(priceLines.filter((l) => l.kind === "tp").length, 0);
    assert.ok(priceLines.some((l) => l.kind === "sl"));
  });

  it("keeps overlapping price levels readable with distinct ids/titles", () => {
    const a = trade({
      trade_id: "st_aaa",
      take_profit_levels: [105],
      execution_events: [openEvt],
    });
    const b = trade({
      trade_id: "st_bbb",
      decision_timestamp: "2024-01-01T12:00:00.000Z",
      take_profit_levels: [105],
      current_stop_loss: 95,
      execution_events: [
        ev({
          ...openEvt,
          event_id: "se_open_b",
        }),
      ],
    });
    const lines = buildTradeChartPriceLines(
      visibleTradesAtClock([a, b], "2024-01-01T12:10:00.000Z"),
      DEFAULT_TRADE_CHART_TOGGLES,
    );
    const tpLines = lines.filter((l) => l.kind === "tp");
    assert.equal(tpLines.length, 2);
    assert.notEqual(tpLines[0]!.id, tpLines[1]!.id);
    assert.ok(tpLines.every((l) => l.title.includes("TP1")));
  });

  it("honors toggle behavior", () => {
    const t = trade({
      lifecycle_status: "closed_tp",
      execution_events: [openEvt, tp1, tp3],
    });
    const off = buildTradeVisuals({
      trades: [t],
      replayTimestamp: "2024-01-01T12:40:00.000Z",
      toggles: {
        entryMarkers: false,
        exitMarkers: true,
        partialExits: false,
        entryLine: false,
        stopLossLine: false,
        takeProfitLines: true,
      },
    });
    assert.equal(off.markers.some((m) => m.kind === "entry_long"), false);
    assert.equal(off.markers.some((m) => m.text === "TP1"), false);
    assert.equal(off.markers.some((m) => m.text === "TP3"), true);
    assert.equal(off.priceLines.some((l) => l.kind === "entry"), false);
    assert.equal(off.priceLines.some((l) => l.kind === "tp"), true);
  });

  it("clears overlays when session trades are empty", () => {
    const { markers, priceLines } = buildTradeVisuals({
      trades: [],
      replayTimestamp: "2024-01-01T12:10:00.000Z",
    });
    assert.deepEqual(markers, []);
    assert.deepEqual(priceLines, []);
  });

  it("hides future trades entirely", () => {
    const future = trade({
      decision_timestamp: "2024-01-02T00:00:00.000Z",
      execution_events: [
        ev({
          event_id: "se_fut",
          event_type: "trade_opened",
          timestamp: "2024-01-02T00:04:59.999Z",
          candle_open_time: "2024-01-02T00:00:00.000Z",
          price: 120,
        }),
      ],
    });
    assert.equal(visibleTradesAtClock([future], "2024-01-01T12:00:00.000Z").length, 0);
  });
});
