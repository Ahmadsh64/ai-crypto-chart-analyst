"use client";

import { useMemo, useState } from "react";
import { useIndicators } from "@/hooks/use-market-data";
import { useLiveIndicatorSubscription } from "@/hooks/use-market-socket";
import { indicatorKey, useLiveMarketStore } from "@/stores/live-market-store";
import { formatPrice, formatVolume } from "@/utils/format";
import { cn } from "@/utils/cn";
import type {
  ExchangeId,
  IndicatorId,
  IndicatorLatest,
  MarketType,
  Timeframe,
} from "@/types/api";

const PANEL_DEFAULTS: IndicatorId[] = [
  "ema_9",
  "ema_20",
  "ema_50",
  "ema_200",
  "rsi_14",
  "macd",
  "atr_14",
  "bollinger",
  "relative_volume",
  "volume_sma_20",
  "obv",
];

const CHART_OVERLAY_OPTIONS: { id: IndicatorId; label: string }[] = [
  { id: "ema_9", label: "EMA 9" },
  { id: "ema_20", label: "EMA 20" },
  { id: "ema_50", label: "EMA 50" },
  { id: "ema_200", label: "EMA 200" },
  { id: "bollinger", label: "Bollinger" },
];

interface IndicatorsPanelProps {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  timeframe: Timeframe;
  chartOverlays: IndicatorId[];
  onChartOverlaysChange: (ids: IndicatorId[]) => void;
}

export function IndicatorsPanel({
  exchange,
  marketType,
  symbol,
  timeframe,
  chartOverlays,
  onChartOverlaysChange,
}: IndicatorsPanelProps) {
  const [enabled, setEnabled] = useState<IndicatorId[]>(PANEL_DEFAULTS);

  useLiveIndicatorSubscription(exchange, marketType, symbol, timeframe, enabled, true);

  const query = useIndicators({
    exchange,
    marketType,
    symbol,
    timeframe,
    indicators: enabled.join(","),
    includeForming: false,
    includeSeries: false,
  });

  const live = useLiveMarketStore(
    (s) => s.indicators[indicatorKey(exchange, marketType, symbol, timeframe)],
  );

  const latest = useMemo(() => {
    const rest = query.data?.indicators ?? {};
    const liveMap = live?.indicators ?? {};
    const merged: Record<string, IndicatorLatest> = { ...rest };
    for (const [key, value] of Object.entries(liveMap)) {
      if (enabled.includes(key as IndicatorId)) merged[key] = value;
    }
    return merged;
  }, [query.data?.indicators, live?.indicators, enabled]);

  const forming = live?.includeForming ?? query.data?.include_forming ?? false;
  const source = live ? "live" : query.isLoading ? "loading" : "rest";

  function toggleEnabled(id: IndicatorId) {
    setEnabled((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  function toggleOverlay(id: IndicatorId) {
    onChartOverlaysChange(
      chartOverlays.includes(id)
        ? chartOverlays.filter((x) => x !== id)
        : [...chartOverlays, id],
    );
  }

  return (
    <div className="space-y-3 rounded-lg border border-terminal-border bg-terminal-panel p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
            Technical Indicators
          </h3>
          <p className="mt-1 text-[11px] text-terminal-muted">
            {source === "loading"
              ? "Loading…"
              : source === "live"
                ? forming
                  ? "Live · forming candle"
                  : "Live · closed candles"
                : "REST seed · closed candles"}
          </p>
        </div>
        {query.isError ? (
          <span className="text-[11px] text-terminal-short">
            {(query.error as Error).message || "Error"}
          </span>
        ) : null}
      </div>

      <div>
        <p className="mb-1.5 text-[10px] uppercase tracking-[0.12em] text-terminal-muted">
          Chart overlays
        </p>
        <div className="flex flex-wrap gap-1.5">
          {CHART_OVERLAY_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              onClick={() => toggleOverlay(opt.id)}
              className={cn(
                "rounded border px-2 py-0.5 text-[11px]",
                chartOverlays.includes(opt.id)
                  ? "border-terminal-accent/60 bg-terminal-accent/15 text-terminal-accent"
                  : "border-terminal-border text-terminal-muted",
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-1.5 text-[10px] uppercase tracking-[0.12em] text-terminal-muted">
          Panel metrics
        </p>
        <div className="flex flex-wrap gap-1.5">
          {PANEL_DEFAULTS.map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => toggleEnabled(id)}
              className={cn(
                "rounded border px-2 py-0.5 text-[11px] uppercase",
                enabled.includes(id)
                  ? "border-terminal-border bg-terminal-surface text-terminal-text"
                  : "border-terminal-border/50 text-terminal-muted/60 line-through",
              )}
            >
              {id.replaceAll("_", " ")}
            </button>
          ))}
        </div>
      </div>

      {query.isLoading && !live ? (
        <p className="text-sm text-terminal-muted">Calculating indicators…</p>
      ) : (
        <div className="space-y-2">
          {enabled.includes("rsi_14") ? <RsiGauge item={latest.rsi_14} /> : null}
          {enabled
            .filter((id) => id !== "rsi_14")
            .map((id) => (
              <IndicatorRow key={id} id={id} item={latest[id]} />
            ))}
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status?: string }) {
  const label = status ?? "—";
  return (
    <span
      className={cn(
        "rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wide",
        status === "ready" && "bg-terminal-long/15 text-terminal-long",
        status === "warming_up" && "bg-amber-500/15 text-amber-400",
        (status === "insufficient_data" || status === "error" || !status) &&
          "bg-terminal-border text-terminal-muted",
      )}
    >
      {label.replaceAll("_", " ")}
    </span>
  );
}

function IndicatorRow({ id, item }: { id: IndicatorId; item?: IndicatorLatest }) {
  return (
    <div className="flex items-start justify-between gap-2 border-b border-terminal-border/60 py-1.5 last:border-0">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-terminal-text">
          {id.replaceAll("_", " ")}
          {item?.is_forming ? (
            <span className="ml-1 text-[10px] font-normal text-amber-400">forming</span>
          ) : null}
        </p>
        <p className="mt-0.5 font-mono text-sm text-terminal-text">{formatIndicator(id, item)}</p>
      </div>
      <StatusBadge status={item?.status} />
    </div>
  );
}

function formatIndicator(id: IndicatorId, item?: IndicatorLatest): string {
  if (!item) return "—";
  if (item.status !== "ready") return item.detail ?? "warming up";
  if (id === "macd") {
    const { macd, signal, histogram } = item.fields;
    return `M ${fmt(macd)} · S ${fmt(signal)} · H ${fmt(histogram)}`;
  }
  if (id === "bollinger") {
    const { upper, middle, lower } = item.fields;
    return `U ${formatPrice(upper)} · M ${formatPrice(middle)} · L ${formatPrice(lower)}`;
  }
  if (id === "stoch_rsi") {
    return `%K ${fmt(item.fields.k)} · %D ${fmt(item.fields.d)}`;
  }
  if (id === "obv" || id === "volume_sma_20") {
    return formatVolume(item.value);
  }
  if (id === "relative_volume") {
    return item.value == null ? "—" : `${item.value.toFixed(2)}x`;
  }
  if (id === "rsi_14") {
    return item.value == null ? "—" : item.value.toFixed(1);
  }
  return formatPrice(item.value);
}

function fmt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toFixed(2);
}

function RsiGauge({ item }: { item?: IndicatorLatest }) {
  const value = item?.value;
  const pct = value == null ? 0 : Math.min(100, Math.max(0, value));
  return (
    <div className="rounded border border-terminal-border/70 bg-terminal-surface/40 p-2">
      <div className="mb-1.5 flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wide text-terminal-text">
          RSI 14
          {item?.is_forming ? (
            <span className="ml-1 text-[10px] font-normal text-amber-400">forming</span>
          ) : null}
        </p>
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm text-terminal-text">
            {value == null ? "—" : value.toFixed(1)}
          </span>
          <StatusBadge status={item?.status} />
        </div>
      </div>
      <div className="relative h-2 overflow-hidden rounded-sm bg-terminal-border">
        <div
          className="absolute inset-y-0 left-0 bg-gradient-to-r from-terminal-short via-terminal-accent to-terminal-long"
          style={{ width: `${pct}%` }}
        />
        <div className="absolute inset-y-0 left-[30%] w-px bg-terminal-bg/70" />
        <div className="absolute inset-y-0 left-[70%] w-px bg-terminal-bg/70" />
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-terminal-muted">
        <span>0</span>
        <span>30</span>
        <span>70</span>
        <span>100</span>
      </div>
    </div>
  );
}
