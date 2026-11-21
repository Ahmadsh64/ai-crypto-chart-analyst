"use client";

import { useEffect, useMemo } from "react";
import { SymbolSearchSelect } from "@/components/trading/symbol-search-select";
import { useExchanges, useMarkets } from "@/hooks/use-market-data";
import { FALLBACK_SYMBOLS, resolveValidSymbol } from "@/lib/market-symbol-search";
import { useMarketStore } from "@/stores/market-store";
import type { Timeframe, TradingPair } from "@/types/api";

const TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"];

interface MarketControlsProps {
  showTimeframe?: boolean;
  compact?: boolean;
}

export function MarketControls({ showTimeframe = true, compact = false }: MarketControlsProps) {
  const { exchange, marketType, symbol, timeframe, setSymbol, setTimeframe } = useMarketStore();

  const exchanges = useExchanges();
  // Load full catalog (server-cached). Local combobox handles search + virtualization.
  const markets = useMarkets(exchange, marketType);

  const pairs: TradingPair[] = useMemo(() => {
    const fromApi = markets.data?.pairs ?? [];
    if (fromApi.length > 0) return fromApi.filter((p) => p.active !== false);
    return FALLBACK_SYMBOLS.map((s) => {
      const [base, quote] = s.split("/");
      return {
        symbol: s,
        base: base || s,
        quote: quote || "USDT",
        exchange,
        market_type: marketType,
        native_symbol: s.replace("/", ""),
        active: true,
      } satisfies TradingPair;
    });
  }, [markets.data, exchange, marketType]);

  useEffect(() => {
    if (markets.isLoading || markets.isError) return;
    if (pairs.length === 0) return;
    const next = resolveValidSymbol(pairs, symbol);
    if (next !== symbol) setSymbol(next);
  }, [pairs, symbol, setSymbol, markets.isLoading, markets.isError, exchange, marketType]);

  return (
    <div className={compact ? "flex flex-wrap gap-2" : "space-y-3"}>
      <label className={compact ? "block min-w-[180px] flex-1" : "block space-y-1.5"}>
        {!compact ? (
          <span className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
            Symbol
          </span>
        ) : null}
        <SymbolSearchSelect
          pairs={pairs}
          value={symbol}
          onChange={setSymbol}
          loading={markets.isLoading}
          error={
            markets.isError
              ? (markets.error as Error)?.message || "Failed to load markets"
              : null
          }
        />
      </label>

      {showTimeframe ? (
        <label className={compact ? "block" : "block space-y-1.5"}>
          {!compact ? (
            <span className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
              Timeframe
            </span>
          ) : null}
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value as Timeframe)}
            className="h-10 w-full min-w-[100px] rounded-md border border-terminal-border bg-terminal-surface px-3 text-sm text-terminal-text outline-none focus:border-terminal-accent"
          >
            {TIMEFRAMES.map((tf) => (
              <option key={tf} value={tf}>
                {tf}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      {exchanges.data ? (
        <p className="text-[11px] text-terminal-muted">
          {markets.isLoading
            ? "Loading pairs…"
            : `${markets.data?.total ?? markets.data?.count ?? pairs.length} active pairs · ${exchange}`}
        </p>
      ) : null}
    </div>
  );
}
