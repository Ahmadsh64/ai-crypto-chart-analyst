import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  AI_ALLOWED_MIME,
  comparisonTone,
  explanationUnavailable,
  formatFileSize,
  isCurrentRequest,
  levelsFromSnapshot,
  shouldBlockDuplicateSubmit,
  validateChartScreenshotFile,
} from "@/lib/ai-analysis-display";

describe("Phase 5.4.0 AI analysis display helpers", () => {
  it("allows Analyze when not loading (duplicate prevention)", () => {
    assert.equal(shouldBlockDuplicateSubmit(false), false);
    assert.equal(shouldBlockDuplicateSubmit(true), true);
  });

  it("protects against stale responses via sequence", () => {
    assert.equal(isCurrentRequest(3, 3), true);
    assert.equal(isCurrentRequest(2, 3), false);
  });

  it("validates screenshot mime and size", () => {
    assert.equal(
      validateChartScreenshotFile({ type: "image/png", size: 100 }).ok,
      true,
    );
    assert.equal(
      validateChartScreenshotFile({ type: "image/gif", size: 100 }).ok,
      false,
    );
    assert.equal(
      validateChartScreenshotFile({
        type: "image/png",
        size: 11 * 1024 * 1024,
      }).ok,
      false,
    );
    assert.ok(AI_ALLOWED_MIME.has("image/webp"));
  });

  it("formats file size for preview UI", () => {
    assert.equal(formatFileSize(500), "500 B");
    assert.match(formatFileSize(2048), /KB/);
  });

  it("marks explainer unavailable for AI_UNAVAILABLE", () => {
    assert.equal(explanationUnavailable("AI_UNAVAILABLE"), true);
    assert.equal(explanationUnavailable("OK"), false);
    assert.equal(explanationUnavailable("INSUFFICIENT_DATA"), false);
  });

  it("reads Entry/SL/TP only from deterministic snapshot", () => {
    const levels = levelsFromSnapshot({
      entry_reference_price: 100,
      stop_loss_price: 90,
      take_profit_prices: [110, 120],
    });
    assert.equal(levels.entry, 100);
    assert.equal(levels.stopLoss, 90);
    assert.deepEqual(levels.takeProfits, [110, 120]);
  });

  it("maps comparison states", () => {
    assert.equal(comparisonTone("CONSISTENT"), "consistent");
    assert.equal(comparisonTone("CONFLICTING"), "conflict");
    assert.equal(comparisonTone("INSUFFICIENT_VISUAL_DATA"), "insufficient");
  });
});
