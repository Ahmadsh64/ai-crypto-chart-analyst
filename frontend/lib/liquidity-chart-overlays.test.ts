import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { mapSweepMarkers } from "@/lib/liquidity-chart-overlays";
import type { LiquiditySweep } from "@/types/api";

function sweep(partial: Partial<LiquiditySweep> & Pick<LiquiditySweep, "liquidity_type" | "reaction_hint">): LiquiditySweep {
  return {
    event_key: partial.event_key ?? "liq:sweep:test",
    direction: partial.direction ?? "bullish_side",
    reaction_hint: partial.reaction_hint,
    liquidity_level_key: "lvl",
    liquidity_type: partial.liquidity_type,
    level_price: 100,
    wick_extreme: 101,
    close_price: 99,
    penetration: 0.1,
    candle_timestamp: "2024-06-01T12:00:00Z",
    confirmation_timestamp: "2024-06-01T12:00:00Z",
    confirmed: true,
    config_version: "liq-v1.1.0-balanced",
  };
}

describe("liquidity sweep markers (Phase 3.3.1)", () => {
  it("BSL bearish hint: arrowDown + BSL ↓ label agree", () => {
    const [m] = mapSweepMarkers(
      [sweep({ liquidity_type: "bsl", reaction_hint: "bearish" })],
      true,
    );
    assert.equal(m.shape, "arrowDown");
    assert.equal(m.text, "BSL ↓");
    assert.match(m.color, /#f97316|#f97/i);
  });

  it("SSL bullish hint: arrowUp + SSL ↑ label agree", () => {
    const [m] = mapSweepMarkers(
      [sweep({ liquidity_type: "ssl", reaction_hint: "bullish", direction: "bearish_side" })],
      true,
    );
    assert.equal(m.shape, "arrowUp");
    assert.equal(m.text, "SSL ↑");
  });

  it("does not use deprecated direction alone for labels", () => {
    const [m] = mapSweepMarkers(
      [sweep({ liquidity_type: "bsl", reaction_hint: "bearish", direction: "bullish_side" })],
      true,
    );
    assert.ok(!m.text.includes("bullish_side"));
    assert.ok(m.text.startsWith("BSL"));
  });
});
