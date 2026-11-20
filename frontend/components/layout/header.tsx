"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import { Search, User } from "lucide-react";
import { StreamStatusBadge } from "@/components/common/stream-status";
import { useMarketSocketBridge } from "@/hooks/use-market-socket";
import { api } from "@/services/api";
import { useMarketStore } from "@/stores/market-store";
import { cn } from "@/utils/cn";
import type { ExchangeId, MarketType } from "@/types/api";

const EXCHANGES: { id: ExchangeId; label: string }[] = [
  { id: "binance", label: "Binance" },
  { id: "bybit", label: "Bybit" },
];

const MARKET_TYPES: Record<ExchangeId, { id: MarketType; label: string }[]> = {
  binance: [
    { id: "spot", label: "Spot" },
    { id: "usdt_m_futures", label: "USDT-M Futures" },
  ],
  bybit: [
    { id: "spot", label: "Spot" },
    { id: "linear_perpetual", label: "Linear Perp" },
  ],
};

function StatusDot({ status }: { status?: string }) {
  const color =
    status === "ok"
      ? "bg-terminal-long"
      : status === "degraded"
        ? "bg-amber-400"
        : "bg-terminal-short";

  return <span className={cn("inline-block h-2 w-2 rounded-full", color)} />;
}

export function Header() {
  useMarketSocketBridge();
  const { exchange, marketType, searchQuery, setExchange, setMarketType, setSearchQuery } =
    useMarketStore();
  const [now, setNow] = useState<Date | null>(null);

  const health = useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => api.health(signal),
    refetchInterval: 30_000,
  });

  useEffect(() => {
    setNow(new Date());
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const markets = MARKET_TYPES[exchange];

  return (
    <header className="flex h-16 shrink-0 items-center gap-4 border-b border-terminal-border bg-terminal-panel/80 px-5 backdrop-blur">
      <div className="flex items-center gap-2">
        <label className="sr-only" htmlFor="exchange">
          Exchange
        </label>
        <select
          id="exchange"
          value={exchange}
          onChange={(e) => {
            const next = e.target.value as ExchangeId;
            setExchange(next);
            const first = MARKET_TYPES[next][0]?.id;
            if (first) setMarketType(first);
          }}
          className="h-9 rounded-md border border-terminal-border bg-terminal-surface px-3 text-sm text-terminal-text outline-none focus:border-terminal-accent"
        >
          {EXCHANGES.map((ex) => (
            <option key={ex.id} value={ex.id}>
              {ex.label}
            </option>
          ))}
        </select>

        <label className="sr-only" htmlFor="market-type">
          Market type
        </label>
        <select
          id="market-type"
          value={marketType}
          onChange={(e) => setMarketType(e.target.value as MarketType)}
          className="h-9 rounded-md border border-terminal-border bg-terminal-surface px-3 text-sm text-terminal-text outline-none focus:border-terminal-accent"
        >
          {markets.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      <div className="relative min-w-0 flex-1 max-w-md">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-terminal-muted" />
        <input
          type="search"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search pairs (BTC/USDT, ETH/USDT…)"
          className="h-9 w-full rounded-md border border-terminal-border bg-terminal-surface pl-9 pr-3 text-sm text-terminal-text placeholder:text-terminal-muted outline-none focus:border-terminal-accent"
        />
      </div>

      <div className="ml-auto flex items-center gap-4">
        <div className="hidden lg:block">
          <StreamStatusBadge exchange={exchange} />
        </div>
        <div className="hidden items-center gap-2 text-xs text-terminal-muted sm:flex">
          <StatusDot status={health.data?.status ?? (health.isError ? "unavailable" : undefined)} />
          <span>
            {health.isLoading
              ? "Connecting…"
              : health.isError
                ? "API offline"
                : `API ${health.data?.status}`}
          </span>
        </div>

        <time
          dateTime={now?.toISOString()}
          className="hidden font-mono text-xs text-terminal-muted md:block"
        >
          {now ? format(now, "yyyy-MM-dd HH:mm:ss") : "--"}
        </time>

        <button
          type="button"
          className="flex h-9 w-9 items-center justify-center rounded-md border border-terminal-border bg-terminal-surface text-terminal-muted hover:text-terminal-text"
          aria-label="User profile"
        >
          <User className="h-4 w-4" />
        </button>
      </div>
    </header>
  );
}
