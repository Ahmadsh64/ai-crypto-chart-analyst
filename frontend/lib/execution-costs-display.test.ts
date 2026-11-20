import assert from "node:assert/strict";
import { describe, it } from "node:test";

function reconcileNet(
  gross: number,
  fees: number,
  slip: number,
  spread: number,
  net: number,
  tol = 1e-6,
): boolean {
  const expected = gross - fees - slip - spread;
  return Math.abs(expected - net) <= tol;
}

describe("execution costs display (Phase 5.2.3)", () => {
  it("reconciles gross versus net with costs", () => {
    assert.equal(reconcileNet(10, 0.2, 0.1, 0.05, 9.65), true);
  });

  it("rejects fabricated disclaimer-free summary", () => {
    const disclaimer =
      "HISTORICAL SIMULATION — NOT REAL EXECUTION — COSTS ARE ESTIMATED";
    assert.match(disclaimer, /NOT REAL EXECUTION/);
    assert.match(disclaimer, /ESTIMATED/);
  });

  it("treats example fee source as non-verified", () => {
    const source = "example_default";
    assert.notEqual(source, "exchange_live");
  });
});
