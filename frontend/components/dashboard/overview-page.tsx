"use client";

import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import {
  ArrowRight,
  Bitcoin,
  CircleDollarSign,
  RefreshCw,
  ScanSearch,
  TrendingDown,
  TrendingUp,
  Wallet,
} from "lucide-react";
import { format } from "date-fns";
import { MarketChartPanel } from "@/components/charts/market-chart-panel";
import { StreamStatusBadge } from "@/components/common/stream-status";
import { StatTile } from "@/components/dashboard/stat-tile";
import { useExchanges, useTicker } from "@/hooks/use-market-data";
import { useLiveTickerSubscription } from "@/hooks/use-market-socket";
import { api } from "@/services/api";
import { tickerKey, useLiveMarketStore } from "@/stores/live-market-store";
import { useMarketStore } from "@/stores/market-store";
import { formatPct, formatPrice, formatVolume } from "@/utils/format";
import { cn } from "@/utils/cn";

const TRACKED_PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT"];

export function OverviewPage() {
  const queryClient = useQueryClient();
  const { exchange, marketType, symbol } = useMarketStore();

  useLiveTickerSubscription(exchange, marketType, TRACKED_PAIRS);

  const health = useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => api.health(signal),
    refetchInterval: 30_000,
  });

  const scannerStatus = useQuery({
    queryKey: ["opportunities", "status"],
    queryFn: ({ signal }) => api.opportunitiesStatus(signal),
    refetchInterval: 30_000,
  });

  const recentHistory = useQuery({
    queryKey: ["history", "overview-recent"],
    queryFn: ({ signal }) => api.historyAnalyses({ limit: 5, offset: 0 }, signal),
    refetchInterval: 60_000,
    retry: false,
  });

  const exchanges = useExchanges();
  const btcSeed = useTicker({ exchange, marketType, symbol: "BTC/USDT", refetchInterval: false });
  const ethSeed = useTicker({ exchange, marketType, symbol: "ETH/USDT", refetchInterval: false });
  const solSeed = useTicker({ exchange, marketType, symbol: "SOL/USDT", refetchInterval: false });

  const longSetups = scannerStatus.data?.status.long_opportunities ?? 0;
  const shortSetups = scannerStatus.data?.status.short_opportunities ?? 0;
  const historyItems = recentHistory.data?.items ?? [];
  const historyTotal = recentHistory.data?.total ?? 0;

  const btcLive = useLiveMarketStore((s) => s.tickers[tickerKey(exchange, marketType, "BTC/USDT")]);
  const ethLive = useLiveMarketStore((s) => s.tickers[tickerKey(exchange, marketType, "ETH/USDT")]);
  const solLive = useLiveMarketStore((s) => s.tickers[tickerKey(exchange, marketType, "SOL/USDT")]);
  const lastMessageAt = useLiveMarketStore((s) => s.lastMessageAt);

  const exchangeStatus =
    exchanges.data?.exchanges.find((item) => item.id === exchange)?.status ?? "unavailable";

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["ticker"] });
    void queryClient.invalidateQueries({ queryKey: ["candles"] });
    void queryClient.invalidateQueries({ queryKey: ["exchanges"] });
    void queryClient.invalidateQueries({ queryKey: ["health"] });
  };

  return (
    <div className="space-y-6 p-5 md:p-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight text-terminal-text">
            Market Overview
          </h1>
          <p className="mt-1 text-sm text-terminal-muted">
            {exchange.toUpperCase()} · {marketType.replaceAll("_", " ")} · Active pair {symbol}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <StreamStatusBadge exchange={exchange} />
            <p className="text-[11px] text-terminal-muted">
              REST reachability:{" "}
              <span
                className={cn(
                  "uppercase",
                  exchangeStatus === "ok" && "text-terminal-long",
                  exchangeStatus === "degraded" && "text-amber-400",
                  exchangeStatus === "unavailable" && "text-terminal-short",
                )}
              >
                {exchangeStatus}
              </span>
              {lastMessageAt ? ` · WS tick ${format(lastMessageAt, "HH:mm:ss")}` : ""}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={refresh}
            className="inline-flex items-center gap-2 rounded-md border border-terminal-border bg-terminal-surface px-3 py-2 text-sm text-terminal-text hover:border-terminal-accent"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh REST
          </button>
          <Link
            href="/chart-analyzer"
            className="inline-flex items-center gap-2 rounded-md bg-terminal-accent px-4 py-2 text-sm font-medium text-terminal-bg transition hover:bg-terminal-accent/90"
          >
            Open AI Market Analyzer
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </div>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
        <LivePriceTile
          label="BTC Price"
          live={btcLive}
          seedLast={btcSeed.data?.ticker.last}
          seedChange={btcSeed.data?.ticker.change_pct_24h}
          seedVolume={btcSeed.data?.ticker.volume_24h}
          icon={<Bitcoin className="h-4 w-4 text-terminal-muted" />}
        />
        <LivePriceTile
          label="ETH Price"
          live={ethLive}
          seedLast={ethSeed.data?.ticker.last}
          seedChange={ethSeed.data?.ticker.change_pct_24h}
          seedVolume={ethSeed.data?.ticker.volume_24h}
          icon={<CircleDollarSign className="h-4 w-4 text-terminal-muted" />}
        />
        <LivePriceTile
          label="SOL Price"
          live={solLive}
          seedLast={solSeed.data?.ticker.last}
          seedChange={solSeed.data?.ticker.change_pct_24h}
          seedVolume={solSeed.data?.ticker.volume_24h}
        />
        <StatTile
          label="Bullish Setups"
          value={String(longSetups)}
          hint="From Market Opportunities scanner"
          tone="long"
          icon={<TrendingUp className="h-4 w-4 text-terminal-long" />}
        />
        <StatTile
          label="Bearish Setups"
          value={String(shortSetups)}
          hint="From Market Opportunities scanner"
          tone="short"
          icon={<TrendingDown className="h-4 w-4 text-terminal-short" />}
        />
        <StatTile
          label="Saved Analyses"
          value={recentHistory.isError ? "—" : String(historyTotal)}
          hint={
            recentHistory.isError
              ? "History unavailable (persistence optional)"
              : "Persisted Analyze runs"
          }
          icon={<Wallet className="h-4 w-4 text-terminal-muted" />}
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <MarketChartPanel
          exchange={exchange}
          marketType={marketType}
          symbol="BTC/USDT"
          timeframe="1h"
          heightClass="h-[320px]"
          limit={180}
        />
        <MarketChartPanel
          exchange={exchange}
          marketType={marketType}
          symbol="ETH/USDT"
          timeframe="1h"
          heightClass="h-[320px]"
          limit={180}
        />
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-lg border border-terminal-border bg-terminal-panel p-4 lg:col-span-1">
          <h2 className="text-sm font-medium text-terminal-text">System Status</h2>
          <p className="mt-1 text-xs text-terminal-muted">
            Live health from {api.baseUrl}/api/v1/health
          </p>
          {health.isLoading ? (
            <p className="mt-4 text-sm text-terminal-muted">Checking API…</p>
          ) : health.isError ? (
            <div className="mt-4 rounded-md border border-terminal-short/40 bg-terminal-short/10 p-3 text-sm text-terminal-short">
              Backend unreachable. Start FastAPI on port 8000.
            </div>
          ) : (
            <ul className="mt-4 space-y-2">
              {health.data?.components.map((component) => (
                <li
                  key={component.name}
                  className="flex items-start justify-between gap-3 rounded-md border border-terminal-border/80 bg-terminal-surface/50 px-3 py-2"
                >
                  <div>
                    <p className="text-sm capitalize text-terminal-text">{component.name}</p>
                    {component.detail ? (
                      <p className="text-[11px] text-terminal-muted">{component.detail}</p>
                    ) : null}
                  </div>
                  <span
                    className={cn(
                      "shrink-0 text-[11px] uppercase tracking-wider",
                      component.status === "ok" && "text-terminal-long",
                      component.status === "degraded" && "text-amber-400",
                      component.status === "unavailable" && "text-terminal-short",
                    )}
                  >
                    {component.status}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-lg border border-terminal-border bg-terminal-panel p-4 lg:col-span-1">
          <h2 className="text-sm font-medium text-terminal-text">Watchlist</h2>
          <p className="mt-1 text-xs text-terminal-muted">WebSocket tickers · 24h change/volume</p>
          <Watchlist exchange={exchange} marketType={marketType} />
        </div>

        <div className="rounded-lg border border-terminal-border bg-terminal-panel p-4 lg:col-span-1">
          <div className="flex items-center gap-2">
            <ScanSearch className="h-4 w-4 text-terminal-accent" />
            <h2 className="text-sm font-medium text-terminal-text">Recent AI Analyses</h2>
          </div>
          <p className="mt-1 text-xs text-terminal-muted">
            From History · soft-persist on Analyze
          </p>
          {recentHistory.isLoading ? (
            <p className="mt-4 text-sm text-terminal-muted">Loading…</p>
          ) : recentHistory.isError ? (
            <div className="mt-4 rounded-md border border-dashed border-terminal-border px-4 py-8 text-center">
              <p className="text-sm text-terminal-muted">
                Persistence offline or unavailable.
              </p>
              <Link
                href="/chart-analyzer"
                className="mt-3 inline-block text-sm text-terminal-accent hover:underline"
              >
                Open AI Market Analyzer
              </Link>
            </div>
          ) : historyItems.length === 0 ? (
            <div className="mt-4 flex flex-col items-center justify-center rounded-md border border-dashed border-terminal-border px-4 py-8 text-center">
              <p className="text-sm text-terminal-muted">No saved analyses yet</p>
              <Link
                href="/chart-analyzer"
                className="mt-3 text-sm text-terminal-accent hover:underline"
              >
                Run Analyze
              </Link>
            </div>
          ) : (
            <ul className="mt-4 divide-y divide-terminal-border">
              {historyItems.map((item) => (
                <li key={item.analysis_run_id} className="py-2.5">
                  <Link
                    href={`/history?run=${encodeURIComponent(item.analysis_run_id)}`}
                    className="block hover:opacity-90"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium text-terminal-text">
                        {item.symbol}
                      </span>
                      <span className="shrink-0 text-[11px] uppercase tracking-wider text-terminal-muted">
                        {item.decision}
                      </span>
                    </div>
                    <p className="mt-0.5 text-[11px] text-terminal-muted">
                      {format(new Date(item.analysis_timestamp), "MMM d · HH:mm")}
                    </p>
                  </Link>
                </li>
              ))}
              <li className="pt-3">
                <Link href="/history" className="text-sm text-terminal-accent hover:underline">
                  View all history
                </Link>
              </li>
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}

function LivePriceTile({
  label,
  live,
  seedLast,
  seedChange,
  seedVolume,
  icon,
}: {
  label: string;
  live?: {
    last: number;
    changePct24h?: number | null;
    volume24h?: number | null;
    direction: "up" | "down" | "flat";
    source: string;
  };
  seedLast?: number;
  seedChange?: number | null;
  seedVolume?: number | null;
  icon?: ReactNode;
}) {
  const last = live?.last ?? seedLast;
  const change = live?.changePct24h ?? seedChange;
  const volume = live?.volume24h ?? seedVolume;
  return (
    <StatTile
      label={label}
      value={formatPrice(last)}
      hint={`${formatPct(change)} · vol ${formatVolume(volume)}${live ? " · LIVE" : " · REST"}`}
      tone={change != null && change >= 0 ? "long" : "short"}
      icon={icon}
    />
  );
}

function Watchlist({
  exchange,
  marketType,
}: {
  exchange: "binance" | "bybit";
  marketType: "spot" | "usdt_m_futures" | "linear_perpetual";
}) {
  return (
    <ul className="mt-4 divide-y divide-terminal-border">
      {TRACKED_PAIRS.map((pair) => (
        <WatchlistRow key={pair} exchange={exchange} marketType={marketType} symbol={pair} />
      ))}
    </ul>
  );
}

function WatchlistRow({
  exchange,
  marketType,
  symbol,
}: {
  exchange: "binance" | "bybit";
  marketType: "spot" | "usdt_m_futures" | "linear_perpetual";
  symbol: string;
}) {
  const seed = useTicker({ exchange, marketType, symbol, refetchInterval: false });
  const live = useLiveMarketStore((s) => s.tickers[tickerKey(exchange, marketType, symbol)]);
  const last = live?.last ?? seed.data?.ticker.last;
  const change = live?.changePct24h ?? seed.data?.ticker.change_pct_24h;
  const volume = live?.volume24h ?? seed.data?.ticker.volume_24h;
  return (
    <li className="flex items-center justify-between py-2.5 text-sm">
      <span className="font-medium text-terminal-text">{symbol}</span>
      <div className="text-right">
        <p
          className={cn(
            "font-mono",
            live?.direction === "up" && "text-terminal-long",
            live?.direction === "down" && "text-terminal-short",
            (!live || live.direction === "flat") && "text-terminal-text",
          )}
        >
          {formatPrice(last)}
        </p>
        <p
          className={cn(
            "text-[11px]",
            change != null && change >= 0 ? "text-terminal-long" : "text-terminal-short",
          )}
        >
          {formatPct(change)} · {formatVolume(volume)}
        </p>
      </div>
    </li>
  );
}
