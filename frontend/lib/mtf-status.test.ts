import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { mtfStatusLabel, resolveMtfCardStatus } from "@/lib/mtf-status";
import type { MtfTimeframeSeries } from "@/types/api";

function series(partial: Partial<MtfTimeframeSeries>): MtfTimeframeSeries {
  return {
    timeframe: "1h",
    purpose: "market_structure",
    duration_minutes: 60,
    candles_count: 100,
    closed_candles_count: 99,
    is_ready: true,
    is_stale: false,
    has_data_gaps: false,
    data_quality: "ok",
    gap_count: 0,
    ...partial,
  };
}

describe("MTF status cards (Phase 4.1)", () => {
  it("renders four ladder statuses distinctly", () => {
    const statuses = [
      resolveMtfCardStatus(series({ data_quality: "ok", is_ready: true }), {
        loading: false,
        hasError: false,
      }),
      resolveMtfCardStatus(null, { loading: true, hasError: false }),
      resolveMtfCardStatus(series({ data_quality: "stale", is_stale: true, is_ready: false }), {
        loading: false,
        hasError: false,
      }),
      resolveMtfCardStatus(
        series({ data_quality: "insufficient", is_ready: false, closed_candles_count: 2 }),
        { loading: false, hasError: false },
      ),
      resolveMtfCardStatus(series({ data_quality: "error", is_ready: false }), {
        loading: false,
        hasError: false,
      }),
    ];
    assert.deepEqual(statuses, ["ready", "loading", "stale", "insufficient", "error"]);
    assert.equal(mtfStatusLabel("insufficient"), "Insufficient Data");
  });

  it("maps gaps quality without calling it ready", () => {
    const status = resolveMtfCardStatus(
      series({ data_quality: "gaps", is_ready: true, has_data_gaps: true }),
      { loading: false, hasError: false },
    );
    assert.equal(status, "gaps");
  });
});
