"use client";

import { useMemo, useState } from "react";
import type {
  BacktestReportSnapshot,
  EquityCurve,
  ReportTradeDetail,
} from "@/types/api";
import {
  REPORT_DISCLAIMER,
  REPORT_EXPORT_ACTIONS,
  formatReportMetric,
  formatReportNumber,
  formatReportUtc,
  pnlTone,
  type ReportExportKind,
} from "@/lib/backtest-report-display";
import { cn } from "@/utils/cn";

interface Props {
  report: BacktestReportSnapshot | null;
  enabled: boolean;
  busy?: boolean;
  exportBusy?: boolean;
  error?: string | null;
  onRefresh?: () => Promise<void>;
  onFilterDirection?: (direction: string | null) => Promise<void>;
  onExportCsv?: (kind: ReportExportKind) => Promise<void>;
  onExportPdf?: () => Promise<void>;
}

function Sparkline({
  values,
  color,
  height = 72,
}: {
  values: number[];
  color: string;
  height?: number;
}) {
  const path = useMemo(() => {
    if (values.length < 2) return "";
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const w = 320;
    return values
      .map((v, i) => {
        const x = (i / (values.length - 1)) * w;
        const y = height - ((v - min) / span) * (height - 8) - 4;
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }, [values, height]);

  if (values.length < 2) {
    return (
      <div className="flex h-[72px] items-center justify-center text-[11px] text-terminal-muted">
        Not enough points
      </div>
    );
  }

  return (
    <svg viewBox={`0 0 320 ${height}`} className="h-[72px] w-full" preserveAspectRatio="none">
      <path d={path} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  );
}

function equitySeries(curve: EquityCurve | undefined, initial: number | null): number[] {
  if (!curve?.points?.length) {
    return initial !== null ? [initial] : [];
  }
  return curve.points.map((p) => {
    if (p.equity !== null && p.equity !== undefined) return Number(p.equity);
    const cum = Number(p.cumulative_net_pnl);
    return initial !== null ? initial + cum : cum;
  });
}

function Card({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "long" | "short" | "muted";
}) {
  return (
    <div className="rounded border border-terminal-border/70 bg-terminal-surface/40 px-2.5 py-2">
      <div className="text-[10px] uppercase tracking-wide text-terminal-muted">{label}</div>
      <div
        className={cn(
          "mt-0.5 font-mono text-sm",
          tone === "long" && "text-terminal-long",
          tone === "short" && "text-terminal-short",
          (!tone || tone === "muted") && "text-terminal-text",
        )}
      >
        {value}
      </div>
    </div>
  );
}

function TradesTable({ rows }: { rows: ReportTradeDetail[] }) {
  const [sortKey, setSortKey] = useState<"exit" | "net" | "id">("exit");

  const sorted = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      if (sortKey === "net") {
        return Number(b.net_realized_pnl ?? 0) - Number(a.net_realized_pnl ?? 0);
      }
      if (sortKey === "id") {
        return a.trade_id.localeCompare(b.trade_id);
      }
      return String(b.exit_timestamp ?? "").localeCompare(String(a.exit_timestamp ?? ""));
    });
    return copy;
  }, [rows, sortKey]);

  return (
    <div className="overflow-x-auto rounded border border-terminal-border/70">
      <div className="flex items-center justify-between gap-2 bg-terminal-surface/80 px-2 py-1.5">
        <span className="text-[11px] font-medium text-terminal-muted">Completed trades</span>
        <label className="text-[10px] text-terminal-muted">
          Sort{" "}
          <select
            className="rounded border border-terminal-border bg-terminal-panel px-1 py-0.5 text-[10px]"
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as "exit" | "net" | "id")}
          >
            <option value="exit">Exit time</option>
            <option value="net">Net P&amp;L</option>
            <option value="id">Trade ID</option>
          </select>
        </label>
      </div>
      <table className="min-w-full text-left text-[11px]">
        <thead className="text-terminal-muted">
          <tr>
            <th className="px-2 py-1">Trade ID</th>
            <th className="px-2 py-1">Dir</th>
            <th className="px-2 py-1">Entry</th>
            <th className="px-2 py-1">Exit</th>
            <th className="px-2 py-1">Entry Px</th>
            <th className="px-2 py-1">Exit Px</th>
            <th className="px-2 py-1">Net P&amp;L</th>
            <th className="px-2 py-1">R</th>
            <th className="px-2 py-1">Fees</th>
            <th className="px-2 py-1">Exit</th>
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 ? (
            <tr>
              <td colSpan={10} className="px-2 py-3 text-terminal-muted">
                No completed trades at this replay clock.
              </td>
            </tr>
          ) : (
            sorted.map((row) => {
              const tone = pnlTone(row.net_realized_pnl);
              return (
                <tr key={row.trade_id} className="border-t border-terminal-border/40">
                  <td className="px-2 py-1 font-mono text-[10px]">{row.trade_id}</td>
                  <td className="px-2 py-1">{row.direction}</td>
                  <td className="px-2 py-1 whitespace-nowrap">
                    {formatReportUtc(row.entry_timestamp)}
                  </td>
                  <td className="px-2 py-1 whitespace-nowrap">
                    {formatReportUtc(row.exit_timestamp)}
                  </td>
                  <td className="px-2 py-1">{formatReportNumber(row.entry_price)}</td>
                  <td className="px-2 py-1">
                    {formatReportNumber(row.average_exit_price)}
                  </td>
                  <td
                    className={cn(
                      "px-2 py-1 font-mono",
                      tone === "long" && "text-terminal-long",
                      tone === "short" && "text-terminal-short",
                    )}
                  >
                    {formatReportNumber(row.net_realized_pnl)}
                  </td>
                  <td className="px-2 py-1">{formatReportNumber(row.r_multiple)}</td>
                  <td className="px-2 py-1">{formatReportNumber(row.fees)}</td>
                  <td className="px-2 py-1">{row.exit_type}</td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

export function HistoricalBacktestReportPanel({
  report,
  enabled,
  busy,
  exportBusy,
  error,
  onRefresh,
  onFilterDirection,
  onExportCsv,
  onExportPdf,
}: Props) {
  if (!enabled) {
    return (
      <section className="rounded-lg border border-terminal-border bg-terminal-panel p-4">
        <h2 className="text-sm font-semibold text-terminal-text">Backtest Report</h2>
        <p className="mt-2 text-[11px] text-terminal-muted">
          Enable Performance Analytics to generate a report snapshot at the current replay clock.
        </p>
      </section>
    );
  }

  const summary = report?.summary;
  const initial =
    summary?.initial_equity !== null && summary?.initial_equity !== undefined
      ? Number(summary.initial_equity)
      : null;
  const equityValues = equitySeries(report?.equity.completed, initial);
  const drawdownValues =
    report?.drawdown.points.map((p) => Number(p.drawdown)) ?? [];
  const filterCtx = report?.metadata.filter_context ?? {};
  const activeDirection =
    typeof filterCtx.direction === "string" ? filterCtx.direction : null;
  const hasActiveFilter = Object.values(filterCtx).some(
    (v) => v !== null && v !== undefined && v !== "",
  );

  return (
    <section className="space-y-3 rounded-lg border border-terminal-border bg-terminal-panel p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-terminal-text">Backtest Report</h2>
          <p className="mt-1 text-[11px] text-amber-400/90">{REPORT_DISCLAIMER}</p>
          {report ? (
            <p className="mt-1 text-[11px] text-terminal-muted">
              Clock {formatReportUtc(report.metadata.replay_timestamp)} · report{" "}
              {report.metadata.report_id}
              {hasActiveFilter ? " · filtered view (not full session)" : ""}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            disabled={busy || !onRefresh}
            onClick={() => void onRefresh?.()}
            className="rounded border border-terminal-border px-2 py-1 text-[11px] text-terminal-text hover:bg-terminal-surface disabled:opacity-50"
          >
            Refresh
          </button>
          {REPORT_EXPORT_ACTIONS.map((action) => (
            <button
              key={action.kind}
              type="button"
              disabled={exportBusy || busy || !report}
              onClick={() => {
                if (action.kind === "pdf") void onExportPdf?.();
                else void onExportCsv?.(action.kind);
              }}
              className="rounded border border-terminal-accent/40 px-2 py-1 text-[11px] text-terminal-accent hover:bg-terminal-accent/10 disabled:opacity-50"
            >
              {action.label}
            </button>
          ))}
        </div>
      </div>

      {onFilterDirection ? (
        <label className="flex items-center gap-2 text-[11px] text-terminal-muted">
          Direction filter
          <select
            className="rounded border border-terminal-border bg-terminal-surface px-2 py-1 text-[11px] text-terminal-text"
            value={activeDirection ?? ""}
            disabled={busy}
            onChange={(e) => {
              const v = e.target.value;
              void onFilterDirection(v === "" ? null : v);
            }}
          >
            <option value="">All directions</option>
            <option value="LONG">LONG</option>
            <option value="SHORT">SHORT</option>
          </select>
        </label>
      ) : null}

      {error ? <p className="text-xs text-terminal-short">{error}</p> : null}

      {!report ? (
        <p className="text-[11px] text-terminal-muted">
          {busy ? "Building report…" : "No report loaded yet."}
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Card label="Completed" value={String(summary?.completed_trade_count ?? 0)} />
            <Card label="Win Rate" value={formatReportMetric(summary?.win_rate)} />
            <Card label="Profit Factor" value={formatReportMetric(summary?.profit_factor)} />
            <Card
              label="Net P&L"
              value={formatReportNumber(summary?.net_pnl)}
              tone={pnlTone(summary?.net_pnl)}
            />
            <Card
              label="Gross P&L"
              value={formatReportNumber(summary?.gross_pnl)}
              tone={pnlTone(summary?.gross_pnl)}
            />
            <Card label="Max Drawdown" value={formatReportNumber(summary?.max_drawdown)} />
            <Card
              label="Ending Equity"
              value={formatReportMetric(summary?.ending_equity)}
            />
            <Card
              label="Exec Costs"
              value={formatReportNumber(summary?.total_execution_costs)}
            />
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded border border-terminal-border/70 p-2">
              <div className="mb-1 text-[11px] text-terminal-muted">Equity curve</div>
              <Sparkline values={equityValues} color="#3ecf8e" />
            </div>
            <div className="rounded border border-terminal-border/70 p-2">
              <div className="mb-1 text-[11px] text-terminal-muted">Drawdown</div>
              <Sparkline values={drawdownValues} color="#f07178" />
            </div>
          </div>

          <TradesTable rows={report.completed_trades} />

          {report.open_trade_total > 0 ? (
            <p className="text-[11px] text-terminal-muted">
              Open / incomplete trades: {report.open_trade_total} (excluded from completed
              metrics)
              {report.open_trades_truncated ? " — list truncated inline" : ""}.
            </p>
          ) : null}

          {report.limitations.length > 0 ? (
            <ul className="space-y-1 text-[11px] text-amber-400">
              {report.limitations.slice(0, 6).map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          ) : null}
        </>
      )}
    </section>
  );
}
