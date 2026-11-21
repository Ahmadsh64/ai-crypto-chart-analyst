/** Client-side market symbol search helpers (Phase 5.4.2). */

import type { TradingPair } from "@/types/api";

export const PAGE_SIZE = 40;
export const FALLBACK_SYMBOLS = [
  "BTC/USDT",
  "ETH/USDT",
  "SOL/USDT",
  "BNB/USDT",
  "XRP/USDT",
  "DOGE/USDT",
];

export function normalizeSymbolQuery(raw: string): string {
  return raw.trim().toUpperCase().replace(/-/g, "/").replace(/\s+/g, "");
}

export function filterTradingPairs(pairs: TradingPair[], query: string): TradingPair[] {
  const needle = normalizeSymbolQuery(query);
  if (!needle) return pairs.filter((p) => p.active !== false);
  const compact = needle.replace(/\//g, "");
  return pairs.filter((p) => {
    if (p.active === false) return false;
    const symbol = p.symbol.toUpperCase();
    const native = (p.native_symbol || "").toUpperCase();
    const base = (p.base || "").toUpperCase();
    const quote = (p.quote || "").toUpperCase();
    return (
      symbol.includes(needle) ||
      symbol.replace(/\//g, "").includes(compact) ||
      native.includes(compact) ||
      native.includes(needle) ||
      base === needle ||
      base === compact ||
      base.startsWith(compact) ||
      quote === needle ||
      quote === compact
    );
  });
}

/** Prefer keeping the current symbol; otherwise BTC/USDT; otherwise first active pair. */
export function resolveValidSymbol(
  pairs: TradingPair[],
  current: string,
  fallbacks: string[] = FALLBACK_SYMBOLS,
): string {
  const active = pairs.filter((p) => p.active !== false);
  if (active.some((p) => p.symbol === current)) return current;
  for (const fb of fallbacks) {
    if (active.some((p) => p.symbol === fb)) return fb;
  }
  return active[0]?.symbol || current || "BTC/USDT";
}

export function analyzerTitle(): string {
  return "AI Market Analyzer";
}

export function analyzerDescription(): string {
  return "Live market intelligence powered by deterministic technical analysis and AI visual interpretation.";
}
