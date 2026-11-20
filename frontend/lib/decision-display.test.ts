import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { decisionLabel, decisionTone } from "@/lib/decision-display";

describe("decision display helpers (Phase 4.4)", () => {
  it("labels decisions", () => {
    assert.equal(decisionLabel("LONG"), "LONG");
    assert.equal(decisionLabel("NO TRADE"), "NO TRADE");
  });

  it("tones LONG and SHORT distinctly", () => {
    assert.ok(decisionTone("LONG").includes("long"));
    assert.ok(decisionTone("SHORT").includes("short"));
    assert.ok(decisionTone("WAIT").includes("amber"));
  });
});
