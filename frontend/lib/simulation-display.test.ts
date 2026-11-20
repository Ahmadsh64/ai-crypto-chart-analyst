import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { SimulatedTrade, SimulationSnapshot } from "@/types/api";

function visibleAtClock(trades: SimulatedTrade[], clockIso: string): SimulatedTrade[] {
  const clockMs = new Date(clockIso).getTime();
  return trades.filter((t) => {
    if (t.lifecycle_status === "rejected" || t.lifecycle_status === "cancelled") return false;
    return new Date(t.decision_timestamp).getTime() <= clockMs;
  });
}

function exitMarkerVisible(trade: SimulatedTrade, clockIso: string): boolean {
  if (!trade.exit_timestamp) return false;
  return new Date(trade.exit_timestamp).getTime() <= new Date(clockIso).getTime();
}

const base: SimulatedTrade = {
  trade_id: "st_1",
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
  take_profit_levels: [105],
  tp_allocations: [1],
  tp_filled: [false],
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
  entry_price: 100,
  entry_timestamp: "2024-01-01T12:05:00.000Z",
  exit_timestamp: "2024-01-01T12:20:00.000Z",
};

describe("simulation display no-look-ahead (Phase 5.2.2)", () => {
  it("hides trades decided after the replay clock", () => {
    assert.equal(visibleAtClock([base], "2023-12-31T00:00:00.000Z").length, 0);
  });

  it("shows trade after decision time", () => {
    assert.equal(visibleAtClock([base], "2024-01-01T12:00:00.000Z").length, 1);
  });

  it("does not show future exit markers", () => {
    assert.equal(exitMarkerVisible(base, "2024-01-01T12:10:00.000Z"), false);
    assert.equal(exitMarkerVisible(base, "2024-01-01T12:20:00.000Z"), true);
  });

  it("snapshot disclaimer is present", () => {
    const snap: SimulationSnapshot = {
      session_id: "rp",
      enabled: true,
      overview: {
        enabled: true,
        pending_count: 0,
        open_count: 1,
        partially_closed_count: 0,
        closed_count: 0,
        rejected_count: 0,
        cancelled_count: 0,
        ambiguous_count: 0,
        total_trades: 1,
        config: {},
        disclaimer: "HISTORICAL SIMULATION — NOT REAL ORDERS",
      },
      trades: [base],
      recent_events: [],
      config_version: "v1",
      disclaimer: "HISTORICAL SIMULATION — NOT REAL ORDERS",
    };
    assert.match(snap.disclaimer, /NOT REAL ORDERS/);
  });
});
