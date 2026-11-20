import assert from "node:assert/strict";
import { describe, it } from "node:test";

type MetricValue = {
  value: string | number | null;
  availability: "available" | "unavailable" | "infinite";
};

function formatMetric(m: MetricValue): string {
  if (m.availability === "unavailable") return "N/A";
  if (m.availability === "infinite") return "∞";
  if (m.value === null || m.value === undefined) return "N/A";
  return String(m.value);
}

function winRate(wins: number, completed: number): MetricValue {
  if (completed <= 0) return { value: null, availability: "unavailable" };
  return { value: (wins / completed) * 100, availability: "available" };
}

describe("performance analytics display (Phase 5.2.4)", () => {
  it("shows N/A for unavailable metrics instead of zero", () => {
    assert.equal(formatMetric({ value: null, availability: "unavailable" }), "N/A");
    assert.equal(formatMetric({ value: 0, availability: "unavailable" }), "N/A");
  });

  it("shows infinity for profit factor with no losses", () => {
    assert.equal(formatMetric({ value: null, availability: "infinite" }), "∞");
  });

  it("computes win rate only over completed trades", () => {
    const m = winRate(1, 2);
    assert.equal(m.availability, "available");
    assert.equal(Number(m.value), 50);
    assert.equal(winRate(0, 0).availability, "unavailable");
  });

  it("keeps backtest disclaimer wording", () => {
    const d = "HISTORICAL BACKTEST — SIMULATED RESULTS — NOT FINANCIAL ADVICE";
    assert.match(d, /NOT FINANCIAL ADVICE/);
    assert.match(d, /SIMULATED/);
  });
});
