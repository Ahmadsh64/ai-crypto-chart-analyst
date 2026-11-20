"use client";

import { useMemo, useState } from "react";
import { useTradePlan } from "@/hooks/use-market-data";
import { useLiveTradePlanSubscription } from "@/hooks/use-market-socket";
import { tradePlanKey, useLiveMarketStore } from "@/stores/live-market-store";
import { cn } from "@/utils/cn";
import type { ExchangeId, MarketType, PlanStatus } from "@/types/api";

interface TradePlanPanelProps {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
}

function statusTone(status?: PlanStatus | null) {
  if (status === "eligible") return "border-terminal-long/50 text-terminal-long";
  if (status === "invalid") return "border-amber-400/50 text-amber-300";
  return "border-terminal-border text-terminal-muted";
}

function fmt(n: number | null | undefined, digits = 2) {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function TradePlanPanel({ exchange, marketType, symbol }: TradePlanPanelProps) {
  const [balanceInput, setBalanceInput] = useState("10000");
  const [riskInput, setRiskInput] = useState("1");

  const accountBalance = useMemo(() => {
    const n = Number(balanceInput);
    return Number.isFinite(n) && n > 0 ? n : undefined;
  }, [balanceInput]);
  const riskPercent = useMemo(() => {
    const n = Number(riskInput);
    return Number.isFinite(n) && n > 0 && n <= 5 ? n : undefined;
  }, [riskInput]);

  useLiveTradePlanSubscription(
    exchange,
    marketType,
    symbol,
    true,
    accountBalance,
    riskPercent,
  );
  const query = useTradePlan({
    exchange,
    marketType,
    symbol,
    accountBalance,
    riskPercent,
  });
  const live = useLiveMarketStore(
    (s) => s.tradePlan[tradePlanKey(exchange, marketType, symbol)],
  );

  const status = live?.planStatus ?? query.data?.plan_status;
  const direction = live?.direction ?? query.data?.direction;
  const entry = live?.entry ?? query.data?.entry;
  const stop = live?.stopLoss ?? query.data?.stop_loss;
  const targets = live?.takeProfitTargets ?? query.data?.take_profit_targets ?? [];
  const risk = live?.risk ?? query.data?.risk;
  const sizing = live?.positionSizing ?? query.data?.position_sizing;
  const validation = live?.validation ?? query.data?.validation;
  const eligibility = live?.eligibility ?? query.data?.eligibility;
  const invalidation =
    live?.invalidationConditions ?? query.data?.invalidation_conditions ?? [];
  const explanations = live?.explanations ?? query.data?.explanations ?? [];
  const version = live?.configurationVersion ?? query.data?.configuration_version;
  const disclaimer =
    live?.analysisOnlyDisclaimer ??
    query.data?.analysis_only_disclaimer ??
    "Analysis only — no orders are executed. Prices are analytical levels, not guaranteed fills.";
  const spotWarning = live?.spotShortWarning ?? query.data?.spot_short_warning;
  const source = live ? "live" : query.isLoading ? "loading" : "rest";

  return (
    <div className="space-y-3 rounded-lg border border-terminal-border bg-terminal-panel p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
            Trade Plan
          </h3>
          <p className="mt-1 text-[11px] text-terminal-muted">
            {source === "loading"
              ? "Loading…"
              : source === "live"
                ? "Live · confirmed candles"
                : "REST seed"}
            {version ? ` · ${version}` : ""}
          </p>
        </div>
        <span
          className={cn(
            "rounded border px-2 py-0.5 text-[10px] uppercase tracking-wide",
            statusTone(status),
          )}
        >
          {status ?? "—"}
          {direction ? ` · ${direction}` : ""}
        </span>
      </div>

      <p className="rounded border border-terminal-border/70 bg-terminal-surface/60 px-2 py-1.5 text-[10px] text-terminal-muted">
        {disclaimer}
      </p>
      {spotWarning ? (
        <p className="rounded border border-amber-400/40 bg-amber-400/5 px-2 py-1.5 text-[10px] text-amber-200">
          {spotWarning}
        </p>
      ) : null}

      <div className="grid grid-cols-2 gap-2">
        <label className="space-y-1 text-[10px] uppercase tracking-wide text-terminal-muted">
          Virtual balance
          <input
            className="w-full rounded border border-terminal-border bg-terminal-surface px-2 py-1.5 font-mono text-[12px] text-terminal-text"
            value={balanceInput}
            onChange={(e) => setBalanceInput(e.target.value)}
            inputMode="decimal"
          />
        </label>
        <label className="space-y-1 text-[10px] uppercase tracking-wide text-terminal-muted">
          Risk %
          <input
            className="w-full rounded border border-terminal-border bg-terminal-surface px-2 py-1.5 font-mono text-[12px] text-terminal-text"
            value={riskInput}
            onChange={(e) => setRiskInput(e.target.value)}
            inputMode="decimal"
          />
        </label>
      </div>
      <p className="text-[10px] text-terminal-muted">
        Balance and sizing are hypothetical. No exchange balances are retrieved.
      </p>

      {query.isError ? (
        <p className="text-[11px] text-terminal-short">
          {(query.error as Error).message || "Trade plan error"}
        </p>
      ) : null}

      {status !== "eligible" ? (
        <div className="space-y-1 border-t border-terminal-border/60 pt-2">
          <p className="text-[10px] uppercase tracking-wide text-terminal-muted">
            Blocking reasons
          </p>
          <ul className="max-h-28 space-y-1 overflow-y-auto text-[11px] text-terminal-text">
            {(validation?.blocking_reasons?.length
              ? validation.blocking_reasons
              : eligibility?.blocking_reasons ?? ["Waiting for strong confluence."]
            ).map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {entry ? (
        <div className="space-y-1 border-t border-terminal-border/60 pt-2">
          <p className="text-[10px] uppercase tracking-wide text-terminal-muted">Entry zone</p>
          <p className="font-mono text-[12px] text-terminal-text">
            {fmt(entry.entry_low, 4)} – {fmt(entry.entry_high, 4)} · ref{" "}
            {fmt(entry.entry_reference_price, 4)}
          </p>
          <p className="text-[11px] text-terminal-muted">
            {entry.entry_type} · {entry.entry_source}
          </p>
          <p className="text-[11px] text-terminal-text">{entry.entry_explanation}</p>
        </div>
      ) : null}

      {stop ? (
        <div className="space-y-1 border-t border-terminal-border/60 pt-2">
          <p className="text-[10px] uppercase tracking-wide text-terminal-muted">Stop loss</p>
          <p className="font-mono text-[12px] text-terminal-short">
            {fmt(stop.stop_loss_price, 4)} · dist {fmt(stop.stop_loss_distance, 4)} (
            {fmt(stop.stop_loss_distance_pct, 2)}%)
          </p>
          <p className="text-[11px] text-terminal-muted">{stop.stop_loss_source}</p>
          <p className="text-[11px] text-terminal-text">{stop.invalidation_explanation}</p>
        </div>
      ) : null}

      {targets.length ? (
        <div className="space-y-1 border-t border-terminal-border/60 pt-2">
          <p className="text-[10px] uppercase tracking-wide text-terminal-muted">
            Take profits
          </p>
          {targets.map((t) => (
            <div key={t.label} className="flex items-baseline justify-between gap-2 text-[11px]">
              <span className="font-mono text-terminal-long">
                {t.label} {fmt(t.price, 4)}
              </span>
              <span className="text-terminal-muted">
                RR {fmt(t.risk_reward_ratio, 2)} · {t.source}
              </span>
            </div>
          ))}
        </div>
      ) : null}

      {risk ? (
        <div className="space-y-1 border-t border-terminal-border/60 pt-2">
          <p className="text-[10px] uppercase tracking-wide text-terminal-muted">Risk / reward</p>
          <p className="font-mono text-[12px] text-terminal-text">
            Primary RR {fmt(risk.primary_rr, 2)} · min {fmt(risk.minimum_required_rr, 2)}
          </p>
        </div>
      ) : null}

      {sizing ? (
        <div className="space-y-1 border-t border-terminal-border/60 pt-2">
          <p className="text-[10px] uppercase tracking-wide text-terminal-muted">
            Hypothetical sizing
          </p>
          <p className="font-mono text-[12px] text-terminal-text">
            Risk {fmt(sizing.risk_amount, 2)} ({fmt(sizing.risk_percent, 2)}%) · size{" "}
            {fmt(sizing.position_size, 6)} · notional {fmt(sizing.position_notional, 2)}
          </p>
          <p className="text-[11px] text-terminal-muted">{sizing.sizing_explanation}</p>
        </div>
      ) : null}

      {invalidation.length ? (
        <div className="space-y-1 border-t border-terminal-border/60 pt-2">
          <p className="text-[10px] uppercase tracking-wide text-terminal-muted">
            Invalidation
          </p>
          <ul className="max-h-24 space-y-1 overflow-y-auto text-[11px]">
            {invalidation.map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {validation?.warnings?.length ? (
        <div className="space-y-1 border-t border-terminal-border/60 pt-2">
          <p className="text-[10px] uppercase tracking-wide text-amber-300/90">Warnings</p>
          <ul className="space-y-1 text-[11px] text-amber-200/90">
            {validation.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {explanations.length && status === "eligible" ? (
        <div className="space-y-1 border-t border-terminal-border/60 pt-2">
          <p className="text-[10px] uppercase tracking-wide text-terminal-muted">Explanation</p>
          <p className="text-[11px] text-terminal-text">{explanations[0]}</p>
        </div>
      ) : null}
    </div>
  );
}
