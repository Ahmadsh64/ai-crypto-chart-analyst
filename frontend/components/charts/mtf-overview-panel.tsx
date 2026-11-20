"use client";

import { format } from "date-fns";
import { useMultiTimeframe } from "@/hooks/use-market-data";
import { useLiveMultiTimeframeSubscription } from "@/hooks/use-market-socket";
import { mtfKey, useLiveMarketStore } from "@/stores/live-market-store";
import {
  mtfStatusLabel,
  mtfStatusTone,
  resolveMtfCardStatus,
  type MtfCardStatus,
} from "@/lib/mtf-status";
import { formatPrice } from "@/utils/format";
import { cn } from "@/utils/cn";
import type { ExchangeId, MarketType, MtfTimeframeSeries, Timeframe } from "@/types/api";

const LADDER: Timeframe[] = ["4h", "1h", "15m", "5m"];

const PURPOSE_LABEL: Record<string, string> = {
  htf_context: "HTF context",
  market_structure: "Structure",
  setup: "Setup",
  entry_confirmation: "Entry confirm",
};

interface MtfOverviewPanelProps {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
}

export function MtfOverviewPanel({ exchange, marketType, symbol }: MtfOverviewPanelProps) {
  useLiveMultiTimeframeSubscription(exchange, marketType, symbol, true);

  const query = useMultiTimeframe({ exchange, marketType, symbol });
  const connectionStatus = useLiveMarketStore((s) => s.connectionStatus);
  const live = useLiveMarketStore((s) => s.multiTimeframe[mtfKey(exchange, marketType, symbol)]);

  const snapshot = live?.snapshot ?? query.data?.snapshot;
  const rows = live?.timeframes ?? query.data?.timeframes ?? snapshot?.timeframes ?? [];
  const byTf = new Map(rows.map((r) => [r.timeframe, r]));
  const source = live ? "live" : query.isLoading ? "loading" : "rest";

  return (
    <div className="space-y-3 rounded-lg border border-terminal-border bg-terminal-panel p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
            Multi-Timeframe
          </h3>
          <p className="mt-1 text-[11px] text-terminal-muted">
            {source === "loading"
              ? "Loading…"
              : source === "live"
                ? "Live · orchestration"
                : "REST seed"}
            {snapshot?.config_version ? ` · ${snapshot.config_version}` : ""}
          </p>
        </div>
        <div className="text-right text-[11px] text-terminal-muted">
          <p className="capitalize">WS {connectionStatus}</p>
          <p className="mt-0.5 font-mono uppercase">
            {snapshot?.overall_status ?? (query.isError ? "error" : "—")}
          </p>
        </div>
      </div>

      {query.isError ? (
        <p className="text-[11px] text-terminal-short">
          {(query.error as Error).message || "Failed to load multi-timeframe data"}
        </p>
      ) : null}

      <div className="grid grid-cols-2 gap-2 xl:grid-cols-4">
        {LADDER.map((tf) => (
          <TimeframeCard
            key={tf}
            timeframe={tf}
            series={byTf.get(tf)}
            loading={query.isLoading && !live}
            hasError={query.isError && !live}
            connectionStatus={connectionStatus}
          />
        ))}
      </div>

      <p className="text-[10px] leading-relaxed text-terminal-muted">
        Data readiness only — no trade signals. Timeframes close independently; a closed 5m
        candle does not confirm the parent 15m bar.
      </p>
    </div>
  );
}

function TimeframeCard({
  timeframe,
  series,
  loading,
  hasError,
  connectionStatus,
}: {
  timeframe: Timeframe;
  series?: MtfTimeframeSeries;
  loading: boolean;
  hasError: boolean;
  connectionStatus: string;
}) {
  const status: MtfCardStatus = resolveMtfCardStatus(series, { loading, hasError });
  const closedAt = series?.latest_closed_candle_time
    ? format(new Date(series.latest_closed_candle_time), "MMM d HH:mm")
    : "—";

  return (
    <div className="rounded border border-terminal-border/70 bg-terminal-surface/40 p-2.5">
      <div className="flex items-center justify-between gap-1">
        <p className="font-mono text-sm font-semibold uppercase text-terminal-text">
          {timeframe}
        </p>
        <span
          className={cn(
            "rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide",
            mtfStatusTone(status),
          )}
        >
          {mtfStatusLabel(status)}
        </span>
      </div>
      <p className="mt-1 text-[10px] text-terminal-muted">
        {PURPOSE_LABEL[series?.purpose ?? ""] ?? series?.purpose ?? "—"}
      </p>
      <p className="mt-2 font-mono text-base text-terminal-text">
        {series?.latest_price != null ? formatPrice(series.latest_price) : "—"}
      </p>
      <dl className="mt-2 space-y-1 text-[10px] text-terminal-muted">
        <div className="flex justify-between gap-2">
          <dt>Closed</dt>
          <dd className="font-mono text-terminal-text">{closedAt} UTC</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Quality</dt>
          <dd className="font-mono uppercase text-terminal-text">
            {series?.data_quality ?? "—"}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Candles</dt>
          <dd className="font-mono text-terminal-text">
            {series ? `${series.closed_candles_count}/${series.candles_count}` : "—"}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Stream</dt>
          <dd className="font-mono capitalize text-terminal-text">{connectionStatus}</dd>
        </div>
      </dl>
      {series?.status_detail ? (
        <p className="mt-2 line-clamp-2 text-[10px] text-terminal-short">{series.status_detail}</p>
      ) : null}
    </div>
  );
}
