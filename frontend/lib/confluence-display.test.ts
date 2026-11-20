import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { assessmentLabel, assessmentTone, categoryLabel } from "@/lib/confluence-display";

describe("confluence display helpers (Phase 4.2)", () => {
  it("maps preliminary assessments without trade language", () => {
    assert.equal(assessmentLabel("bullish_confluence"), "Bullish confluence");
    assert.equal(assessmentLabel("bearish_confluence"), "Bearish confluence");
    assert.equal(assessmentLabel("mixed"), "Mixed");
    assert.ok(!assessmentLabel("mixed").toLowerCase().includes("long"));
    assert.ok(!assessmentLabel("mixed").toLowerCase().includes("short"));
  });

  it("uses distinct tones and category labels", () => {
    assert.ok(assessmentTone("bullish_confluence").includes("long"));
    assert.ok(assessmentTone("bearish_confluence").includes("short"));
    assert.equal(categoryLabel("htf_context"), "4H context");
    assert.equal(categoryLabel("ob_fvg"), "OB / FVG");
  });
});
