import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { UTCTimestamp } from "lightweight-charts";
import type {
  DecisionResponse,
  TradePlanResponse,
  TradePlanTarget,
} from "@/types/api";
import {
  DEFAULT_TRADE_PLAN_CHART_TOGGLES,
  buildTradePlanChartVisuals,
  marketSelectionKey,
  resolvePlanChartStatus,
  resolveTradePlanVisualSource,
  setAllTradePlanLevelsVisible,
  shouldAcceptPlanVisualUpdate,
  type TradePlanVisualSource,
} from "@/lib/trade-plan-chart-visuals";

function target(
  index: number,
  price: number,
  partial: Partial<TradePlanTarget> = {},
): TradePlanTarget {
  return {
    index,
    label: `TP${index}`,
    price,
    source: "test",
    source_event_key: null,
    distance: Math.abs(price - 100),
    distance_pct: 1,
    risk_reward_ratio: index,
    explanation: "test",
    ...partial,
  };
}

function baseSource(partial: Partial<TradePlanVisualSource> = {}): TradePlanVisualSource {
  return {
    exchange: "binance",
    marketType: "spot",
    symbol: "BTC/USDT",
    planId: "plan_1",
    decisionId: "dec_1",
    decision: "WAIT",
    direction: "bullish",
    planStatus: "eligible",
    validationValid: true,
    entryPrice: 100,
    entryLow: 99,
    entryHigh: 101,
    priceInsideZone: true,
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

const ZONE_START = 1_700_000_000 as UTCTimestamp;
const ZONE_END = 1_700_086_400 as UTCTimestamp;

describe("trade-plan-chart-visuals", () => {
  it("valid LONG plan produces entry/sl/tp line definitions", () => {
    const visuals = buildTradePlanChartVisuals({
      source: baseSource({ decision: "LONG", direction: "bullish" }),
      zoneStart: ZONE_START,
      zoneEnd: ZONE_END,
    });
    assert.equal(visuals.status, "LONG SETUP CONFIRMED");
    assert.equal(visuals.priceLines.length, 5);
    assert.ok(visuals.priceLines.some((l) => l.kind === "entry" && l.price === 100));
    assert.ok(visuals.priceLines.some((l) => l.kind === "sl" && l.price === 95));
    assert.equal(visuals.priceLines.filter((l) => l.kind === "tp").length, 3);
    assert.ok(visuals.priceLines.every((l) => l.title.includes("—")));
    assert.ok(!visuals.priceLines.some((l) => /fill|executed/i.test(l.title)));
  });

  it("valid SHORT plan produces correct line definitions", () => {
    const visuals = buildTradePlanChartVisuals({
      source: baseSource({
        decision: "SHORT",
        direction: "bearish",
        entryPrice: 100,
        stopLossPrice: 105,
        takeProfits: [
          { index: 1, label: "TP1", price: 90 },
          { index: 2, label: "TP2", price: 80 },
        ],
      }),
      zoneStart: ZONE_START,
      zoneEnd: ZONE_END,
    });
    assert.equal(visuals.status, "SHORT SETUP CONFIRMED");
    assert.equal(visuals.priceLines.filter((l) => l.kind === "tp").length, 2);
    assert.ok(visuals.zones.some((z) => z.id.includes("risk")));
    assert.ok(visuals.zones.some((z) => z.id.includes("reward")));
  });

  it("WAIT with valid plan displays planned levels", () => {
    const visuals = buildTradePlanChartVisuals({
      source: baseSource({ decision: "WAIT" }),
    });
    assert.equal(visuals.status, "WAITING FOR CONFIRMATION");
    assert.ok(visuals.priceLines.some((l) => l.title.startsWith("PLANNED ENTRY")));
    assert.ok(visuals.priceLines.some((l) => l.title.startsWith("PLANNED STOP LOSS")));
    assert.ok(visuals.priceLines.some((l) => l.title.startsWith("PLANNED TP1")));
  });

  it("LONG with valid plan displays confirmed (non-fill) levels", () => {
    const visuals = buildTradePlanChartVisuals({
      source: baseSource({ decision: "LONG" }),
    });
    assert.equal(visuals.status, "LONG SETUP CONFIRMED");
    assert.ok(visuals.priceLines.some((l) => l.title.startsWith("ENTRY —")));
    assert.ok(!visuals.priceLines.some((l) => l.title.startsWith("PLANNED ENTRY")));
  });

  it("SHORT with valid plan displays confirmed levels", () => {
    const visuals = buildTradePlanChartVisuals({
      source: baseSource({ decision: "SHORT", direction: "bearish" }),
    });
    assert.equal(visuals.status, "SHORT SETUP CONFIRMED");
    assert.ok(visuals.priceLines.length > 0);
  });

  it("NO TRADE clears all plan levels", () => {
    const visuals = buildTradePlanChartVisuals({
      source: baseSource({ decision: "NO TRADE" }),
    });
    assert.equal(visuals.status, "NO TRADE");
    assert.equal(visuals.priceLines.length, 0);
    assert.equal(visuals.zones.length, 0);
    assert.equal(visuals.legend.entry, null);
  });

  it("missing plan clears stale levels", () => {
    const visuals = buildTradePlanChartVisuals({ source: null });
    assert.equal(visuals.status, "PLAN UNAVAILABLE");
    assert.equal(visuals.priceLines.length, 0);
  });

  it("missing TP3 does not generate a TP3 line", () => {
    const visuals = buildTradePlanChartVisuals({
      source: baseSource({
        takeProfits: [
          { index: 1, label: "TP1", price: 110 },
          { index: 2, label: "TP2", price: 120 },
        ],
      }),
    });
    assert.equal(visuals.priceLines.filter((l) => l.kind === "tp").length, 2);
    assert.ok(!visuals.priceLines.some((l) => l.tpIndex === 3));
  });

  it("missing SL does not generate an SL line", () => {
    const visuals = buildTradePlanChartVisuals({
      source: baseSource({ stopLossPrice: null }),
    });
    assert.ok(!visuals.priceLines.some((l) => l.kind === "sl"));
    assert.ok(visuals.priceLines.some((l) => l.kind === "entry"));
  });

  it("symbol / market key mismatch clears incompatible levels", () => {
    const visuals = buildTradePlanChartVisuals({
      source: baseSource(),
      expectedMarketKey: marketSelectionKey("binance", "spot", "ETH/USDT"),
    });
    assert.equal(visuals.priceLines.length, 0);
    assert.equal(visuals.status, "PLAN UNAVAILABLE");
  });

  it("duplicate levels are not created", () => {
    const source = baseSource({
      takeProfits: [
        { index: 1, label: "TP1", price: 110 },
        { index: 1, label: "TP1-dup", price: 111 },
      ],
    });
    // resolve path dedupes by index; direct source with duplicate ids still deduped by line id
    const visuals = buildTradePlanChartVisuals({ source });
    const ids = visuals.priceLines.map((l) => l.id);
    assert.equal(new Set(ids).size, ids.length);
  });

  it("visibility toggles work independently", () => {
    const visuals = buildTradePlanChartVisuals({
      source: baseSource({ decision: "LONG" }),
      toggles: { ...DEFAULT_TRADE_PLAN_CHART_TOGGLES, entry: false, tp2: false },
      zoneStart: ZONE_START,
      zoneEnd: ZONE_END,
    });
    assert.ok(!visuals.priceLines.some((l) => l.kind === "entry"));
    assert.ok(visuals.priceLines.some((l) => l.kind === "sl"));
    assert.ok(visuals.priceLines.some((l) => l.tpIndex === 1));
    assert.ok(!visuals.priceLines.some((l) => l.tpIndex === 2));
    assert.ok(visuals.priceLines.some((l) => l.tpIndex === 3));
  });

  it("Show/Hide All works correctly", () => {
    const hidden = buildTradePlanChartVisuals({
      source: baseSource({ decision: "LONG" }),
      toggles: setAllTradePlanLevelsVisible(false),
      zoneStart: ZONE_START,
      zoneEnd: ZONE_END,
    });
    assert.equal(hidden.priceLines.length, 0);
    assert.equal(hidden.zones.length, 0);

    const shown = buildTradePlanChartVisuals({
      source: baseSource({ decision: "LONG" }),
      toggles: setAllTradePlanLevelsVisible(true),
      zoneStart: ZONE_START,
      zoneEnd: ZONE_END,
    });
    assert.ok(shown.priceLines.length >= 4);
    assert.ok(shown.zones.length >= 1);
  });

  it("live plan updates replace old prices", () => {
    const first = buildTradePlanChartVisuals({
      source: baseSource({ entryPrice: 100, analysisTimestamp: "2024-06-01T12:00:00.000Z" }),
    });
    const second = buildTradePlanChartVisuals({
      source: baseSource({ entryPrice: 101, analysisTimestamp: "2024-06-01T12:01:00.000Z" }),
      acceptedAnalysisTimestamp: "2024-06-01T12:00:00.000Z",
      expectedMarketKey: first.legend.planId
        ? marketSelectionKey("binance", "spot", "BTC/USDT")
        : marketSelectionKey("binance", "spot", "BTC/USDT"),
    });
    assert.equal(second.applied, true);
    assert.equal(second.priceLines.find((l) => l.kind === "entry")?.price, 101);
  });

  it("outdated responses cannot overwrite newer plans", () => {
    const stale = buildTradePlanChartVisuals({
      source: baseSource({
        entryPrice: 99,
        analysisTimestamp: "2024-06-01T11:00:00.000Z",
      }),
      acceptedAnalysisTimestamp: "2024-06-01T12:00:00.000Z",
      expectedMarketKey: marketSelectionKey("binance", "spot", "BTC/USDT"),
    });
    assert.equal(stale.applied, false);
    assert.equal(stale.priceLines.length, 0);
  });

  it("chart cleanup path: invalid plan yields empty lines", () => {
    const visuals = buildTradePlanChartVisuals({
      source: baseSource({ planStatus: "invalid", validationValid: false }),
    });
    assert.equal(visuals.status, "PLAN UNAVAILABLE");
    assert.equal(visuals.priceLines.length, 0);
    assert.equal(visuals.zones.length, 0);
  });

  it("resolveTradePlanVisualSource prefers live over REST", () => {
    const restPlan = {
      exchange: "binance",
      symbol: "BTC/USDT",
      market_type: "spot",
      plan_id: "rest_plan",
      plan_status: "eligible",
      direction: "bullish",
      entry: {
        entry_low: 99,
        entry_high: 101,
        entry_reference_price: 100,
        entry_type: "zone",
        entry_source: "ob",
        source_event_key: "e",
        timeframe: "15m",
        entry_explanation: "x",
        price_inside_zone: true,
      },
      stop_loss: {
        stop_loss_price: 95,
        stop_loss_source: "swing",
        stop_loss_distance: 5,
        stop_loss_distance_pct: 5,
        buffer_value: 0,
        invalidation_explanation: "x",
      },
      take_profit_targets: [target(1, 110)],
      validation: { is_valid: true, validation_errors: [], warnings: [], blocking_reasons: [] },
      eligibility: { is_eligible: true, direction: "bullish", blocking_reasons: [] },
      supporting_evidence_ids: [],
      conflict_ids: [],
      invalidation_conditions: [],
      explanations: [],
      configuration_version: "v1",
      analysis_timestamp: "2024-06-01T12:00:00.000Z",
      data_quality: {
        overall: "ok",
        is_analysis_complete: true,
        timeframes_used: [],
        timeframes_unavailable: [],
        timeframes_stale: [],
        limitations: [],
        atr_available: true,
      },
      analysis_only_disclaimer: "analysis only",
      config: {},
      data_source: "rest",
      metadata: {},
    } as TradePlanResponse;

    const restDecision = {
      exchange: "binance",
      symbol: "BTC/USDT",
      market_type: "spot",
      decision_id: "rest_dec",
      decision: "WAIT",
      decision_reason: "await",
      lifecycle: "awaiting_confirmation",
      confluence_scores: { bullish_score: 1, bearish_score: 0 },
      entry_confirmation: {
        status: "pending",
        is_confirmed: false,
        explanation: "x",
      },
      take_profit_prices: [110],
      supporting_evidence: [],
      blocking_conditions: [],
      conflict_ids: [],
      data_quality: {
        overall: "ok",
        is_analysis_complete: true,
        timeframes_used: [],
        timeframes_unavailable: [],
        timeframes_stale: [],
        limitations: [],
      },
      analysis_only_disclaimer: "analysis only",
      configuration_version: "v1",
      analysis_timestamp: "2024-06-01T12:00:00.000Z",
      config: {},
      data_source: "rest",
      metadata: {},
    } as DecisionResponse;

    const source = resolveTradePlanVisualSource({
      exchange: "binance",
      marketType: "spot",
      symbol: "BTC/USDT",
      restPlan,
      restDecision,
      livePlan: {
        exchange: "binance",
        marketType: "spot",
        symbol: "BTC/USDT",
        planId: "live_plan",
        direction: "bullish",
        planStatus: "eligible",
        entry: {
          entry_low: 100,
          entry_high: 102,
          entry_reference_price: 101.5,
          entry_type: "zone",
          entry_source: "ob",
          source_event_key: "e",
          timeframe: "15m",
          entry_explanation: "x",
          price_inside_zone: true,
        },
        stopLoss: {
          stop_loss_price: 96,
          stop_loss_source: "swing",
          stop_loss_distance: 5,
          stop_loss_distance_pct: 5,
          buffer_value: 0,
          invalidation_explanation: "x",
        },
        takeProfitTargets: [target(1, 112)],
        validation: {
          is_valid: true,
          validation_errors: [],
          warnings: [],
          blocking_reasons: [],
        },
        eligibility: { is_eligible: true, direction: "bullish", blocking_reasons: [] },
        invalidationConditions: [],
        explanations: [],
        configurationVersion: "v1",
        analysisTimestamp: "2024-06-01T12:05:00.000Z",
        dataQuality: {
          overall: "ok",
          is_analysis_complete: true,
          timeframes_used: [],
          timeframes_unavailable: [],
          timeframes_stale: [],
          limitations: [],
          atr_available: true,
        },
        analysisOnlyDisclaimer: "analysis only",
        processedAt: "2024-06-01T12:05:00.000Z",
      },
      liveDecision: {
        exchange: "binance",
        marketType: "spot",
        symbol: "BTC/USDT",
        decisionId: "live_dec",
        decision: "LONG",
        decisionReason: "confirmed",
        direction: "bullish",
        lifecycle: "entry_confirmed",
        confluenceScores: { bullish_score: 2, bearish_score: 0 },
        entryConfirmation: {
          status: "confirmed",
          is_confirmed: true,
          explanation: "x",
        },
        takeProfitPrices: [112],
        supportingEvidence: [],
        blockingConditions: [],
        conflictIds: [],
        dataQuality: {
          overall: "ok",
          is_analysis_complete: true,
          timeframes_used: [],
          timeframes_unavailable: [],
          timeframes_stale: [],
          limitations: [],
        },
        analysisOnlyDisclaimer: "analysis only",
        configurationVersion: "v1",
        analysisTimestamp: "2024-06-01T12:05:00.000Z",
        processedAt: "2024-06-01T12:05:00.000Z",
      },
    });

    assert.equal(source.planId, "live_plan");
    assert.equal(source.decision, "LONG");
    assert.equal(source.entryPrice, 101.5);
    assert.equal(resolvePlanChartStatus(source), "LONG SETUP CONFIRMED");
  });

  it("shouldAcceptPlanVisualUpdate rejects strictly older stamps", () => {
    assert.equal(
      shouldAcceptPlanVisualUpdate(
        {
          marketKey: "binance:spot:BTC/USDT",
          analysisTimestamp: "2024-06-01T11:00:00.000Z",
        },
        {
          marketKey: "binance:spot:BTC/USDT",
          analysisTimestamp: "2024-06-01T12:00:00.000Z",
        },
      ),
      false,
    );
    assert.equal(
      shouldAcceptPlanVisualUpdate(
        {
          marketKey: "binance:spot:ETH/USDT",
          analysisTimestamp: "2024-06-01T11:00:00.000Z",
        },
        {
          marketKey: "binance:spot:BTC/USDT",
          analysisTimestamp: "2024-06-01T12:00:00.000Z",
        },
      ),
      true,
    );
  });
});
