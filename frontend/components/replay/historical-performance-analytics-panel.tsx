"use client";

import { useMemo, useState } from "react";
import type {
  AnalyticsConfigPublic,
  AnalyticsSnapshot,
  EquityCurve,
  GroupPerformanceRow,
  MetricValue,
} from "@/types/api";
import { cn } from "@/utils/cn";

interface Props {
  snapshot: AnalyticsSnapshot | null;
  enabled: boolean;
  busy?: boolean;
  config?: AnalyticsConfigPublic | null;
  onSaveConfig?: (patch: Partial<AnalyticsConfigPublic> & { clear_initial_equity?: boolean }) => Promise<void>;
  onFilter?: (direction: string | null) => Promise<void>;
}

function fmtMetric(m?: MetricValue | null): string {
  if (!m) return "N/A";
  if (m.availability === "unavailable") return "N/A";
  if (m.availability === "infinite") return "∞";
  if (m.value === null || m.value === undefined) return "N/A";
  const n = Number(m.value);
  if (!Number.isFinite(n)) return String(m.value);
  return n.toFixed(n >= 100 || n <= -100 ? 2 : 5);
}

function fmtNum(v: string | number | null | undefined): string {
  if (v === null || v === undefined) return "N/A";
  const n = Number(v);
  if (!Number.isFinite(n)) return "N/A";
  return n.toFixed(5);
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

function GroupTable({ title, rows }: { title: string; rows: GroupPerformanceRow[] }) {
  return (
    <div className="overflow-x-auto rounded border border-terminal-border/70">
      <div className="bg-terminal-surface/80 px-2 py-1.5 text-[11px] font-medium text-terminal-muted">
        {title}
      </div>
      <table className="min-w-full text-left text-[11px]">
        <thead className="text-terminal-muted">
          <tr>
            <th className="px-2 py-1">Key</th>
            <th className="px-2 py-1">Trades</th>
            <th className="px-2 py-1">Win%</th>
            <th className="px-2 py-1">Net</th>
            <th className="px-2 py-1">PF</th>
            <th className="px-2 py-1">Avg</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={6} className="px-2 py-2 text-terminal-muted">
                No rows
              </td>
            </tr>
          ) : (
            rows.map((r) => (
              <tr key={r.key} className="border-t border-terminal-border/40">
                <td className="px-2 py-1 text-terminal-text">{r.key}</td>
                <td className="px-2 py-1">{r.completed_trades}</td>
                <td className="px-2 py-1">{fmtMetric(r.win_rate)}</td>
                <td className="px-2 py-1">{fmtNum(r.net_pnl)}</td>
                <td className="px-2 py-1">{fmtMetric(r.profit_factor)}</td>
                <td className="px-2 py-1">{fmtMetric(r.average_net_trade)}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export function HistoricalPerformanceAnalyticsPanel({
  snapshot,
  enabled,
  busy = false,
  config,
  onSaveConfig,
  onFilter,
}: Props) {
  const [equityMode, setEquityMode] = useState<"completed_trade" | "realized_cashflow">(
    "completed_trade",
  );
  const [initialEquity, setInitialEquity] = useState(
    config?.initial_equity != null ? String(config.initial_equity) : "",
  );
  const [directionFilter, setDirectionFilter] = useState<string>("");

  if (!enabled) {
    return (
      <div className="rounded-lg border border-terminal-border bg-terminal-panel p-4 text-sm text-terminal-muted">
        Performance analytics is off. Enable it to compute win rate, profit factor, equity curve,
        and drawdown from simulated + cost results.
      </div>
    );
  }

  const summary = snapshot?.summary;
  const stats = summary?.trade_stats;
  const profit = summary?.profitability;
  const dd = snapshot?.drawdown ?? summary?.drawdown;
  const initial =
    summary?.initial_equity != null ? Number(summary.initial_equity) : null;
  const curve =
    equityMode === "completed_trade"
      ? snapshot?.equity_completed
      : snapshot?.equity_cashflow;
  const series = equitySeries(curve, initial);
  const ddSeries = (dd?.series ?? []).map((p) => -Math.abs(Number(p.drawdown)));

  return (
    <div className="space-y-3 rounded-lg border border-terminal-border bg-terminal-panel p-4">
      <div>
        <h2 className="font-display text-sm font-semibold text-terminal-text">
          Historical Performance Analytics
        </h2>
        <p className="mt-1 text-[11px] font-medium uppercase tracking-[0.12em] text-amber-300/90">
          HISTORICAL BACKTEST — SIMULATED RESULTS — NOT FINANCIAL ADVICE
        </p>
        <p className="mt-1 text-[11px] text-terminal-muted">
          Analytics {snapshot?.analytics_version ?? "—"} · cost model{" "}
          {summary?.cost_model_version ?? "—"} · initial equity{" "}
          {summary?.initial_equity_source ?? "not_configured"}
          {summary?.initial_equity != null ? ` (${fmtNum(summary.initial_equity)})` : ""}
        </p>
      </div>

      {!snapshot ? (
        <p className="text-xs text-terminal-muted">
          {busy ? "Updating analytics…" : "No analytics snapshot yet."}
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
            <Stat label="Net P&L" value={fmtNum(profit?.total_net_realized_pnl)} tone="accent" />
            <Stat label="Gross P&L" value={fmtNum(profit?.total_gross_realized_pnl)} />
            <Stat label="Win Rate" value={fmtMetric(stats?.win_rate)} />
            <Stat label="Profit Factor" value={fmtMetric(profit?.profit_factor)} />
            <Stat
              label="Max Drawdown"
              value={dd?.available ? fmtNum(dd.max_drawdown) : "N/A"}
            />
            <Stat label="Completed" value={String(stats?.completed_trades ?? 0)} />
            <Stat label="Exec Costs" value={fmtNum(profit?.total_execution_costs)} />
            <Stat
              label="Avg Net Trade"
              value={fmtMetric(profit?.average_net_pnl_per_completed)}
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded border border-terminal-border/70 p-2">
              <div className="mb-1 flex items-center justify-between gap-2">
                <p className="text-[11px] font-medium text-terminal-muted">Equity curve</p>
                <select
                  className="rounded border border-terminal-border bg-terminal-surface px-1.5 py-0.5 text-[11px]"
                  value={equityMode}
                  onChange={(e) =>
                    setEquityMode(e.target.value as "completed_trade" | "realized_cashflow")
                  }
                >
                  <option value="completed_trade">Completed-trade</option>
                  <option value="realized_cashflow">Cash-flow</option>
                </select>
              </div>
              <Sparkline values={series} color="#2dd4bf" />
              <p className="mt-1 text-[10px] text-terminal-muted">
                Ending {curve?.ending_equity != null ? fmtNum(curve.ending_equity) : "N/A"} · cum
                net {fmtNum(curve?.cumulative_net_pnl)}
              </p>
            </div>
            <div className="rounded border border-terminal-border/70 p-2">
              <p className="mb-1 text-[11px] font-medium text-terminal-muted">Drawdown</p>
              {dd?.available ? (
                <>
                  <Sparkline values={ddSeries.length ? ddSeries : [0]} color="#f87171" />
                  <p className="mt-1 text-[10px] text-terminal-muted">
                    Max {fmtNum(dd.max_drawdown)} ({fmtMetric(dd.max_drawdown_pct)}%) · current{" "}
                    {fmtNum(dd.current_drawdown)}
                  </p>
                </>
              ) : (
                <p className="py-6 text-center text-[11px] text-terminal-muted">
                  {dd?.unavailable_reason ?? "N/A"}
                </p>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
            <Stat label="Wins" value={String(stats?.winning_trades ?? 0)} />
            <Stat label="Losses" value={String(stats?.losing_trades ?? 0)} />
            <Stat label="Break-even" value={String(stats?.break_even_trades ?? 0)} />
            <Stat label="Avg Win" value={fmtMetric(stats?.average_winning_trade)} />
            <Stat label="Avg Loss" value={fmtMetric(stats?.average_losing_trade)} />
            <Stat label="Best" value={fmtMetric(stats?.largest_winning_trade)} />
            <Stat label="Worst" value={fmtMetric(stats?.largest_losing_trade)} />
            <Stat label="Avg R" value={fmtMetric(summary?.risk_reward.average_r_multiple)} />
          </div>

          <div className="grid gap-2 lg:grid-cols-2">
            <GroupTable title="By Direction" rows={snapshot.groups.by_direction} />
            <GroupTable title="By Symbol" rows={snapshot.groups.by_symbol} />
            <GroupTable title="By Exit Type" rows={snapshot.groups.by_exit_type} />
            <GroupTable title="By Period" rows={snapshot.groups.by_period} />
          </div>
          {snapshot.groups.timeframe_unavailable_reason ? (
            <p className="text-[11px] text-amber-300/90">
              {snapshot.groups.timeframe_unavailable_reason}
            </p>
          ) : null}

          <div className="overflow-x-auto rounded border border-terminal-border/70">
            <table className="min-w-full text-left text-[11px]">
              <thead className="bg-terminal-surface/80 text-terminal-muted">
                <tr>
                  <th className="px-2 py-1.5">Trade</th>
                  <th className="px-2 py-1.5">Dir</th>
                  <th className="px-2 py-1.5">Exit</th>
                  <th className="px-2 py-1.5">Net</th>
                  <th className="px-2 py-1.5">R</th>
                </tr>
              </thead>
              <tbody>
                {snapshot.completed_trades.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-2 py-3 text-terminal-muted">
                      No completed trades in analytics window.
                    </td>
                  </tr>
                ) : (
                  snapshot.completed_trades.map((t) => (
                    <tr key={t.trade_id} className="border-t border-terminal-border/40">
                      <td className="px-2 py-1.5 font-mono text-terminal-text">{t.trade_id}</td>
                      <td className="px-2 py-1.5">{t.direction}</td>
                      <td className="px-2 py-1.5">{t.exit_type}</td>
                      <td className="px-2 py-1.5">{fmtNum(t.net_realized_pnl)}</td>
                      <td className="px-2 py-1.5">
                        {t.r_multiple != null ? fmtNum(t.r_multiple) : "N/A"}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <p className="text-[11px] text-terminal-muted">
            Included completed {summary?.included_completed_trades ?? 0} · excluded open{" "}
            {summary?.excluded_open_trades ?? 0} · excluded partial{" "}
            {summary?.excluded_partial_trades ?? 0}
          </p>
          {(summary?.assumptions?.length || summary?.warnings?.length) ? (
            <ul className="space-y-1 text-[11px] text-amber-300/90">
              {(summary?.assumptions ?? []).slice(0, 4).map((a) => (
                <li key={a}>{a}</li>
              ))}
              {(summary?.warnings ?? []).slice(0, 4).map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          ) : null}
        </>
      )}

      {onSaveConfig ? (
        <div className="space-y-2 rounded border border-terminal-border/70 bg-terminal-surface/40 p-3 text-xs">
          <p className="font-medium text-terminal-muted">Analytics configuration</p>
          <label className="block">
            <span className="text-terminal-muted">Initial equity (optional)</span>
            <input
              className="mt-1 w-full rounded border border-terminal-border bg-terminal-panel px-2 py-1"
              value={initialEquity}
              onChange={(e) => setInitialEquity(e.target.value)}
              placeholder="Leave empty → % returns N/A"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy}
              className="rounded bg-terminal-accent/90 px-3 py-1.5 text-xs font-medium text-terminal-bg disabled:opacity-50"
              onClick={() =>
                onSaveConfig(
                  initialEquity.trim() === ""
                    ? { clear_initial_equity: true }
                    : { initial_equity: Number(initialEquity) },
                )
              }
            >
              Apply equity
            </button>
            {onFilter ? (
              <>
                <select
                  className="rounded border border-terminal-border bg-terminal-panel px-2 py-1"
                  value={directionFilter}
                  onChange={(e) => setDirectionFilter(e.target.value)}
                >
                  <option value="">All directions</option>
                  <option value="LONG">LONG</option>
                  <option value="SHORT">SHORT</option>
                </select>
                <button
                  type="button"
                  disabled={busy}
                  className="rounded border border-terminal-border px-3 py-1.5 text-xs disabled:opacity-50"
                  onClick={() => onFilter(directionFilter || null)}
                >
                  Apply filter
                </button>
              </>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "accent";
}) {
  return (
    <div className="rounded border border-terminal-border/60 bg-terminal-surface/30 px-2 py-1.5">
      <p className="text-[10px] uppercase tracking-wide text-terminal-muted">{label}</p>
      <p
        className={cn(
          "mt-0.5 font-mono text-sm",
          tone === "accent" ? "text-terminal-accent" : "text-terminal-text",
        )}
      >
        {value}
      </p>
    </div>
  );
}
