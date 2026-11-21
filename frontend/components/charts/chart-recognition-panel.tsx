"use client";

import type { ExchangeId, MarketType, Timeframe, VisionResult } from "@/types/api";
import {
  SUPPORTED_TIMEFRAMES,
  formatConfidence,
  type RecognitionDraft,
} from "@/lib/chart-recognition";
import { cn } from "@/utils/cn";

interface ChartRecognitionPanelProps {
  vision: VisionResult | null;
  draft: RecognitionDraft;
  /** Partial patch — parent merges onto latest draft to avoid stale confirm flags. */
  onDraftChange: (patch: Partial<RecognitionDraft>) => void;
  recognizing?: boolean;
  disabled?: boolean;
}

export function ChartRecognitionPanel({
  vision,
  draft,
  onDraftChange,
  recognizing,
  disabled,
}: ChartRecognitionPanelProps) {
  const needsSymbol = !draft.symbolConfirmed;
  const needsTf = !draft.timeframeConfirmed;

  return (
    <div
      className="space-y-3 rounded-md border border-terminal-border bg-terminal-panel p-3"
      data-testid="recognition-panel"
    >
      <div>
        <p className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
          Screenshot recognition
        </p>
        <p className="mt-1 text-[11px] text-terminal-muted">
          OCR/visual estimates only — confirm before deterministic analysis. Not live market data.
        </p>
      </div>

      {recognizing ? (
        <p className="text-[11px] text-terminal-muted">Recognizing chart image…</p>
      ) : null}

      {vision?.message ? (
        <p className="text-[11px] text-amber-200">{vision.message}</p>
      ) : null}

      <div className="grid gap-2 text-[11px]">
        <Row
          label="Detected symbol"
          value={vision?.detected_symbol || "unavailable"}
          meta={`confidence ${formatConfidence(vision?.symbol_confidence)}`}
        />
        <Row
          label="Detected timeframe"
          value={vision?.detected_timeframe || "unavailable"}
          meta={`confidence ${formatConfidence(vision?.timeframe_confidence)}`}
        />
        <Row
          label="Detected exchange / platform"
          value={
            [vision?.detected_exchange, vision?.detected_platform]
              .filter(Boolean)
              .join(" · ") || "unavailable"
          }
        />
        <Row
          label="Screenshot-observed price"
          value={
            vision?.observed_last_price != null
              ? String(vision.observed_last_price)
              : vision?.observed_price_label || "unavailable"
          }
          meta={`confidence ${formatConfidence(vision?.observed_price_confidence)} · not verified`}
        />
      </div>

      {(needsSymbol || needsTf) && (
        <p className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-100">
          Confirm or correct the fields below before Analyze. Ambiguous recognition is never
          silently guessed.
        </p>
      )}

      <label className="block space-y-1">
        <span className="text-[10px] uppercase tracking-[0.12em] text-terminal-muted">
          Confirmed exchange
        </span>
        <select
          disabled={disabled}
          value={draft.exchange}
          onChange={(e) =>
            onDraftChange({
              exchange: e.target.value as ExchangeId,
            })
          }
          className="h-9 w-full rounded-md border border-terminal-border bg-terminal-surface px-2 text-sm text-terminal-text"
        >
          <option value="binance">Binance</option>
          <option value="bybit">Bybit</option>
        </select>
      </label>

      <label className="block space-y-1">
        <span className="text-[10px] uppercase tracking-[0.12em] text-terminal-muted">
          Confirmed market type
        </span>
        <select
          disabled={disabled}
          value={draft.marketType}
          onChange={(e) =>
            onDraftChange({
              marketType: e.target.value as MarketType,
            })
          }
          className="h-9 w-full rounded-md border border-terminal-border bg-terminal-surface px-2 text-sm text-terminal-text"
        >
          <option value="spot">Spot</option>
          {draft.exchange === "binance" ? (
            <option value="usdt_m_futures">USDT-M Futures</option>
          ) : (
            <option value="linear_perpetual">Linear Perp</option>
          )}
        </select>
      </label>

      <label className="block space-y-1">
        <span className="text-[10px] uppercase tracking-[0.12em] text-terminal-muted">
          Confirmed symbol
        </span>
        <input
          disabled={disabled}
          value={draft.symbol}
          onChange={(e) =>
            onDraftChange({
              symbol: e.target.value.toUpperCase(),
              symbolConfirmed: true,
            })
          }
          placeholder="BTC/USDT"
          className={cn(
            "h-9 w-full rounded-md border bg-terminal-surface px-2 text-sm text-terminal-text",
            needsSymbol ? "border-amber-500/60" : "border-terminal-border",
          )}
          data-testid="confirm-symbol"
        />
      </label>

      <label className="block space-y-1">
        <span className="text-[10px] uppercase tracking-[0.12em] text-terminal-muted">
          Confirmed timeframe
        </span>
        <select
          disabled={disabled}
          value={draft.timeframe}
          onChange={(e) =>
            onDraftChange({
              timeframe: e.target.value as Timeframe,
              timeframeConfirmed: true,
            })
          }
          className={cn(
            "h-9 w-full rounded-md border bg-terminal-surface px-2 text-sm text-terminal-text",
            needsTf ? "border-amber-500/60" : "border-terminal-border",
          )}
          data-testid="confirm-timeframe"
        >
          {SUPPORTED_TIMEFRAMES.map((tf) => (
            <option key={tf} value={tf}>
              {tf}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

function Row({
  label,
  value,
  meta,
}: {
  label: string;
  value: string;
  meta?: string;
}) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-terminal-border/60 pb-1.5 last:border-0">
      <span className="text-terminal-muted">{label}</span>
      <span className="text-terminal-text">{value}</span>
      {meta ? <span className="text-terminal-muted">{meta}</span> : null}
    </div>
  );
}
