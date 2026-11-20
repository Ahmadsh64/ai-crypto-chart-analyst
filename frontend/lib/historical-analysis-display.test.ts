import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { decisionLabel, decisionTone } from "@/lib/decision-display";

describe("historical analysis display (Phase 5.2.1)", () => {
  it("reuses decision tones for historical panel", () => {
    assert.equal(decisionLabel("WAIT"), "WAIT");
    assert.ok(decisionTone("LONG").includes("long"));
    assert.ok(decisionTone("NO TRADE").includes("muted") || decisionTone("NO TRADE").includes("border"));
  });
});
