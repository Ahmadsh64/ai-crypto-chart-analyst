"use client";

import { useLiquidity } from "@/hooks/use-market-data";
import { useLiveLiquiditySubscription } from "@/hooks/use-market-socket";
import { indicatorKey, useLiveMarketStore } from "@/stores/live-market-store";
import { formatPrice } from "@/utils/format";
import { cn } from "@/utils/cn";
import type { ExchangeId, MarketType, Timeframe } from "@/types/api";
import type { LiquidityOverlayId } from "@/lib/liquidity-chart-overlays";

interface LiquidityPanelProps {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  timeframe: Timeframe;
  overlays: LiquidityOverlayId[];
  onOverlaysChange: (ids: LiquidityOverlayId[]) => void;
}

const OVERLAY_OPTIONS: { id: LiquidityOverlayId; label: string }[] = [
  { id: "eqh", label: "EQH" },
  { id: "eql", label: "EQL" },
  { id: "bsl", label: "BSL" },
  { id: "ssl", label: "SSL" },
  { id: "sweeps", label: "Sweeps" },
];

export function LiquidityPanel({
  exchange,
  marketType,
  symbol,
  timeframe,
  overlays,
  onOverlaysChange,
}: LiquidityPanelProps) {
  useLiveLiquiditySubscription(exchange, marketType, symbol, timeframe, true);

  const query = useLiquidity({
    exchange,
    marketType,
    symbol,
    timeframe,
    includeUnconfirmed: false,
  });

  const live = useLiveMarketStore(
    (s) => s.liquidity[indicatorKey(exchange, marketType, symbol, timeframe)],
  );

  const snapshot = live?.snapshot ?? query.data?.snapshot;
  const eqh = live?.eqhClusters ?? query.data?.eqh_clusters ?? [];
  const eql = live?.eqlClusters ?? query.data?.eql_clusters ?? [];
  const bsl = live?.bslLevels ?? query.data?.bsl_levels ?? [];
  const ssl = live?.sslLevels ?? query.data?.ssl_levels ?? [];
  const sweeps = live?.sweeps ?? query.data?.sweeps ?? [];
  const source = live ? "live" : query.isLoading ? "loading" : "rest";

  function toggle(id: LiquidityOverlayId) {
    onOverlaysChange(
      overlays.includes(id) ? overlays.filter((x) => x !== id) : [...overlays, id],
    );
  }

  const selectedLevel =
    [...bsl, ...ssl].find((lv) => lv.status === "active") ?? bsl[0] ?? ssl[0] ?? null;
  const selectedCluster = eqh[0] ?? eql[0] ?? null;
  const lastSweep = sweeps.at(-1) ?? null;

  return (
    <div className="space-y-3 rounded-lg border border-terminal-border bg-terminal-panel p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
            Liquidity
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
        <Stat label="EQH" value={String(eqh.length)} />
        <Stat label="EQL" value={String(eql.length)} />
        <Stat label="BSL" value={String(bsl.length)} />
        <Stat label="SSL" value={String(ssl.length)} />
        <Stat label="Sweeps" value={String(sweeps.length)} />
        <Stat
          label="Active"
          value={String(
            bsl.filter((x) => x.status === "active").length +
              ssl.filter((x) => x.status === "active").length,
          )}
        />
      </div>

      <div className="space-y-1 border-t border-terminal-border/60 pt-2 text-xs">
        <Row
          label="Last sweep pool"
          value={
            lastSweep ? lastSweep.liquidity_type.toUpperCase() : "—"
          }
        />
        <Row
          label="Reaction hint"
          value={
            lastSweep?.reaction_hint
              ? `${lastSweep.reaction_hint} (context only)`
              : lastSweep
                ? "—"
                : "—"
          }
        />
        <p className="pt-0.5 text-[10px] text-terminal-muted">
          Hint is not a trade signal or guaranteed reversal.
        </p>

        {selectedCluster ? (
          <>
            <Row
              label={`${selectedCluster.kind.toUpperCase()} level`}
              value={formatPrice(
                selectedCluster.representative_level ?? selectedCluster.level,
              )}
            />
            <Row
              label="Price range"
              value={
                selectedCluster.price_range != null &&
                selectedCluster.min_price != null &&
                selectedCluster.max_price != null
                  ? `${formatPrice(selectedCluster.min_price)}–${formatPrice(selectedCluster.max_price)} (${formatPrice(selectedCluster.price_range)})`
                  : "—"
              }
            />
            <Row
              label="Tolerance"
              value={formatPrice(selectedCluster.tolerance_used)}
            />
            <Row label="Members" value={String(selectedCluster.member_count)} />
          </>
        ) : null}

        {selectedLevel ? (
          <>
            <Row
              label="Selected level"
              value={`${selectedLevel.liquidity_type.toUpperCase()} ${formatPrice(selectedLevel.price)}`}
            />
            <Row label="Status" value={selectedLevel.status} />
            <Row label="Source" value={selectedLevel.source_type} />
            <div className="pt-1 text-[10px] text-terminal-muted">
              Contributing swings:
              <ul className="mt-1 space-y-0.5 font-mono text-terminal-text">
                {selectedLevel.source_swings.map((s) => (
                  <li key={s.swing_key}>
                    {formatPrice(s.price)} · {s.candle_timestamp}
                  </li>
                ))}
              </ul>
            </div>
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
      <span className="font-mono text-terminal-text text-right">{value}</span>
    </div>
  );
}
