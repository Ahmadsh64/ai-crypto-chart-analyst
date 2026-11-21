import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  consistencyLabel,
  extractPlannedLevels,
  hasAnyPlannedLevel,
  historyErrorMessage,
  historyPageCount,
  isIncompleteConsistency,
} from "./history-display";
import type { AnalysisHistoryDetail } from "@/types/api";

function baseDetail(
  overrides: Partial<AnalysisHistoryDetail> = {},
): AnalysisHistoryDetail {
  return {
    analysis_run_id: "ar_test",
    snapshot_id: "11111111-1111-1111-1111-111111111111",
    consistency_status: "ALIGNED",
    snapshot_kind: "live_analyze",
    exchange: "binance",
    market_type: "spot",
    symbol: "BTC/USDT",
    timeframe: "1h",
    analysis_timestamp: "2024-06-01T12:00:00Z",
    decision: "LONG",
    configuration_versions: {},
    snapshot_schema_version: "analysis-snapshot-db-v1",
    entry_reference_price: "100.0",
    entry_low: "99.0",
    entry_high: "101.0",
    stop_loss_price: "90.0",
    take_profit_prices: ["110.0", "120.0", "130.0"],
    primary_rr: "2.0",
    content_hash: "abc",
    created_at: "2024-06-01T12:00:01Z",
    levels_note:
      "Stored planned Entry/SL/TP are analytical levels from Analyze time — not exchange fills.",
    snapshot_payload: {},
    ...overrides,
  };
}

describe("history-display", () => {
  it("labels consistency statuses", () => {
    assert.equal(consistencyLabel("ALIGNED"), "Aligned");
    assert.equal(consistencyLabel("DUAL_FETCH_DIVERGED"), "Diverged");
    assert.equal(isIncompleteConsistency("DUAL_FETCH_DIVERGED"), true);
    assert.equal(isIncompleteConsistency("ALIGNED"), false);
  });

  it("extracts planned levels and omits empty TPs", () => {
    const levels = extractPlannedLevels(
      baseDetail({ take_profit_prices: ["110", "", "130"] }),
    );
    assert.equal(levels.entry, "100.0");
    assert.equal(levels.stopLoss, "90.0");
    assert.deepEqual(levels.takeProfits, ["110", "130"]);
    assert.equal(hasAnyPlannedLevel(levels), true);
    assert.match(levels.note, /not exchange fills/i);
  });

  it("reports empty planned levels when absent", () => {
    const levels = extractPlannedLevels(
      baseDetail({
        entry_reference_price: null,
        entry_low: null,
        entry_high: null,
        stop_loss_price: null,
        take_profit_prices: [],
        primary_rr: null,
      }),
    );
    assert.equal(hasAnyPlannedLevel(levels), false);
  });

  it("computes page count and error messages", () => {
    assert.equal(historyPageCount(0, 20), 1);
    assert.equal(historyPageCount(41, 20), 3);
    assert.equal(
      historyErrorMessage({ message: "DATABASE_UNAVAILABLE: down" }),
      "DATABASE_UNAVAILABLE: down",
    );
  });
});
