import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  analyzerDescription,
  analyzerTitle,
  filterTradingPairs,
  resolveValidSymbol,
} from "./market-symbol-search";
import { chartExportFilename } from "./chart-export";
import type { TradingPair } from "@/types/api";

function pair(symbol: string, active = true): TradingPair {
  const [base, quote] = symbol.split("/");
  return {
    symbol,
    base,
    quote,
    exchange: "binance",
    market_type: "spot",
    native_symbol: symbol.replace("/", ""),
    active,
  };
}

describe("Phase 5.4.2 market symbol search", () => {
  it("uses AI Market Analyzer title", () => {
    assert.equal(analyzerTitle(), "AI Market Analyzer");
    assert.match(analyzerDescription(), /deterministic technical analysis/i);
  });

  it("filters by symbol, base, and quote", () => {
    const pairs = [pair("BTC/USDT"), pair("ETH/USDT"), pair("SOL/USDT")];
    assert.deepEqual(
      filterTradingPairs(pairs, "btc").map((p) => p.symbol),
      ["BTC/USDT"],
    );
    assert.equal(filterTradingPairs(pairs, "USDT").length, 3);
    assert.deepEqual(
      filterTradingPairs(pairs, "ETHUSDT").map((p) => p.symbol),
      ["ETH/USDT"],
    );
  });

  it("excludes inactive pairs and resolves valid selection", () => {
    const pairs = [pair("AAA/USDT", false), pair("ETH/USDT"), pair("BTC/USDT")];
    assert.equal(filterTradingPairs(pairs, "").length, 2);
    assert.equal(resolveValidSymbol(pairs, "AAA/USDT"), "BTC/USDT");
    assert.equal(resolveValidSymbol(pairs, "ETH/USDT"), "ETH/USDT");
  });

  it("builds chart export filenames from market context", () => {
    const name = chartExportFilename({
      exchange: "binance",
      marketType: "spot",
      symbol: "BTC/USDT",
      timeframe: "1h",
      capturedAt: new Date("2024-06-01T12:00:00.000Z"),
    });
    assert.match(name, /^binance_spot_BTCUSDT_1h_/);
    assert.match(name, /\.png$/);
  });
});
