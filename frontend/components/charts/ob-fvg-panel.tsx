"use client";

import { useObFvg } from "@/hooks/use-market-data";
import { useLiveObFvgSubscription } from "@/hooks/use-market-socket";
import { indicatorKey, useLiveMarketStore } from "@/stores/live-market-store";
import { formatPrice } from "@/utils/format";
import { cn } from "@/utils/cn";
import type { ExchangeId, MarketType, Timeframe } from "@/types/api";
import type { ObFvgOverlayId } from "@/lib/ob-fvg-chart-overlays";

interface ObFvgPanelProps {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  timeframe: Timeframe;
  overlays: ObFvgOverlayId[];
  onOverlaysChange: (ids: ObFvgOverlayId[]) => void;
}

const OVERLAY_OPTIONS: { id: ObFvgOverlayId; label: string }[] = [
  { id: "bullishOb", label: "Bull OB" },
  { id: "bearishOb", label: "Bear OB" },
  { id: "bullishFvg", label: "Bull FVG" },
  { id: "bearishFvg", label: "Bear FVG" },
  { id: "recentZones", label: "Recent zones" },
];

export function ObFvgPanel({
  exchange,
  marketType,
  symbol,
  timeframe,
  overlays,
  onOverlaysChange,
}: ObFvgPanelProps) {
  useLiveObFvgSubscription(exchange, marketType, symbol, timeframe, true);

  const query = useObFvg({
    exchange,
    marketType,
    symbol,
    timeframe,
    includeUnconfirmed: false,
  });

  const live = useLiveMarketStore(
    (s) => s.obFvg[indicatorKey(exchange, marketType, symbol, timeframe)],
  );

  const snapshot = live?.snapshot ?? query.data?.snapshot;
  const bullOb = live?.bullishOrderBlocks ?? query.data?.bullish_order_blocks ?? [];
  const bearOb = live?.bearishOrderBlocks ?? query.data?.bearish_order_blocks ?? [];
  const bullFvg = live?.bullishFvgs ?? query.data?.bullish_fvgs ?? [];
  const bearFvg = live?.bearishFvgs ?? query.data?.bearish_fvgs ?? [];
  const source = live ? "live" : query.isLoading ? "loading" : "rest";

  function toggle(id: ObFvgOverlayId) {
    onOverlaysChange(
      overlays.includes(id) ? overlays.filter((x) => x !== id) : [...overlays, id],
    );
  }

  const selectedOb = [...bullOb, ...bearOb].find((o) => o.status === "active") ?? bullOb[0] ?? bearOb[0] ?? null;
  const selectedFvg =
    [...bullFvg, ...bearFvg].find((f) => f.status === "active") ?? bullFvg[0] ?? bearFvg[0] ?? null;

  return (
    <div className="space-y-3 rounded-lg border border-terminal-border bg-terminal-panel p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
            Order Blocks / FVG
          </h3>
          <p className="mt-1 text-[11px] text-terminal-muted">
            {source === "loading"
              ? "Loading…"
              : source === "live"
                ? "Live · closed candles"
                : "REST seed"}
            {snapshot?.config_version ? ` · ${snapshot.config_version}` : ""}
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
          {OVERLAY_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              onClick={() => toggle(opt.id)}
              className={cn(
                "rounded border px-2 py-0.5 text-[11px]",
                overlays.includes(opt.id)
                  ? "border-terminal-accent/60 bg-terminal-accent/15 text-terminal-accent"
                  : "border-terminal-border text-terminal-muted",
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <Stat label="Bull OB" value={String(bullOb.length)} />
        <Stat label="Bear OB" value={String(bearOb.length)} />
        <Stat label="Bull FVG" value={String(bullFvg.length)} />
        <Stat label="Bear FVG" value={String(bearFvg.length)} />
        <Stat
          label="Active OB"
          value={String(
            [...bullOb, ...bearOb].filter((x) => x.status === "active").length,
          )}
        />
        <Stat
          label="Active FVG"
          value={String(
            [...bullFvg, ...bearFvg].filter((x) => x.status === "active").length,
          )}
        />
      </div>

      <div className="space-y-1 border-t border-terminal-border/60 pt-2 text-xs">
        {selectedOb ? (
          <>
            <Row
              label="Selected OB"
              value={`${selectedOb.side} ${formatPrice(selectedOb.zone_low)}–${formatPrice(selectedOb.zone_high)}`}
            />
            <Row label="Status" value={selectedOb.status} />
            <Row
              label="Source"
              value={`${selectedOb.source_structure_kind.toUpperCase()} · ${selectedOb.source_candle_timestamp}`}
            />
          </>
        ) : null}
        {selectedFvg ? (
          <>
            <Row
              label="Selected FVG"
              value={`${selectedFvg.side} ${formatPrice(selectedFvg.zone_low)}–${formatPrice(selectedFvg.zone_high)}`}
            />
            <Row label="Status" value={selectedFvg.status} />
            <Row label="Fill %" value={`${selectedFvg.max_fill_pct.toFixed(1)}%`} />
          </>
        ) : null}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-terminal-border/70 bg-terminal-surface/40 px-2 py-1.5">
      <p className="text-[10px] uppercase tracking-wide text-terminal-muted">{label}</p>
      <p className="font-mono text-sm text-terminal-text">{value}</p>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-terminal-muted">{label}</span>
      <span className="max-w-[60%] truncate text-right font-mono text-terminal-text">
        {value}
      </span>
    </div>
  );
}
