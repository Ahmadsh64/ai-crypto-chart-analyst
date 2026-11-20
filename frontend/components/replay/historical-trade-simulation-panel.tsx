"use client";

import { useState } from "react";
import { formatReplayClock } from "@/lib/replay-display";
import type { SimulatedTrade, SimulationSnapshot } from "@/types/api";
import { cn } from "@/utils/cn";

interface HistoricalTradeSimulationPanelProps {
  snapshot: SimulationSnapshot | null;
  enabled: boolean;
  busy?: boolean;
  onSelectTrade?: (trade: SimulatedTrade) => void;
}

export function HistoricalTradeSimulationPanel({
  snapshot,
  enabled,
  busy = false,
  onSelectTrade,
}: HistoricalTradeSimulationPanelProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (!enabled) {
    return (
      <div className="rounded-lg border border-terminal-border bg-terminal-panel p-4 text-sm text-terminal-muted">
        Historical trade simulation is off. Enable it to track hypothetical entries and exits from
        historical decisions.
      </div>
    );
  }

  const overview = snapshot?.overview;
  const trades = snapshot?.trades ?? [];
  const selected = trades.find((t) => t.trade_id === selectedId) ?? trades[0] ?? null;

  return (
    <div className="space-y-3 rounded-lg border border-terminal-border bg-terminal-panel p-4">
      <div>
        <h2 className="font-display text-sm font-semibold text-terminal-text">
          Historical Trade Simulation
        </h2>
        <p className="mt-1 text-[11px] font-medium uppercase tracking-[0.14em] text-amber-300/90">
          HISTORICAL SIMULATION — NOT REAL ORDERS
        </p>
        <p className="mt-1 text-[11px] text-terminal-muted">
          Counts only — no fees, P&amp;L, or performance metrics in this phase.
        </p>
      </div>

      {!snapshot ? (
        <p className="text-xs text-terminal-muted">
          {busy ? "Updating simulation…" : "No simulation snapshot yet."}
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
            <Stat label="Pending" value={overview?.pending_count ?? 0} />
            <Stat label="Open" value={overview?.open_count ?? 0} />
            <Stat label="Partial" value={overview?.partially_closed_count ?? 0} />
            <Stat label="Closed" value={overview?.closed_count ?? 0} />
            <Stat label="Rejected" value={overview?.rejected_count ?? 0} />
            <Stat label="Ambiguous" value={overview?.ambiguous_count ?? 0} />
          </div>

          <div className="overflow-x-auto rounded border border-terminal-border/70">
            <table className="min-w-full text-left text-[11px]">
              <thead className="bg-terminal-surface/80 text-terminal-muted">
                <tr>
                  <th className="px-2 py-1.5 font-medium">ID</th>
                  <th className="px-2 py-1.5 font-medium">Dir</th>
                  <th className="px-2 py-1.5 font-medium">Decision</th>
                  <th className="px-2 py-1.5 font-medium">Entry</th>
                  <th className="px-2 py-1.5 font-medium">SL</th>
                  <th className="px-2 py-1.5 font-medium">TP</th>
                  <th className="px-2 py-1.5 font-medium">Qty left</th>
                  <th className="px-2 py-1.5 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {trades.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-2 py-3 text-terminal-muted">
                      No simulated trades yet.
                    </td>
                  </tr>
                ) : (
                  trades.map((t) => (
                    <tr
                      key={t.trade_id}
                      className={cn(
                        "cursor-pointer border-t border-terminal-border/50 hover:bg-terminal-surface/50",
                        selected?.trade_id === t.trade_id && "bg-terminal-accent/10",
                      )}
                      onClick={() => {
                        setSelectedId(t.trade_id);
                        onSelectTrade?.(t);
                      }}
                    >
                      <td className="px-2 py-1.5 font-mono text-terminal-text">
                        {t.trade_id.slice(0, 10)}
                      </td>
                      <td
                        className={cn(
                          "px-2 py-1.5 font-semibold",
                          t.direction === "LONG" ? "text-terminal-long" : "text-terminal-short",
                        )}
                      >
                        {t.direction}
                      </td>
                      <td className="px-2 py-1.5 text-terminal-muted">
                        {formatReplayClock(t.decision_timestamp)}
                      </td>
                      <td className="px-2 py-1.5 text-terminal-text">
                        {t.entry_price != null ? t.entry_price : "—"}
                      </td>
                      <td className="px-2 py-1.5 text-terminal-text">{t.current_stop_loss}</td>
                      <td className="px-2 py-1.5 text-terminal-text">
                        {t.take_profit_levels.join(", ") || "—"}
                      </td>
                      <td className="px-2 py-1.5 text-terminal-text">{t.remaining_quantity}</td>
                      <td className="px-2 py-1.5 text-terminal-muted">{t.lifecycle_status}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {selected ? <TradeDetail trade={selected} /> : null}
        </>
      )}
    </div>
  );
}

function TradeDetail({ trade }: { trade: SimulatedTrade }) {
  return (
    <div className="space-y-2 rounded border border-terminal-border/70 bg-terminal-surface/50 p-3 text-xs">
      <p className="text-[11px] uppercase tracking-[0.12em] text-terminal-muted">Trade detail</p>
      <p className="text-terminal-text">
        {trade.symbol} · {trade.direction} · {trade.decision}
      </p>
      <p className="text-terminal-muted">Decision: {formatReplayClock(trade.decision_timestamp)}</p>
      <p className="text-terminal-muted">
        Entry:{" "}
        {trade.entry_timestamp
          ? `${formatReplayClock(trade.entry_timestamp)} @ ${trade.entry_price}`
          : "pending / not filled"}
      </p>
      <p className="text-terminal-muted">
        Limit {trade.entry_limit_price ?? "—"} · SL {trade.current_stop_loss} · TP{" "}
        {trade.take_profit_levels.join(", ") || "—"}
      </p>
      <p className="text-terminal-muted">
        Qty original {trade.original_quantity} · remaining {trade.remaining_quantity} · TP closed{" "}
        {trade.quantity_closed_tp} · SL closed {trade.quantity_closed_sl}
      </p>
      {trade.rejection_reason ? (
        <p className="text-terminal-short">Rejected: {trade.rejection_reason}</p>
      ) : null}
      {trade.ambiguity_warnings.length ? (
        <ul className="space-y-1 text-amber-300/90">
          {trade.ambiguity_warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      ) : null}
      <div className="space-y-1">
        <p className="text-[11px] uppercase tracking-[0.12em] text-terminal-muted">Events</p>
        {trade.execution_events.length === 0 ? (
          <p className="text-terminal-muted">No events yet.</p>
        ) : (
          trade.execution_events.map((ev) => (
            <div key={ev.event_id} className="rounded border border-terminal-border/40 px-2 py-1">
              <span className="font-medium text-terminal-text">{ev.event_type}</span>
              <span className="text-terminal-muted">
                {" "}
                · {formatReplayClock(ev.timestamp)}
                {ev.price != null ? ` · ${ev.price}` : ""}
                {ev.quantity != null ? ` · qty ${ev.quantity}` : ""}
              </span>
              {ev.reason ? <p className="text-terminal-muted">{ev.reason}</p> : null}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border border-terminal-border/60 bg-terminal-surface/40 px-2 py-1.5">
      <p className="text-[10px] uppercase tracking-[0.12em] text-terminal-muted">{label}</p>
      <p className="font-mono text-sm text-terminal-text">{value}</p>
    </div>
  );
}
