"use client";

import { MarketChartPanel } from "@/components/charts/market-chart-panel";
import { StreamStatusBadge } from "@/components/common/stream-status";
import { MarketControls } from "@/components/trading/market-controls";
import { useTicker } from "@/hooks/use-market-data";
import { tickerKey, useLiveMarketStore } from "@/stores/live-market-store";
import { useMarketStore } from "@/stores/market-store";
import { formatPct, formatPrice, formatVolume } from "@/utils/format";
import { cn } from "@/utils/cn";

export default function LiveMarketPage() {
  const { exchange, marketType, symbol, timeframe } = useMarketStore();
  // REST seed once; live values come from WebSocket.
  const seed = useTicker({ exchange, marketType, symbol, refetchInterval: false });
  const live = useLiveMarketStore((s) => s.tickers[tickerKey(exchange, marketType, symbol)]);

  const last = live?.last ?? seed.data?.ticker.last;
  const change = live?.changePct24h ?? seed.data?.ticker.change_pct_24h;
  const high = live?.high24h ?? seed.data?.ticker.high_24h;
  const volume = live?.volume24h ?? seed.data?.ticker.volume_24h;

  return (
    <div className="space-y-4 p-4 md:p-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold text-terminal-text">Live Market</h1>
          <p className="mt-1 text-sm text-terminal-muted">
            Real-time {exchange} ({marketType.replaceAll("_", " ")}) via WebSocket — analysis only
          </p>
          <div className="mt-2">
            <StreamStatusBadge exchange={exchange} />
          </div>
        </div>
        <div className="rounded-lg border border-terminal-border bg-terminal-panel p-3">
          <MarketControls compact />
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Last"
          value={formatPrice(last)}
          tone={live?.direction === "up" ? "long" : live?.direction === "down" ? "short" : "neutral"}
        />
        <Stat
          label="24h Change"
          value={formatPct(change)}
          tone={change != null && change >= 0 ? "long" : "short"}
        />
        <Stat label="24h High" value={formatPrice(high)} />
        <Stat label="24h Volume" value={formatVolume(volume)} />
      </div>

      <MarketChartPanel
        exchange={exchange}
        marketType={marketType}
        symbol={symbol}
        timeframe={timeframe}
        heightClass="h-[520px]"
      />
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "long" | "short";
}) {
  return (
    <div className="rounded-lg border border-terminal-border bg-terminal-panel px-4 py-3">
      <p className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">{label}</p>
      <p
        className={cn(
          "mt-1 font-mono text-lg font-semibold",
          tone === "long" && "text-terminal-long",
          tone === "short" && "text-terminal-short",
          tone === "neutral" && "text-terminal-text",
        )}
      >
        {value}
      </p>
    </div>
  );
}
