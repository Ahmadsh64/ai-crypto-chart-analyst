"use client";

import { format } from "date-fns";
import { useTicker } from "@/hooks/use-market-data";
import { tickerKey, useLiveMarketStore } from "@/stores/live-market-store";
import {
  connectionBadgeLabel,
  formatPairLabel,
  pairBaseName,
  resolveConnectionBadge,
  type LiveConnectionBadge,
} from "@/lib/analyzer-dashboard-display";
import { formatPct, formatPrice } from "@/utils/format";
import { cn } from "@/utils/cn";
import type { AnalysisMode } from "@/lib/analysis-mode";
import type { ExchangeId, MarketType, Timeframe } from "@/types/api";

interface AnalyzerMarketOverviewProps {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  timeframe: Timeframe;
  analysisMode: AnalysisMode;
  /** Optional screenshot-observed price (upload mode only). */
  screenshotObservedPrice?: number | null;
  verifiedPriceTimestamp?: string | null;
  verifiedPriceSource?: string | null;
  loading?: boolean;
  error?: string | null;
}

function badgeTone(badge: LiveConnectionBadge): string {
  switch (badge) {
    case "live":
      return "border-terminal-long/50 bg-terminal-long/10 text-terminal-long";
    case "rest":
      return "border-terminal-accent/40 bg-terminal-accent/10 text-terminal-accent";
    case "stale":
      return "border-amber-400/50 bg-amber-400/10 text-amber-200";
    case "connecting":
      return "border-terminal-border text-terminal-muted";
    default:
      return "border-terminal-short/40 bg-terminal-short/10 text-terminal-short";
  }
}

export function AnalyzerMarketOverview({
  exchange,
  marketType,
  symbol,
  timeframe,
  analysisMode,
  screenshotObservedPrice,
  verifiedPriceTimestamp,
  verifiedPriceSource,
  loading,
  error,
}: AnalyzerMarketOverviewProps) {
  const connectionStatus = useLiveMarketStore((s) => s.connectionStatus);
  const liveTicker = useLiveMarketStore(
    (s) => s.tickers[tickerKey(exchange, marketType, symbol)],
  );
  const seed = useTicker({ exchange, marketType, symbol, refetchInterval: false });

  const last =
    liveTicker?.last ?? seed.data?.ticker.last ?? null;
  const change = liveTicker?.changePct24h ?? seed.data?.ticker.change_pct_24h ?? null;
  const updatedAt =
    liveTicker?.processedAt ??
    seed.data?.ticker.updated_at ??
    seed.data?.last_updated ??
    verifiedPriceTimestamp ??
    null;
  const sourceLabel =
    liveTicker?.source === "websocket"
      ? `${exchange} websocket`
      : verifiedPriceSource || seed.data?.data_source || `${exchange} REST`;

  const hasLiveTicker = liveTicker?.source === "websocket";
  const badge = resolveConnectionBadge(connectionStatus, hasLiveTicker);
  const showLiveWord = badge === "live";
  const priceLoading = last == null && (seed.isLoading || seed.isFetching || Boolean(loading));

  const base = pairBaseName(symbol);
  const pair = formatPairLabel(symbol);

  return (
    <section
      className="rounded-lg border border-terminal-border bg-terminal-panel p-4"
      data-testid="market-overview"
      aria-label="Market overview"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <p className="text-[11px] uppercase tracking-[0.16em] text-terminal-muted">
            Market overview
          </p>
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h2 className="font-display text-2xl font-semibold tracking-tight text-terminal-text md:text-3xl">
              {base}
            </h2>
            <span className="font-mono text-lg text-terminal-accent md:text-xl">{pair}</span>
          </div>
          <p className="text-xs capitalize text-terminal-muted">
            {exchange} · {marketType.replaceAll("_", " ")} · {timeframe}
            {analysisMode === "UPLOADED_IMAGE" ? " · Uploaded chart mode" : " · Live market mode"}
          </p>
        </div>

        <div className="text-right">
          {priceLoading ? (
            <p className="font-mono text-3xl text-terminal-muted md:text-4xl">Loading…</p>
          ) : (
            <p
              className={cn(
                "font-mono text-3xl font-semibold tabular-nums tracking-tight md:text-4xl",
                liveTicker?.direction === "up" && "text-terminal-long",
                liveTicker?.direction === "down" && "text-terminal-short",
                (!liveTicker || liveTicker.direction === "flat") && "text-terminal-text",
              )}
              data-testid="live-price"
            >
              {formatPrice(last)}
            </p>
          )}
          <p
            className={cn(
              "mt-1 text-sm font-medium",
              change != null && change >= 0 ? "text-terminal-long" : "text-terminal-short",
            )}
          >
            24h {formatPct(change)}
          </p>
          <div className="mt-2 flex flex-wrap items-center justify-end gap-2">
            <span
              className={cn(
                "rounded border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide",
                badgeTone(badge),
              )}
              data-testid="connection-badge"
            >
              {showLiveWord ? "Live" : connectionBadgeLabel(badge)}
            </span>
            <span className="text-[10px] text-terminal-muted">
              {updatedAt
                ? `Updated ${format(new Date(updatedAt), "HH:mm:ss")}`
                : "No price timestamp"}
            </span>
          </div>
          <p className="mt-1 text-[10px] text-terminal-muted">Source: {sourceLabel}</p>
        </div>
      </div>

      {error ? (
        <p className="mt-3 text-xs text-terminal-short" data-testid="overview-error">
          {error}
        </p>
      ) : null}

      {analysisMode === "UPLOADED_IMAGE" ? (
        <div className="mt-3 grid gap-2 rounded-md border border-terminal-border/70 bg-terminal-surface/50 p-3 sm:grid-cols-2">
          <div>
            <p className="text-[10px] uppercase tracking-wide text-terminal-muted">
              Screenshot-observed price
            </p>
            <p className="font-mono text-sm text-terminal-muted">
              {screenshotObservedPrice != null
                ? formatPrice(screenshotObservedPrice)
                : "Unavailable"}
            </p>
            <p className="text-[10px] text-terminal-muted">OCR estimate only</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wide text-terminal-muted">
              Verified exchange price
            </p>
            <p className="font-mono text-sm text-terminal-accent">{formatPrice(last)}</p>
            <p className="text-[10px] text-terminal-muted">
              Deterministic analysis uses verified OHLCV only
            </p>
          </div>
        </div>
      ) : null}
    </section>
  );
}
