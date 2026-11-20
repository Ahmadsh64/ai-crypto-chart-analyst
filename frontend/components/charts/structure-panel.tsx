"use client";

import { useMarketStructure } from "@/hooks/use-market-data";
import { useLiveStructureSubscription } from "@/hooks/use-market-socket";
import { indicatorKey, useLiveMarketStore } from "@/stores/live-market-store";
import { formatPrice } from "@/utils/format";
import { cn } from "@/utils/cn";
import type { ExchangeId, MarketType, Timeframe } from "@/types/api";

export type StructureOverlayId =
  | "swings"
  | "hh"
  | "hl"
  | "lh"
  | "ll"
  | "bos"
  | "choch"
  | "mss"
  | "recentLabels";

interface StructurePanelProps {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  timeframe: Timeframe;
  overlays: StructureOverlayId[];
  onOverlaysChange: (ids: StructureOverlayId[]) => void;
}

const OVERLAY_OPTIONS: { id: StructureOverlayId; label: string }[] = [
  { id: "swings", label: "Swings" },
  { id: "hh", label: "HH" },
  { id: "hl", label: "HL" },
  { id: "lh", label: "LH" },
  { id: "ll", label: "LL" },
  { id: "bos", label: "BOS" },
  { id: "choch", label: "CHoCH" },
  { id: "mss", label: "MSS" },
  { id: "recentLabels", label: "Recent labels only" },
];

export function StructurePanel({
  exchange,
  marketType,
  symbol,
  timeframe,
  overlays,
  onOverlaysChange,
}: StructurePanelProps) {
  useLiveStructureSubscription(exchange, marketType, symbol, timeframe, true);

  const query = useMarketStructure({
    exchange,
    marketType,
    symbol,
    timeframe,
    includeUnconfirmed: false,
  });

  const live = useLiveMarketStore(
    (s) => s.structure[indicatorKey(exchange, marketType, symbol, timeframe)],
  );

  const snapshot = live?.snapshot ?? query.data?.snapshot;
  const swings = live?.swings ?? query.data?.swings ?? [];
  const bos = live?.bosEvents ?? query.data?.bos_events ?? [];
  const choch = live?.chochEvents ?? query.data?.choch_events ?? [];
  const mss = live?.mssEvents ?? query.data?.mss_events ?? [];
  const source = live ? "live" : query.isLoading ? "loading" : "rest";

  function toggle(id: StructureOverlayId) {
    onOverlaysChange(
      overlays.includes(id) ? overlays.filter((x) => x !== id) : [...overlays, id],
    );
  }

  const bias = snapshot?.bias ?? "undefined";

  return (
    <div className="space-y-3 rounded-lg border border-terminal-border bg-terminal-panel p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
            Market Structure
          </h3>
          <p className="mt-1 text-[11px] text-terminal-muted">
            {source === "loading" ? "Loading…" : source === "live" ? "Live · closed candles" : "REST seed"}
            {snapshot?.config_version ? ` · ${snapshot.config_version}` : ""}
          </p>
        </div>
        {query.isError ? (
          <span className="text-[11px] text-terminal-short">
            {(query.error as Error).message || "Error"}
          </span>
        ) : null}
      </div>

      <div
        className={cn(
          "rounded border px-3 py-2 text-center",
          bias === "bullish" && "border-terminal-long/40 bg-terminal-long/10 text-terminal-long",
          bias === "bearish" && "border-terminal-short/40 bg-terminal-short/10 text-terminal-short",
          bias === "undefined" && "border-terminal-border text-terminal-muted",
        )}
      >
        <p className="text-[10px] uppercase tracking-[0.14em]">Structure bias</p>
        <p className="mt-0.5 font-display text-lg font-semibold uppercase">{bias}</p>
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
        <p className="mt-1.5 text-[10px] text-terminal-muted">
          Historical structure data is retained in this panel. “Recent labels only”
          hides older chart labels/segments for readability.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <Stat label="Swings" value={String(swings.length)} />
        <Stat label="BOS" value={String(bos.length)} />
        <Stat label="CHoCH" value={String(choch.length)} />
        <Stat label="MSS" value={String(mss.length)} />
      </div>

      <div className="space-y-1 border-t border-terminal-border/60 pt-2 text-xs">
        <Row
          label="Unbroken SH (bullish break target)"
          value={formatPrice(
            snapshot?.active_unbroken_swing_high ?? snapshot?.active_bullish_level,
          )}
        />
        <Row
          label="Unbroken SL (bearish break target)"
          value={formatPrice(
            snapshot?.active_unbroken_swing_low ?? snapshot?.active_bearish_level,
          )}
        />
        <Row
          label="Last BOS"
          value={bos.at(-1) ? `${bos.at(-1)!.direction} @ ${formatPrice(bos.at(-1)!.broken_level)}` : "—"}
        />
        <Row
          label="Last CHoCH"
          value={
            choch.at(-1)
              ? `${choch.at(-1)!.direction} @ ${formatPrice(choch.at(-1)!.broken_level)}`
              : "—"
          }
        />
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
      <span className="font-mono text-terminal-text">{value}</span>
    </div>
  );
}
