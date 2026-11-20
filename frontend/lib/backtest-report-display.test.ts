import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  REPORT_DISCLAIMER,
  REPORT_EXPORT_ACTIONS,
  formatReportMetric,
  formatReportNumber,
  formatReportUtc,
  pnlTone,
} from "./backtest-report-display";

describe("backtest report display (Phase 5.2.6)", () => {
  it("shows N/A for unavailable metrics instead of zero", () => {
    assert.equal(
      formatReportMetric({ value: null, availability: "unavailable" }),
      "N/A",
    );
    assert.equal(
      formatReportMetric({ value: 0, availability: "unavailable" }),
      "N/A",
    );
  });

  it("shows infinity for infinite profit factor", () => {
    assert.equal(
      formatReportMetric({ value: null, availability: "infinite" }),
      "∞",
    );
  });

  it("formats available numbers without inventing zeros for null", () => {
    assert.equal(formatReportNumber(null), "N/A");
    assert.equal(formatReportNumber("1.234567"), "1.23457");
  });

  it("keeps UTC labels and disclaimer wording", () => {
    assert.equal(
      formatReportUtc("2024-01-01T00:00:00+00:00"),
      "2024-01-01T00:00:00Z",
    );
    assert.match(REPORT_DISCLAIMER, /NOT REAL ORDERS/);
    assert.match(REPORT_DISCLAIMER, /NOT FINANCIAL ADVICE/);
  });

  it("exposes working export action labels", () => {
    assert.ok(REPORT_EXPORT_ACTIONS.some((a) => a.kind === "pdf"));
    assert.ok(REPORT_EXPORT_ACTIONS.some((a) => a.kind === "trades"));
  });

  it("tones PnL only when numeric and non-zero", () => {
    assert.equal(pnlTone(null), "muted");
    assert.equal(pnlTone(0), "muted");
    assert.equal(pnlTone("1.5"), "long");
    assert.equal(pnlTone("-2"), "short");
  });
});
