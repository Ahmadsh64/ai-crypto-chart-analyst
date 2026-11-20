"use client";

import { useMemo } from "react";
import { useExchanges, useMarkets } from "@/hooks/use-market-data";
import { useMarketStore } from "@/stores/market-store";
import type { Timeframe } from "@/types/api";

const FALLBACK_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT"];
const TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"];

interface MarketControlsProps {
  showTimeframe?: boolean;
  compact?: boolean;
}

export function MarketControls({ showTimeframe = true, compact = false }: MarketControlsProps) {
  const {
    exchange,
    marketType,
    symbol,
    timeframe,
    searchQuery,
    setSymbol,
    setTimeframe,
  } = useMarketStore();

  const exchanges = useExchanges();
  const markets = useMarkets(exchange, marketType, searchQuery || undefined);

  const symbols = useMemo(() => {
    const fromApi = markets.data?.pairs.map((p) => p.symbol) ?? [];
    if (fromApi.length === 0) return FALLBACK_SYMBOLS;
    const defaults = FALLBACK_SYMBOLS.filter((s) => fromApi.includes(s));
    const rest = fromApi.filter((s) => !FALLBACK_SYMBOLS.includes(s)).slice(0, 40);
    return [...defaults, ...rest];
  }, [markets.data]);

  return (
    <div className={compact ? "flex flex-wrap gap-2" : "space-y-3"}>
      <label className={compact ? "block" : "block space-y-1.5"}>
        {!compact ? (
          <span className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">Symbol</span>
        ) : null}
        <select
          value={symbols.includes(symbol) ? symbol : symbols[0]}
          onChange={(e) => setSymbol(e.target.value)}
          className="h-10 w-full min-w-[140px] rounded-md border border-terminal-border bg-terminal-surface px-3 text-sm text-terminal-text outline-none focus:border-terminal-accent"
        >
          {symbols.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
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
            : `${markets.data?.count ?? 0} USDT pairs · source ${exchange}`}
        </p>
      ) : null}
    </div>
  );
}
