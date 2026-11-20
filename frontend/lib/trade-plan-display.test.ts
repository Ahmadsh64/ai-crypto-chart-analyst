import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { planStatusLabel, planStatusTone } from "@/lib/trade-plan-display";

describe("trade plan display helpers (Phase 4.3)", () => {
  it("labels plan statuses", () => {
    assert.equal(planStatusLabel("eligible"), "Eligible");
    assert.equal(planStatusLabel("blocked"), "Blocked");
    assert.equal(planStatusLabel("invalid"), "Invalid");
  });

  it("tones eligible as long-side accent", () => {
    assert.ok(planStatusTone("eligible").includes("long"));
    assert.ok(planStatusTone("blocked").includes("muted"));
  });
});
