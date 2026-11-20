import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { mapObFvgZones } from "@/lib/ob-fvg-chart-overlays";
import type { FairValueGap, OrderBlock } from "@/types/api";

function ob(partial: Partial<OrderBlock> & Pick<OrderBlock, "side" | "event_key">): OrderBlock {
  return {
    event_key: partial.event_key,
    side: partial.side,
    status: partial.status ?? "active",
    zone_low: partial.zone_low ?? 100,
    zone_high: partial.zone_high ?? 110,
    boundary_method: "full_candle",
    source_candle_timestamp: partial.source_candle_timestamp ?? "2024-06-01T10:00:00Z",
    source_structure_kind: partial.source_structure_kind ?? "bos",
    source_structure_event_key: partial.source_structure_event_key ?? "bos:bullish:1",
    structure_candle_timestamp: "2024-06-01T11:00:00Z",
    detection_timestamp: partial.detection_timestamp ?? "2024-06-01T11:00:00Z",
    config_version: "obfvg-v1.0.0-balanced",
    confirmed: true,
    segment_start: partial.segment_start ?? "2024-06-01T10:00:00Z",
    segment_end: partial.segment_end ?? "2024-06-01T14:00:00Z",
    segment_active: true,
  };
}

function fvg(partial: Partial<FairValueGap> & Pick<FairValueGap, "side" | "event_key">): FairValueGap {
  return {
    event_key: partial.event_key,
    side: partial.side,
    status: partial.status ?? "active",
    zone_low: partial.zone_low ?? 200,
    zone_high: partial.zone_high ?? 210,
    gap_size: 10,
    candle1_timestamp: "2024-06-01T09:00:00Z",
    candle2_timestamp: "2024-06-01T10:00:00Z",
    candle3_timestamp: "2024-06-01T11:00:00Z",
    detection_timestamp: partial.detection_timestamp ?? "2024-06-01T11:00:00Z",
    max_fill_pct: partial.max_fill_pct ?? 0,
    config_version: "obfvg-v1.0.0-balanced",
    confirmed: true,
    segment_start: partial.segment_start ?? "2024-06-01T09:00:00Z",
    segment_end: partial.segment_end ?? "2024-06-01T14:00:00Z",
    segment_active: true,
  };
}

describe("OB/FVG chart overlays (Phase 3.4)", () => {
  it("maps bullish OB to green zone with exact prices", () => {
    const zones = mapObFvgZones({
      bullishObs: [ob({ event_key: "ob:bull:1", side: "bullish", zone_low: 95.5, zone_high: 101.25 })],
      bearishObs: [],
      bullishFvgs: [],
      bearishFvgs: [],
      showBullishOb: true,
      showBearishOb: false,
      showBullishFvg: false,
      showBearishFvg: false,
      recentOnly: false,
      fallbackEndIso: "2024-06-01T15:00:00Z",
    });
    assert.equal(zones.length, 1);
    assert.equal(zones[0].priceLow, 95.5);
    assert.equal(zones[0].priceHigh, 101.25);
    assert.ok(zones[0].fillColor.includes("34, 197, 94"));
  });

  it("respects independent toggles and recent limit", () => {
    const zones = mapObFvgZones({
      bullishObs: [
        ob({ event_key: "ob:a", side: "bullish", detection_timestamp: "2024-06-01T12:00:00Z" }),
        ob({ event_key: "ob:b", side: "bullish", detection_timestamp: "2024-06-01T11:00:00Z" }),
      ],
      bearishObs: [ob({ event_key: "ob:c", side: "bearish" })],
      bullishFvgs: [fvg({ event_key: "fvg:a", side: "bullish" })],
      bearishFvgs: [fvg({ event_key: "fvg:b", side: "bearish" })],
      showBullishOb: true,
      showBearishOb: false,
      showBullishFvg: true,
      showBearishFvg: false,
      recentOnly: true,
      recentLimit: 1,
      fallbackEndIso: null,
    });
    assert.equal(zones.length, 2);
    assert.equal(zones[0].id, "ob:a");
    assert.equal(zones[1].id, "fvg:a");
  });
});
