import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  applyPlanLineHighlights,
  buildMonitorAlerts,
  buildTradePlanMonitor,
  candleTouchesLevel,
  computeEntryDistance,
  computeSlMonitor,
  computeTpProgress,
  computeTpProximity,
  dedupeMonitorAlerts,
  detectLevelTouch,
  filterNewTouchKeys,
  freshnessAllowsAlerts,
  resolveMarketFreshness,
  resolveMonitorSide,
  touchEventKey,
  type TradePlanMonitorModel,
} from "@/lib/trade-plan-monitor";
import { marketSelectionKey, type TradePlanVisualSource } from "@/lib/trade-plan-chart-visuals";
import type { TradeChartPriceLine } from "@/lib/trade-chart-visuals";

function source(partial: Partial<TradePlanVisualSource> = {}): TradePlanVisualSource {
  return {
    exchange: "binance",
    marketType: "spot",
    symbol: "BTC/USDT",
    planId: "plan_1",
    decisionId: "dec_1",
    decision: "LONG",
    direction: "bullish",
    planStatus: "eligible",
    validationValid: true,
    entryPrice: 100,
    entryLow: 99,
    entryHigh: 101,
    priceInsideZone: false,
    stopLossPrice: 95,
    takeProfits: [
      { index: 1, label: "TP1", price: 110 },
      { index: 2, label: "TP2", price: 120 },
      { index: 3, label: "TP3", price: 130 },
    ],
    primaryRr: 2,
    analysisTimestamp: "2024-06-01T12:00:00.000Z",
    spotRestriction: null,
    marketKey: marketSelectionKey("binance", "spot", "BTC/USDT"),
    ...partial,
  };
}

describe("trade-plan-monitor distance", () => {
  it("LONG above Entry", () => {
    const d = computeEntryDistance({ currentPrice: 102, entryPrice: 100, decision: "LONG" });
    assert.equal(d.status, "ABOVE PLANNED ENTRY");
    assert.equal(d.absoluteDistance, 2);
    assert.ok(Math.abs((d.percentDistance ?? 0) - 2) < 1e-9);
  });

  it("LONG below Entry", () => {
    const d = computeEntryDistance({ currentPrice: 98, entryPrice: 100, decision: "LONG" });
    assert.equal(d.status, "BELOW PLANNED ENTRY");
    assert.equal(d.absoluteDistance, -2);
  });

  it("SHORT above Entry", () => {
    const d = computeEntryDistance({ currentPrice: 102, entryPrice: 100, decision: "SHORT" });
    assert.equal(d.status, "ABOVE PLANNED ENTRY");
  });

  it("SHORT below Entry", () => {
    const d = computeEntryDistance({ currentPrice: 98, entryPrice: 100, decision: "SHORT" });
    assert.equal(d.status, "BELOW PLANNED ENTRY");
  });

  it("Zero Entry is unavailable", () => {
    const d = computeEntryDistance({ currentPrice: 100, entryPrice: 0 });
    assert.equal(d.status, "UNAVAILABLE");
    assert.equal(d.percentDistance, null);
  });

  it("Missing market price", () => {
    const d = computeEntryDistance({ currentPrice: null, entryPrice: 100 });
    assert.equal(d.status, "UNAVAILABLE");
  });

  it("Invalid prices", () => {
    const d = computeEntryDistance({ currentPrice: Number.NaN, entryPrice: 100 });
    assert.equal(d.status, "UNAVAILABLE");
  });
});

describe("trade-plan-monitor TP progress", () => {
  it("LONG progress", () => {
    const p = computeTpProgress({
      side: "long",
      currentPrice: 105,
      entryPrice: 100,
      targetPrice: 110,
      index: 1,
    });
    assert.equal(p.progressPct, 50);
    assert.equal(p.progressLabel, "PRICE PROGRESS");
  });

  it("SHORT progress", () => {
    const p = computeTpProgress({
      side: "short",
      currentPrice: 95,
      entryPrice: 100,
      targetPrice: 90,
      index: 1,
    });
    assert.equal(p.progressPct, 50);
  });

  it("Negative progress", () => {
    const p = computeTpProgress({
      side: "long",
      currentPrice: 95,
      entryPrice: 100,
      targetPrice: 110,
      index: 1,
    });
    assert.equal(p.progressPct, -50);
  });

  it("Progress between 0% and 100%", () => {
    const p = computeTpProgress({
      side: "long",
      currentPrice: 107,
      entryPrice: 100,
      targetPrice: 110,
      index: 1,
    });
    assert.ok((p.progressPct ?? 0) > 0 && (p.progressPct ?? 0) < 100);
  });

  it("Progress beyond 100% (uncapped)", () => {
    const p = computeTpProgress({
      side: "long",
      currentPrice: 120,
      entryPrice: 100,
      targetPrice: 110,
      index: 1,
    });
    assert.equal(p.progressPct, 200);
    assert.equal(p.progressLabel, "PRICE ABOVE TARGET LEVEL");
    assert.equal(p.beyondTarget, true);
  });

  it("Missing TP levels yield empty progress list", () => {
    const m = buildTradePlanMonitor({
      source: source({ takeProfits: [] }),
      currentPrice: 105,
      freshness: "LIVE",
      planActive: true,
    });
    assert.equal(m.tpProgress.length, 0);
  });

  it("Zero denominator", () => {
    const p = computeTpProgress({
      side: "long",
      currentPrice: 100,
      entryPrice: 100,
      targetPrice: 100,
      index: 1,
    });
    assert.equal(p.progressPct, null);
    assert.equal(p.progressLabel, "UNAVAILABLE");
  });
});

describe("trade-plan-monitor stop loss", () => {
  it("Safe distance", () => {
    const s = computeSlMonitor({
      side: "long",
      currentPrice: 100,
      entryPrice: 100,
      stopLossPrice: 90,
    });
    assert.equal(s.status, "SAFE DISTANCE");
  });

  it("Approaching SL", () => {
    // risk span 10; distance 4 → 40% of span → approaching (<=50%)
    const s = computeSlMonitor({
      side: "long",
      currentPrice: 94,
      entryPrice: 100,
      stopLossPrice: 90,
    });
    assert.equal(s.status, "APPROACHING SL");
  });

  it("Near SL", () => {
    // distance 2 / span 10 = 20% → near (<=25%)
    const s = computeSlMonitor({
      side: "long",
      currentPrice: 92,
      entryPrice: 100,
      stopLossPrice: 90,
    });
    assert.equal(s.status, "NEAR SL");
  });

  it("Price at SL", () => {
    const s = computeSlMonitor({
      side: "long",
      currentPrice: 90,
      entryPrice: 100,
      stopLossPrice: 90,
    });
    assert.equal(s.status, "PRICE AT SL LEVEL");
    assert.ok(s.warningText?.includes("EXECUTION NOT VERIFIED"));
  });

  it("Price beyond SL", () => {
    const s = computeSlMonitor({
      side: "long",
      currentPrice: 88,
      entryPrice: 100,
      stopLossPrice: 90,
    });
    assert.equal(s.status, "PRICE BEYOND SL LEVEL");
  });

  it("LONG and SHORT directional handling", () => {
    const longBeyond = computeSlMonitor({
      side: "long",
      currentPrice: 89,
      entryPrice: 100,
      stopLossPrice: 90,
    });
    const shortBeyond = computeSlMonitor({
      side: "short",
      currentPrice: 111,
      entryPrice: 100,
      stopLossPrice: 110,
    });
    assert.equal(longBeyond.status, "PRICE BEYOND SL LEVEL");
    assert.equal(shortBeyond.status, "PRICE BEYOND SL LEVEL");
    assert.equal(resolveMonitorSide("SHORT", "bearish"), "short");
  });
});

describe("trade-plan-monitor price touch", () => {
  it("Forming candle touch", () => {
    const t = detectLevelTouch({
      levelKind: "entry",
      levelPrice: 100,
      formingCandle: {
        timestamp: "2024-06-01T12:00:00.000Z",
        high: 101,
        low: 99,
        isClosed: false,
      },
      nowMs: Date.parse("2024-06-01T12:01:00.000Z"),
    });
    assert.equal(t.status, "POSSIBLE TOUCH — FORMING CANDLE");
  });

  it("Closed candle touch", () => {
    const t = detectLevelTouch({
      levelKind: "tp1",
      levelPrice: 110,
      closedCandles: [
        {
          timestamp: "2024-06-01T11:00:00.000Z",
          high: 111,
          low: 109,
          isClosed: true,
        },
      ],
      nowMs: Date.parse("2024-06-01T12:00:00.000Z"),
    });
    assert.equal(t.status, "PRICE LEVEL TOUCHED — CLOSED CANDLE");
  });

  it("Candle does not touch", () => {
    assert.equal(
      candleTouchesLevel({ high: 105, low: 101 }, 100),
      false,
    );
    const t = detectLevelTouch({
      levelKind: "sl",
      levelPrice: 90,
      closedCandles: [
        { timestamp: "2024-06-01T11:00:00.000Z", high: 100, low: 95, isClosed: true },
      ],
      nowMs: Date.parse("2024-06-01T12:00:00.000Z"),
    });
    assert.equal(t.status, "NO TOUCH");
  });

  it("Missing OHLC", () => {
    const t = detectLevelTouch({
      levelKind: "entry",
      levelPrice: 100,
      formingCandle: null,
      closedCandles: [],
    });
    assert.equal(t.status, "TOUCH DATA UNAVAILABLE");
  });

  it("Duplicate touch prevention", () => {
    const touch = detectLevelTouch({
      levelKind: "entry",
      levelPrice: 100,
      closedCandles: [
        { timestamp: "2024-06-01T11:00:00.000Z", high: 101, low: 99, isClosed: true },
      ],
      nowMs: Date.parse("2024-06-01T12:00:00.000Z"),
    });
    const key = touchEventKey(touch);
    assert.ok(key);
    const first = filterNewTouchKeys([touch], new Set());
    assert.equal(first.newKeys.length, 1);
    const second = filterNewTouchKeys([touch], first.nextSeen);
    assert.equal(second.newKeys.length, 0);
  });

  it("No future candle access", () => {
    const t = detectLevelTouch({
      levelKind: "entry",
      levelPrice: 100,
      closedCandles: [
        {
          timestamp: "2024-06-01T15:00:00.000Z",
          high: 101,
          low: 99,
          isClosed: true,
        },
      ],
      nowMs: Date.parse("2024-06-01T12:00:00.000Z"),
    });
    assert.equal(t.status, "NO TOUCH");
  });
});

describe("trade-plan-monitor alerts and data quality", () => {
  it("Alert threshold behavior", () => {
    const m = buildTradePlanMonitor({
      source: source(),
      currentPrice: 92,
      freshness: "LIVE",
      planActive: true,
    });
    assert.ok(m.alerts.some((a) => a.type === "SL WARNING"));
  });

  it("Alert deduplication", () => {
    const alerts = buildMonitorAlerts({
      planId: "p1",
      symbol: "BTC/USDT",
      side: "long",
      freshness: "LIVE",
      entryDistance: computeEntryDistance({ currentPrice: 100, entryPrice: 100 }),
      stopLoss: computeSlMonitor({
        side: "long",
        currentPrice: 92,
        entryPrice: 100,
        stopLossPrice: 90,
      }),
      tpProximity: [
        computeTpProximity({
          side: "long",
          currentPrice: 109,
          entryPrice: 100,
          targetPrice: 110,
          index: 1,
        }),
      ],
    });
    const once = dedupeMonitorAlerts(alerts, new Set());
    assert.ok(once.visible.length >= 1);
    const twice = dedupeMonitorAlerts(alerts, once.nextFired);
    assert.equal(twice.visible.length, 0);
  });

  it("Alert reset after plan change (new plan ids fire again)", () => {
    const a1 = buildMonitorAlerts({
      planId: "old",
      symbol: "BTC/USDT",
      side: "long",
      freshness: "LIVE",
      entryDistance: computeEntryDistance({ currentPrice: 100.2, entryPrice: 100 }),
      stopLoss: computeSlMonitor({
        side: "long",
        currentPrice: 99,
        entryPrice: 100,
        stopLossPrice: 90,
      }),
      tpProximity: [],
    });
    const fired = dedupeMonitorAlerts(a1, new Set()).nextFired;
    const a2 = buildMonitorAlerts({
      planId: "new",
      symbol: "BTC/USDT",
      side: "long",
      freshness: "LIVE",
      entryDistance: computeEntryDistance({ currentPrice: 100.2, entryPrice: 100 }),
      stopLoss: computeSlMonitor({
        side: "long",
        currentPrice: 99,
        entryPrice: 100,
        stopLossPrice: 90,
      }),
      tpProximity: [],
    });
    const next = dedupeMonitorAlerts(a2, fired);
    assert.ok(next.visible.length >= 1);
  });

  it("No alerts with stale prices", () => {
    assert.equal(freshnessAllowsAlerts("STALE"), false);
    const m = buildTradePlanMonitor({
      source: source(),
      currentPrice: 92,
      freshness: "STALE",
      planActive: true,
    });
    assert.equal(m.alerts.length, 0);
  });

  it("No alerts with disconnected market data", () => {
    const m = buildTradePlanMonitor({
      source: source(),
      currentPrice: 92,
      freshness: "DISCONNECTED",
      planActive: true,
    });
    assert.equal(m.alerts.length, 0);
  });

  it("Symbol switch cleanup via inactive monitor", () => {
    const m = buildTradePlanMonitor({
      source: source({ marketKey: "binance:spot:ETH/USDT", symbol: "ETH/USDT" }),
      currentPrice: 2000,
      freshness: "LIVE",
      planActive: false,
    });
    assert.equal(m.active, false);
    assert.equal(m.tpProgress.length, 0);
    assert.equal(m.alerts.length, 0);
  });

  it("Freshness mapping", () => {
    assert.equal(
      resolveMarketFreshness({
        connectionStatus: "disconnected",
        processedAt: new Date().toISOString(),
        hasPrice: true,
        source: "websocket",
      }),
      "DISCONNECTED",
    );
    assert.equal(
      resolveMarketFreshness({
        connectionStatus: "connected",
        processedAt: new Date().toISOString(),
        hasPrice: true,
        source: "websocket",
      }),
      "LIVE",
    );
  });

  it("NO TRADE cleanup", () => {
    const m = buildTradePlanMonitor({
      source: source({ decision: "NO TRADE" }),
      currentPrice: 100,
      freshness: "LIVE",
      planActive: true,
    });
    assert.equal(m.active, false);
    assert.equal(m.decision, "NO TRADE");
    assert.equal(m.tpProgress.length, 0);
  });

  it("TP proximity approaching", () => {
    // distance 4 / reward 10 = 40% → APPROACHING (<=50%, >25%)
    const p = computeTpProximity({
      side: "long",
      currentPrice: 106,
      entryPrice: 100,
      targetPrice: 110,
      index: 1,
    });
    assert.equal(p.status, "APPROACHING");
  });

  it("Highlight does not duplicate line ids", () => {
    const lines: TradeChartPriceLine[] = [
      {
        id: "plan:p:entry",
        tradeId: "p",
        kind: "entry",
        price: 100,
        title: "ENTRY — 100",
        color: "#eab308",
        lineWidth: 2,
        lineStyle: 2,
      },
    ];
    const out = applyPlanLineHighlights(lines, {
      selectedLineId: "plan:p:entry",
      approachingLineIds: ["plan:p:entry"],
    });
    assert.equal(out.length, 1);
    assert.equal(out[0]!.id, "plan:p:entry");
    assert.equal(out[0]!.lineWidth, 4);
  });
});

describe("trade-plan-monitor integration smoke", () => {
  it("builds full LONG monitor model", () => {
    const m: TradePlanMonitorModel = buildTradePlanMonitor({
      source: source({ decision: "WAIT", direction: "bullish" }),
      currentPrice: 102,
      freshness: "LIVE",
      planActive: true,
      formingCandle: {
        timestamp: "2024-06-01T12:00:00.000Z",
        high: 103,
        low: 101,
        isClosed: false,
      },
      closedCandles: [],
    });
    assert.equal(m.active, true);
    assert.equal(m.side, "long");
    assert.equal(m.entryDistance.plannedLabel, true);
    assert.equal(m.tpProgress.length, 3);
    assert.ok(m.disclaimer.includes("not realized profit"));
  });
});
