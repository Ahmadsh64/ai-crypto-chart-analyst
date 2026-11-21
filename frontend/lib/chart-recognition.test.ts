import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  draftFromVision,
  formatConfidence,
  formatDiscrepancyPct,
  needsSymbolConfirmation,
  needsTimeframeConfirmation,
  normalizeDetectedExchange,
  normalizeDetectedSymbol,
  normalizeDetectedTimeframe,
} from "./chart-recognition";
import type { VisionResult } from "@/types/api";

describe("Phase 5.4.2.2 chart recognition helpers", () => {
  it("normalizes symbols and timeframes without inventing unknowns", () => {
    assert.equal(normalizeDetectedSymbol("btc-usdt"), "BTC/USDT");
    assert.equal(normalizeDetectedSymbol("ETHUSDT"), "ETH/USDT");
    assert.equal(normalizeDetectedSymbol(""), "");
    assert.equal(normalizeDetectedTimeframe("1H"), "1h");
    assert.equal(normalizeDetectedTimeframe("15min"), "15m");
    assert.equal(normalizeDetectedTimeframe("mystery"), null);
    assert.equal(normalizeDetectedExchange("Binance Spot"), "binance");
    assert.equal(normalizeDetectedExchange("TradingView"), null);
  });

  it("requires confirmation when confidence is low or missing", () => {
    const low = {
      status: "OK",
      detected_symbol: "BTC/USDT",
      symbol_confidence: 0.4,
      detected_timeframe: "1h",
      timeframe_confidence: 0.5,
      observations: [],
      visible_price_labels: [],
      visible_indicators: [],
      unreadable_fields: [],
      limitations: [],
    } as VisionResult;
    assert.equal(needsSymbolConfirmation(low), true);
    assert.equal(needsTimeframeConfirmation(low), true);

    const high = {
      ...low,
      symbol_confidence: 0.95,
      timeframe_confidence: 0.9,
    } as VisionResult;
    assert.equal(needsSymbolConfirmation(high), false);
    assert.equal(needsTimeframeConfirmation(high), false);
  });

  it("builds a confirmation draft from vision estimates", () => {
    const vision = {
      status: "OK",
      detected_symbol: "APTUSDT",
      symbol_confidence: 0.92,
      detected_timeframe: "4H",
      timeframe_confidence: 0.88,
      detected_exchange: "bybit",
      observations: [],
      visible_price_labels: [],
      visible_indicators: [],
      unreadable_fields: [],
      limitations: [],
    } as VisionResult;
    const draft = draftFromVision(vision, {
      exchange: "binance",
      marketType: "spot",
      symbol: "BTC/USDT",
      timeframe: "1h",
    });
    assert.equal(draft.symbol, "APT/USDT");
    assert.equal(draft.timeframe, "4h");
    assert.equal(draft.exchange, "bybit");
    assert.equal(draft.symbolConfirmed, true);
    assert.equal(draft.timeframeConfirmed, true);
  });

  it("formats confidence and discrepancy as unavailable when missing", () => {
    assert.equal(formatConfidence(0.812), "81%");
    assert.equal(formatConfidence(null), "unavailable");
    assert.equal(formatDiscrepancyPct(1.25), "+1.25%");
    assert.equal(formatDiscrepancyPct(null), "unavailable");
  });
});
