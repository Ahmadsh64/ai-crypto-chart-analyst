import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildAnalyzerTradeLevels,
  connectionBadgeLabel,
  decisionAllowsTradeLevels,
  formatPairLabel,
  pairBaseName,
  resolveConnectionBadge,
} from "@/lib/analyzer-dashboard-display";
import type { DecisionResponse, TradePlanResponse } from "@/types/api";

describe("analyzer dashboard display", () => {
  it("formats pair and base names", () => {
    assert.equal(pairBaseName("BTC/USDT"), "BTC");
    assert.equal(formatPairLabel("ETH/USDT"), "ETH/USDT");
  });

  it("shows Live badge only when connected with live ticker", () => {
    assert.equal(resolveConnectionBadge("connected", true), "live");
    assert.equal(resolveConnectionBadge("connected", false), "rest");
    assert.equal(resolveConnectionBadge("stale", true), "stale");
    assert.equal(resolveConnectionBadge("disconnected", true), "disconnected");
    assert.equal(connectionBadgeLabel("live"), "Live");
    assert.notEqual(connectionBadgeLabel("stale"), "Live");
  });

  it("allows trade levels only for LONG/SHORT", () => {
    assert.equal(decisionAllowsTradeLevels("LONG"), true);
    assert.equal(decisionAllowsTradeLevels("SHORT"), true);
    assert.equal(decisionAllowsTradeLevels("WAIT"), false);
    assert.equal(decisionAllowsTradeLevels("NO TRADE"), false);
  });

  it("WAIT clears fabricated entry and TPs", () => {
    const model = buildAnalyzerTradeLevels({
      snapshotDecision: "WAIT",
      snapshotEntryRef: 100,
      snapshotStop: 90,
      snapshotTps: [110, 120, 130],
      livePrice: 105,
    });
    assert.equal(model.showTradeLevels, false);
    assert.equal(model.entry.available, false);
    assert.equal(model.stopLoss.available, false);
    assert.equal(model.takeProfits[0].available, false);
    assert.equal(model.takeProfits[2].available, false);
    assert.equal(model.livePrice, 105);
  });

  it("NO TRADE clears fabricated levels", () => {
    const model = buildAnalyzerTradeLevels({
      snapshotDecision: "NO TRADE",
      snapshotEntryRef: 50,
      snapshotTps: [60],
    });
    assert.equal(model.showTradeLevels, false);
    assert.equal(model.entry.price, null);
  });

  it("LONG shows engine TPs and marks missing slots unavailable", () => {
    const tradePlan = {
      take_profit_targets: [
        {
          index: 1,
          label: "TP1",
          price: 110,
          source: "engine",
          distance: 10,
          distance_pct: 1,
          risk_reward_ratio: 1,
          explanation: "x",
        },
        {
          index: 2,
          label: "TP2",
          price: 120,
          source: "engine",
          distance: 20,
          distance_pct: 2,
          risk_reward_ratio: 2,
          explanation: "x",
        },
      ],
      stop_loss: {
        stop_loss_price: 90,
        stop_loss_source: "swing",
        stop_loss_distance: 10,
        stop_loss_distance_pct: 1,
        buffer_value: 0,
        invalidation_explanation: "Break below swing",
      },
      entry: {
        entry_low: 98,
        entry_high: 102,
        entry_reference_price: 100,
        entry_type: "zone",
        entry_source: "ob",
        source_event_key: "k",
        timeframe: "1h",
        entry_explanation: "e",
        price_inside_zone: true,
      },
      invalidation_conditions: ["Break below SL"],
      risk: { primary_rr: 2, risk_distance: 10, risk_distance_pct: 1, reward_distances: [], minimum_required_rr: 1.5, meets_minimum_rr: true },
    } as unknown as TradePlanResponse;

    const decision = {
      decision: "LONG",
      take_profit_prices: [110, 120],
      stop_loss_price: 90,
      data_quality: { current_price: 101 },
    } as unknown as DecisionResponse;

    const model = buildAnalyzerTradeLevels({
      decision,
      tradePlan,
      livePrice: 101.5,
    });
    assert.equal(model.showTradeLevels, true);
    assert.equal(model.entry.available, true);
    assert.equal(model.entry.price, 100);
    assert.deepEqual(model.entryZone, { low: 98, high: 102 });
    assert.equal(model.stopLoss.price, 90);
    assert.equal(model.takeProfits[0].price, 110);
    assert.equal(model.takeProfits[1].price, 120);
    assert.equal(model.takeProfits[2].available, false);
    assert.equal(model.invalidation.available, true);
    assert.equal(model.livePrice, 101.5);
  });

  it("SHORT with three TPs fills all slots", () => {
    const model = buildAnalyzerTradeLevels({
      snapshotDecision: "SHORT",
      snapshotEntryRef: 200,
      snapshotStop: 210,
      snapshotTps: [190, 180, 170],
    });
    assert.equal(model.showTradeLevels, true);
    assert.equal(model.takeProfits.every((t) => t.available), true);
  });

  it("missing stop loss stays unavailable without inventing", () => {
    const model = buildAnalyzerTradeLevels({
      snapshotDecision: "LONG",
      snapshotEntryRef: 100,
      snapshotTps: [110],
    });
    assert.equal(model.stopLoss.available, false);
    assert.equal(model.stopLoss.price, null);
    assert.equal(model.takeProfits[0].available, true);
    assert.equal(model.takeProfits[1].available, false);
  });
});
