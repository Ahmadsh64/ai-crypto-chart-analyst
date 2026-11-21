import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  analyzerHref,
  opportunityStatusLabel,
  opportunityStatusTone,
} from "@/lib/opportunities-display";

describe("opportunities display (Phase 5.5)", () => {
  it("labels READY distinctly from WAITING", () => {
    assert.equal(opportunityStatusLabel("READY"), "Ready");
    assert.equal(opportunityStatusLabel("WAITING"), "Waiting confirmation");
    assert.ok(opportunityStatusTone("READY").includes("long"));
    assert.ok(!opportunityStatusTone("WAITING").includes("long"));
  });

  it("builds Open Full Analysis href without inventing levels", () => {
    const href = analyzerHref({
      exchange: "binance",
      marketType: "spot",
      symbol: "BTC/USDT",
      timeframe: "1h",
    });
    assert.ok(href.startsWith("/chart-analyzer?"));
    assert.ok(href.includes("symbol=BTC"));
    assert.ok(href.includes("from=opportunities"));
  });
});
