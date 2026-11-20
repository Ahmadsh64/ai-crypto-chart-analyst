import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  candlesFromReplaySnapshot,
  clampSeekIndex,
  formatReplayClock,
  replayProgressLabel,
  replayStatusLabel,
  scrubberEnabled,
  scrubberLabel,
} from "@/lib/replay-display";
import type { Candle, ReplaySnapshot } from "@/types/api";

const baseCandle = (ts: string, high = 110): Candle => ({
  timestamp: ts,
  open: 100,
  high,
  low: 90,
  close: 105,
  volume: 1,
  exchange: "binance",
  symbol: "BTC/USDT",
  market_type: "spot",
  is_closed: true,
});

function snap(partial: Partial<ReplaySnapshot> = {}): ReplaySnapshot {
  return {
    session_id: "rp_test",
    replay_timestamp: "2024-01-01T00:04:59.999Z",
    exchange: "binance",
    symbol: "BTC/USDT",
    market_type: "spot",
    event_index: 0,
    event_count: 10,
    progress_pct: 10,
    status: "paused",
    speed: "10x",
    timeframes: {
      "5m": {
        timeframe: "5m",
        closed_candles: [baseCandle("2024-01-01T00:00:00.000Z")],
        closed_count: 1,
        forming_candle: null,
        is_ready: true,
        data_quality: "ok",
        gap_count: 0,
      },
      "15m": {
        timeframe: "15m",
        closed_candles: [],
        closed_count: 0,
        forming_candle: {
          ...baseCandle("2024-01-01T00:00:00.000Z", 108),
          is_closed: false,
        },
        is_ready: false,
        data_quality: "insufficient",
        gap_count: 0,
      },
    },
    gaps: [],
    data_quality: "partial",
    limitations: [],
    config_version: "replay-v1.0.0",
    timestamp_convention: "open_time_utc",
    ...partial,
  };
}

describe("replay display helpers (Phase 5.1)", () => {
  it("exposes only closed + forming for selected TF", () => {
    const { closed, forming } = candlesFromReplaySnapshot(snap(), "15m");
    assert.equal(closed.length, 0);
    assert.ok(forming);
    assert.equal(forming?.is_closed, false);
    assert.equal(forming?.high, 108);
  });

  it("does not invent candles when TF missing", () => {
    const { closed, forming } = candlesFromReplaySnapshot(snap(), "1h");
    assert.deepEqual(closed, []);
    assert.equal(forming, null);
  });

  it("formats progress and status", () => {
    assert.match(replayProgressLabel(snap()), /1 \/ 10/);
    assert.equal(replayStatusLabel("running"), "Playing");
    assert.match(formatReplayClock("2024-01-01T00:04:59.999Z"), /UTC/);
  });

  it("disables scrubber without session or events", () => {
    assert.equal(scrubberEnabled(null, { sessionReady: false, busy: false }), false);
    assert.equal(scrubberEnabled(snap(), { sessionReady: false, busy: false }), false);
    assert.equal(scrubberEnabled(snap(), { sessionReady: true, busy: true }), false);
    assert.equal(
      scrubberEnabled(snap({ event_count: 0 }), { sessionReady: true, busy: false }),
      false,
    );
    assert.equal(scrubberEnabled(snap(), { sessionReady: true, busy: false }), true);
  });

  it("clamps seek index and labels scrubber", () => {
    assert.equal(clampSeekIndex(-3, 10), 0);
    assert.equal(clampSeekIndex(99, 10), 9);
    assert.equal(clampSeekIndex(4.7, 10), 4);
    assert.equal(scrubberLabel(0, 10), "Event 1 / 10");
    assert.equal(scrubberLabel(0, 0), "No events");
  });
});
