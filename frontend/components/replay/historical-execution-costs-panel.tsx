"use client";

import { useState } from "react";
import { formatReplayClock } from "@/lib/replay-display";
import type { CostSnapshot, ExecutionCostConfigPublic, LedgerEntry } from "@/types/api";
import { cn } from "@/utils/cn";

interface HistoricalExecutionCostsPanelProps {
  snapshot: CostSnapshot | null;
  enabled: boolean;
  busy?: boolean;
  config?: ExecutionCostConfigPublic | null;
  onSaveConfig?: (patch: Partial<ExecutionCostConfigPublic>) => Promise<void>;
}

export function HistoricalExecutionCostsPanel({
  snapshot,
  enabled,
  busy = false,
  config,
  onSaveConfig,
}: HistoricalExecutionCostsPanelProps) {
  const [maker, setMaker] = useState(String(config?.maker_fee_rate ?? "0.001"));
  const [taker, setTaker] = useState(String(config?.taker_fee_rate ?? "0.001"));
  const [slipPolicy, setSlipPolicy] = useState(config?.slippage_policy ?? "fixed_bps");
  const [slipBps, setSlipBps] = useState(String(config?.slippage_bps ?? "1"));
  const [spreadPolicy, setSpreadPolicy] = useState(config?.spread_policy ?? "none");
  const [spreadBps, setSpreadBps] = useState(String(config?.spread_bps ?? "2"));
  const [fallback, setFallback] = useState(config?.maker_taker_fallback ?? "assume_taker");

  if (!enabled) {
    return (
      <div className="rounded-lg border border-terminal-border bg-terminal-panel p-4 text-sm text-terminal-muted">
        Execution cost modeling is off. Enable it to estimate fees, slippage, spread, and net P&amp;L
        from simulated fills.
      </div>
    );
  }

  const summary = snapshot?.summary;
  const ledger = snapshot?.recent_ledger ?? [];

  return (
    <div className="space-y-3 rounded-lg border border-terminal-border bg-terminal-panel p-4">
      <div>
        <h2 className="font-display text-sm font-semibold text-terminal-text">
          Historical Execution Costs
        </h2>
        <p className="mt-1 text-[11px] font-medium uppercase tracking-[0.12em] text-amber-300/90">
          HISTORICAL SIMULATION — NOT REAL EXECUTION — COSTS ARE ESTIMATED
        </p>
        <p className="mt-1 text-[11px] text-terminal-muted">
          Model {snapshot?.cost_model_version ?? "—"} · fee source{" "}
          {summary?.fee_config_source ?? "—"}
        </p>
      </div>

      {!snapshot ? (
        <p className="text-xs text-terminal-muted">
          {busy ? "Updating costs…" : "No cost snapshot yet."}
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
            <Stat label="Gross P&L" value={fmt(summary?.gross_realized_pnl)} tone="neutral" />
            <Stat label="Total Fees" value={fmt(summary?.total_fees)} />
            <Stat label="Slippage" value={fmt(summary?.total_slippage)} />
            <Stat label="Spread" value={fmt(summary?.total_spread_cost)} />
            <Stat label="Total Costs" value={fmt(summary?.total_costs)} />
            <Stat
              label="Net P&L"
              value={fmt(summary?.net_realized_pnl)}
              tone={num(summary?.net_realized_pnl) >= 0 ? "long" : "short"}
            />
          </div>

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

          <div className="overflow-x-auto rounded border border-terminal-border/70">
            <table className="min-w-full text-left text-[11px]">
              <thead className="bg-terminal-surface/80 text-terminal-muted">
                <tr>
                  <th className="px-2 py-1.5 font-medium">Time</th>
                  <th className="px-2 py-1.5 font-medium">Trade</th>
                  <th className="px-2 py-1.5 font-medium">Role</th>
                  <th className="px-2 py-1.5 font-medium">Side</th>
                  <th className="px-2 py-1.5 font-medium">Qty</th>
                  <th className="px-2 py-1.5 font-medium">Exec px</th>
                  <th className="px-2 py-1.5 font-medium">M/T</th>
                  <th className="px-2 py-1.5 font-medium">Fee</th>
                  <th className="px-2 py-1.5 font-medium">Slip</th>
                  <th className="px-2 py-1.5 font-medium">Spread</th>
                  <th className="px-2 py-1.5 font-medium">Net</th>
                </tr>
              </thead>
              <tbody>
                {ledger.length === 0 ? (
                  <tr>
                    <td colSpan={11} className="px-2 py-3 text-terminal-muted">
                      No ledger entries yet.
                    </td>
                  </tr>
                ) : (
                  ledger.map((e) => <LedgerRow key={e.execution_id} entry={e} />)
                )}
              </tbody>
            </table>
          </div>

          {onSaveConfig ? (
            <div className="space-y-2 rounded border border-terminal-border/70 bg-terminal-surface/40 p-3 text-xs">
              <p className="text-[11px] uppercase tracking-[0.12em] text-terminal-muted">
                Cost configuration
              </p>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Maker fee">
                  <input
                    value={maker}
                    onChange={(e) => setMaker(e.target.value)}
                    className="h-8 w-full rounded border border-terminal-border bg-terminal-panel px-2 text-terminal-text"
                  />
                </Field>
                <Field label="Taker fee">
                  <input
                    value={taker}
                    onChange={(e) => setTaker(e.target.value)}
                    className="h-8 w-full rounded border border-terminal-border bg-terminal-panel px-2 text-terminal-text"
                  />
                </Field>
                <Field label="Slippage model">
                  <select
                    value={slipPolicy}
                    onChange={(e) => setSlipPolicy(e.target.value)}
                    className="h-8 w-full rounded border border-terminal-border bg-terminal-panel px-2 text-terminal-text"
                  >
                    <option value="none">none</option>
                    <option value="fixed_bps">fixed_bps</option>
                    <option value="percentage">percentage</option>
                    <option value="conservative_ohlcv">conservative_ohlcv</option>
                  </select>
                </Field>
                <Field label="Slippage bps">
                  <input
                    value={slipBps}
                    onChange={(e) => setSlipBps(e.target.value)}
                    className="h-8 w-full rounded border border-terminal-border bg-terminal-panel px-2 text-terminal-text"
                  />
                </Field>
                <Field label="Spread model">
                  <select
                    value={spreadPolicy}
                    onChange={(e) => setSpreadPolicy(e.target.value)}
                    className="h-8 w-full rounded border border-terminal-border bg-terminal-panel px-2 text-terminal-text"
                  >
                    <option value="none">none</option>
                    <option value="fixed_bps">fixed_bps</option>
                    <option value="percentage">percentage</option>
                    <option value="synthetic_assumption">synthetic_assumption</option>
                  </select>
                </Field>
                <Field label="Spread bps">
                  <input
                    value={spreadBps}
                    onChange={(e) => setSpreadBps(e.target.value)}
                    className="h-8 w-full rounded border border-terminal-border bg-terminal-panel px-2 text-terminal-text"
                  />
                </Field>
                <Field label="M/T fallback">
                  <select
                    value={fallback}
                    onChange={(e) => setFallback(e.target.value)}
                    className="h-8 w-full rounded border border-terminal-border bg-terminal-panel px-2 text-terminal-text"
                  >
                    <option value="assume_taker">assume_taker</option>
                    <option value="assume_maker">assume_maker</option>
                    <option value="unknown">unknown</option>
                  </select>
                </Field>
              </div>
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  onSaveConfig({
                    maker_fee_rate: maker,
                    taker_fee_rate: taker,
                    slippage_policy: slipPolicy,
                    slippage_bps: slipBps,
                    spread_policy: spreadPolicy,
                    spread_bps: spreadBps,
                    maker_taker_fallback: fallback,
                  })
                }
                className="h-8 rounded border border-terminal-accent/40 bg-terminal-accent/15 px-3 text-terminal-accent disabled:opacity-50"
              >
                Apply & rebuild ledger
              </button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

function LedgerRow({ entry }: { entry: LedgerEntry }) {
  return (
    <tr className="border-t border-terminal-border/50 text-terminal-text">
      <td className="px-2 py-1.5 text-terminal-muted">{formatReplayClock(entry.event_timestamp)}</td>
      <td className="px-2 py-1.5 font-mono">{entry.trade_id.slice(0, 8)}</td>
      <td className="px-2 py-1.5">{entry.execution_role}</td>
      <td
        className={cn(
          "px-2 py-1.5 font-semibold",
          entry.direction === "LONG" ? "text-terminal-long" : "text-terminal-short",
        )}
      >
        {entry.direction}
      </td>
      <td className="px-2 py-1.5">{fmt(entry.executed_quantity)}</td>
      <td className="px-2 py-1.5">{fmt(entry.execution_price)}</td>
      <td className="px-2 py-1.5 text-terminal-muted">{entry.maker_taker}</td>
      <td className="px-2 py-1.5">{fmt(entry.fee_amount)}</td>
      <td className="px-2 py-1.5">{fmt(entry.slippage_amount)}</td>
      <td className="px-2 py-1.5">{fmt(entry.spread_cost)}</td>
      <td className="px-2 py-1.5">{entry.net_realized_pnl != null ? fmt(entry.net_realized_pnl) : "—"}</td>
    </tr>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-[10px] uppercase tracking-[0.12em] text-terminal-muted">{label}</span>
      {children}
    </label>
  );
}

function Stat({
  label,
  value,
  tone = "muted",
}: {
  label: string;
  value: string;
  tone?: "muted" | "neutral" | "long" | "short";
}) {
  return (
    <div className="rounded border border-terminal-border/60 bg-terminal-surface/40 px-2 py-1.5">
      <p className="text-[10px] uppercase tracking-[0.12em] text-terminal-muted">{label}</p>
      <p
        className={cn(
          "font-mono text-sm",
          tone === "long" && "text-terminal-long",
          tone === "short" && "text-terminal-short",
          tone === "neutral" && "text-terminal-text",
          tone === "muted" && "text-terminal-text",
        )}
      >
        {value}
      </p>
    </div>
  );
}

function fmt(v: string | number | null | undefined): string {
  if (v == null || v === "") return "—";
  const n = typeof v === "number" ? v : Number(v);
  if (Number.isFinite(n)) return n.toPrecision(6);
  return String(v);
}

function num(v: string | number | null | undefined): number {
  if (v == null) return 0;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
}
