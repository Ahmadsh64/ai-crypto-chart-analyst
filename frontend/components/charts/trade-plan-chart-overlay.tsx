"use client";

import {
  DEFAULT_TRADE_PLAN_CHART_TOGGLES,
  setAllTradePlanLevelsVisible,
  type PlanChartStatus,
  type TradePlanChartToggleState,
  type TradePlanLegendModel,
} from "@/lib/trade-plan-chart-visuals";
import { cn } from "@/utils/cn";

const TOGGLE_ROWS: { key: keyof TradePlanChartToggleState; label: string }[] = [
  { key: "entry", label: "Entry" },
  { key: "stopLoss", label: "Stop Loss" },
  { key: "tp1", label: "TP1" },
  { key: "tp2", label: "TP2" },
  { key: "tp3", label: "TP3" },
  { key: "riskRewardZones", label: "Risk / Reward zones" },
];

function statusTone(status: PlanChartStatus): string {
  switch (status) {
    case "WAITING FOR CONFIRMATION":
      return "border-amber-400/50 bg-amber-400/10 text-amber-200";
    case "LONG SETUP CONFIRMED":
      return "border-terminal-long/50 bg-terminal-long/10 text-terminal-long";
    case "SHORT SETUP CONFIRMED":
      return "border-terminal-short/50 bg-terminal-short/10 text-terminal-short";
    case "NO TRADE":
      return "border-terminal-border bg-terminal-surface text-terminal-muted";
    default:
      return "border-terminal-border bg-terminal-surface text-terminal-muted";
  }
}

function fmtLevel(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: 8 });
}

export function TradePlanChartStatusBadge({ status }: { status: PlanChartStatus }) {
  return (
    <span
      className={cn(
        "rounded border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide",
        statusTone(status),
      )}
    >
      {status}
    </span>
  );
}

export function TradePlanChartLegend({
  legend,
  currentPrice,
}: {
  legend: TradePlanLegendModel;
  currentPrice?: number | null;
}) {
  const rows: { label: string; value: string; note?: string }[] = [
    { label: "Decision", value: legend.decision ?? "—" },
    { label: "Direction", value: legend.direction ?? "—" },
    { label: "Entry", value: fmtLevel(legend.entry), note: "Planned" },
    { label: "Stop Loss", value: fmtLevel(legend.stopLoss), note: "Planned" },
    { label: "TP1", value: fmtLevel(legend.tp1), note: "Planned" },
    { label: "TP2", value: fmtLevel(legend.tp2), note: "Planned" },
    { label: "TP3", value: fmtLevel(legend.tp3), note: "Planned" },
    {
      label: "R:R",
      value: legend.primaryRr != null ? legend.primaryRr.toFixed(2) : "—",
    },
    {
      label: "Current Price",
      value: currentPrice != null && Number.isFinite(currentPrice) ? fmtLevel(currentPrice) : "—",
    },
  ];

  return (
    <div className="rounded-md border border-terminal-border/70 bg-terminal-bg/40 p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
          Trade plan legend
        </div>
        <TradePlanChartStatusBadge status={legend.status} />
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 sm:grid-cols-3">
        {rows.map((r) => (
          <div key={r.label} className="flex justify-between gap-2 border-b border-terminal-border/30 py-1 text-[11px]">
            <span className="text-terminal-muted">
              {r.label}
              {r.note ? (
                <span className="ml-1 text-[9px] uppercase tracking-wide text-terminal-muted/70">
                  {r.note}
                </span>
              ) : null}
            </span>
            <span className="font-mono text-terminal-text">{r.value}</span>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[10px] text-terminal-muted">
        Planned analysis levels only — not exchange fills. No execution markers.
      </p>
    </div>
  );
}

export function TradePlanChartControls({
  toggles,
  onChange,
  disabled,
}: {
  toggles: TradePlanChartToggleState;
  onChange: (next: TradePlanChartToggleState) => void;
  disabled?: boolean;
}) {
  return (
    <div className="rounded-md border border-terminal-border/70 bg-terminal-bg/40 p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
          Trade plan chart overlays
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={disabled}
            className="rounded border border-terminal-border px-2 py-0.5 text-[10px] text-terminal-text hover:border-terminal-accent/50 disabled:opacity-40"
            onClick={() => onChange(setAllTradePlanLevelsVisible(true))}
          >
            Show all
          </button>
          <button
            type="button"
            disabled={disabled}
            className="rounded border border-terminal-border px-2 py-0.5 text-[10px] text-terminal-text hover:border-terminal-accent/50 disabled:opacity-40"
            onClick={() => onChange(setAllTradePlanLevelsVisible(false))}
          >
            Hide all
          </button>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 sm:grid-cols-3 lg:grid-cols-4">
        {TOGGLE_ROWS.map(({ key, label }) => (
          <label
            key={key}
            className={cn(
              "flex items-center gap-2 text-[11px] text-terminal-text",
              (disabled || !toggles.allLevels) && key !== "allLevels" && "opacity-40",
            )}
          >
            <input
              type="checkbox"
              className="accent-amber-400"
              checked={toggles.allLevels && toggles[key]}
              disabled={disabled || !toggles.allLevels}
              onChange={(e) => onChange({ ...toggles, [key]: e.target.checked })}
            />
            {label}
          </label>
        ))}
        <label
          className={cn(
            "flex items-center gap-2 text-[11px] text-terminal-text",
            disabled && "opacity-40",
          )}
        >
          <input
            type="checkbox"
            className="accent-amber-400"
            checked={toggles.allLevels}
            disabled={disabled}
            onChange={(e) =>
              onChange({
                ...toggles,
                allLevels: e.target.checked,
                ...(e.target.checked ? {} : {}),
              })
            }
          />
          All trade plan levels
        </label>
      </div>
    </div>
  );
}

export { DEFAULT_TRADE_PLAN_CHART_TOGGLES };
