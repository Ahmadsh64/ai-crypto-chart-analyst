"use client";

import type {
  TradeChartToggleState,
  TradeDetailsModel,
} from "@/lib/trade-chart-visuals";
import { formatReplayClock } from "@/lib/replay-display";
import { cn } from "@/utils/cn";

const TOGGLE_ROWS: { key: keyof TradeChartToggleState; label: string }[] = [
  { key: "entryMarkers", label: "Entry markers" },
  { key: "exitMarkers", label: "Exit markers" },
  { key: "partialExits", label: "Partial exits" },
  { key: "entryLine", label: "Entry line" },
  { key: "stopLossLine", label: "Stop Loss line" },
  { key: "takeProfitLines", label: "Take Profit lines" },
];

export function HistoricalTradeOverlayControls({
  toggles,
  onChange,
  disabled,
}: {
  toggles: TradeChartToggleState;
  onChange: (next: TradeChartToggleState) => void;
  disabled?: boolean;
}) {
  return (
    <div className="rounded-md border border-terminal-border/70 bg-terminal-bg/40 p-3">
      <div className="mb-2 text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
        Trade chart overlays
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 sm:grid-cols-3">
        {TOGGLE_ROWS.map(({ key, label }) => (
          <label
            key={key}
            className={cn(
              "flex items-center gap-2 text-[11px] text-terminal-text",
              disabled && "opacity-40",
            )}
          >
            <input
              type="checkbox"
              className="accent-emerald-400"
              checked={toggles[key]}
              disabled={disabled}
              onChange={(e) => onChange({ ...toggles, [key]: e.target.checked })}
            />
            {label}
          </label>
        ))}
      </div>
      <p className="mt-2 text-[10px] text-terminal-muted">
        Markers use executed fill times/prices. Lines are planned levels — not fills.
      </p>
    </div>
  );
}

export function HistoricalTradeDetailsPanel({
  details,
  onClose,
}: {
  details: TradeDetailsModel | null;
  onClose: () => void;
}) {
  if (!details) return null;

  const rows: { label: string; value: string }[] = [
    { label: "Trade ID", value: details.tradeId },
    { label: "Direction", value: details.direction },
    {
      label: "Entry price",
      value: details.entryPrice != null ? String(details.entryPrice) : "N/A",
    },
    {
      label: "Entry time",
      value: details.entryTimestamp ? formatReplayClock(details.entryTimestamp) : "N/A",
    },
    {
      label: "Exit price",
      value: details.exitPrice != null ? String(details.exitPrice) : "N/A",
    },
    { label: "Exit type", value: details.exitType ?? "N/A" },
    {
      label: "Executed qty",
      value: details.executedQuantity != null ? String(details.executedQuantity) : "N/A",
    },
    {
      label: "Remaining qty",
      value: details.remainingQuantity != null ? String(details.remainingQuantity) : "N/A",
    },
    { label: "Status @ clock", value: details.status },
    {
      label: "Realized P&L",
      value: details.realizedPnl != null ? String(details.realizedPnl) : "N/A",
    },
  ];

  return (
    <div className="rounded-md border border-emerald-400/30 bg-terminal-panel px-3 py-2 text-xs">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-emerald-300/90">
          Trade details
        </span>
        <button
          type="button"
          onClick={onClose}
          className="text-[11px] text-terminal-muted hover:text-terminal-text"
        >
          Close
        </button>
      </div>
      <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
        {rows.map((r) => (
          <div key={r.label} className="flex justify-between gap-3 border-b border-terminal-border/40 py-1">
            <span className="text-terminal-muted">{r.label}</span>
            <span className="font-mono text-terminal-text">{r.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
