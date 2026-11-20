"use client";

import { useMemo, useState } from "react";
import { useDecision } from "@/hooks/use-market-data";
import { useLiveDecisionSubscription } from "@/hooks/use-market-socket";
import { decisionKey, useLiveMarketStore } from "@/stores/live-market-store";
import { decisionLabel, decisionTone } from "@/lib/decision-display";
import { cn } from "@/utils/cn";
import type { ExchangeId, MarketType } from "@/types/api";

interface DecisionPanelProps {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
}

function fmt(n: number | null | undefined, digits = 2) {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function DecisionPanel({ exchange, marketType, symbol }: DecisionPanelProps) {
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

  useLiveDecisionSubscription(
    exchange,
    marketType,
    symbol,
    true,
    accountBalance,
    riskPercent,
  );
  const query = useDecision({
    exchange,
    marketType,
    symbol,
    accountBalance,
    riskPercent,
  });
  const live = useLiveMarketStore(
    (s) => s.decision[decisionKey(exchange, marketType, symbol)],
  );

  const decision = live?.decision ?? query.data?.decision;
  const reason = live?.decisionReason ?? query.data?.decision_reason;
  const lifecycle = live?.lifecycle ?? query.data?.lifecycle;
  const scores = live?.confluenceScores ?? query.data?.confluence_scores;
  const planStatus = live?.tradePlanStatus ?? query.data?.trade_plan_status;
  const confirm = live?.entryConfirmation ?? query.data?.entry_confirmation;
  const entry = live?.entryZoneSummary ?? query.data?.entry_zone_summary;
  const sl = live?.stopLossPrice ?? query.data?.stop_loss_price;
  const tps = live?.takeProfitPrices ?? query.data?.take_profit_prices ?? [];
  const rr = live?.primaryRr ?? query.data?.primary_rr;
  const riskAmt = live?.riskAmount ?? query.data?.risk_amount;
  const size = live?.positionSize ?? query.data?.position_size;
  const blockers = live?.blockingConditions ?? query.data?.blocking_conditions ?? [];
  const conflicts = live?.conflictIds ?? query.data?.conflict_ids ?? [];
  const spot = live?.spotRestriction ?? query.data?.spot_restriction;
  const disclaimer =
    live?.analysisOnlyDisclaimer ??
    query.data?.analysis_only_disclaimer ??
    "Analysis only — no orders are executed. Analytical conditions do not guarantee execution or profit.";
  const version = live?.configurationVersion ?? query.data?.configuration_version;
  const updated = live?.analysisTimestamp ?? query.data?.analysis_timestamp;
  const source = live ? "live" : query.isLoading ? "loading" : "rest";

  return (
    <div className="space-y-3 rounded-lg border border-terminal-border bg-terminal-panel p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
            Final Decision
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
            "rounded border px-2 py-1 text-[11px] font-semibold uppercase tracking-wide",
            decisionTone(decision),
          )}
        >
          {decisionLabel(decision)}
        </span>
      </div>

      <p className="rounded border border-terminal-border/70 bg-terminal-surface/60 px-2 py-1.5 text-[10px] text-terminal-muted">
        {disclaimer}
      </p>
      {spot ? (
        <p className="rounded border border-amber-400/40 bg-amber-400/5 px-2 py-1.5 text-[10px] text-amber-200">
          {spot}
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

      {query.isError ? (
        <p className="text-[11px] text-terminal-short">
          {(query.error as Error).message || "Decision error"}
        </p>
      ) : null}

      <div className="space-y-1 border-t border-terminal-border/60 pt-2">
        <p className="text-[10px] uppercase tracking-wide text-terminal-muted">Reason</p>
        <p className="text-[11px] text-terminal-text">{reason ?? "—"}</p>
      </div>

      <div className="grid grid-cols-2 gap-2 text-[11px]">
        <div className="rounded border border-terminal-border bg-terminal-surface/50 px-2 py-1.5">
          <p className="text-[10px] uppercase text-terminal-muted">Lifecycle</p>
          <p className="font-mono text-terminal-text">{lifecycle ?? "—"}</p>
        </div>
        <div className="rounded border border-terminal-border bg-terminal-surface/50 px-2 py-1.5">
          <p className="text-[10px] uppercase text-terminal-muted">Trade plan</p>
          <p className="font-mono text-terminal-text">{planStatus ?? "—"}</p>
        </div>
      </div>

      <div className="space-y-1">
        <p className="text-[10px] uppercase tracking-wide text-terminal-muted">
          Confluence scores
        </p>
        <p className="font-mono text-[12px] text-terminal-text">
          B {fmt(scores?.bullish_score, 1)} / S {fmt(scores?.bearish_score, 1)}
          {scores?.assessment_strength ? ` · ${scores.assessment_strength}` : ""}
        </p>
      </div>

      <div className="space-y-1 border-t border-terminal-border/60 pt-2">
        <p className="text-[10px] uppercase tracking-wide text-terminal-muted">
          Entry confirmation
        </p>
        <p className="text-[11px] text-terminal-text">
          {confirm?.status ?? "—"}
          {confirm?.confirmation_type ? ` · ${confirm.confirmation_type}` : ""}
        </p>
        <p className="text-[11px] text-terminal-muted">{confirm?.explanation}</p>
      </div>

      {entry ? (
        <div className="space-y-1 border-t border-terminal-border/60 pt-2">
          <p className="text-[10px] uppercase tracking-wide text-terminal-muted">Entry zone</p>
          <p className="font-mono text-[12px] text-terminal-text">
            {fmt(Number(entry.entry_low), 4)} – {fmt(Number(entry.entry_high), 4)} · ref{" "}
            {fmt(Number(entry.entry_reference_price), 4)}
          </p>
          <p className="text-[11px] text-terminal-muted">
            Inside zone: {String(entry.price_inside_zone ?? "—")}
          </p>
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-2 text-[11px]">
        <div>
          <p className="text-[10px] uppercase text-terminal-muted">Stop loss</p>
          <p className="font-mono text-terminal-short">{fmt(sl, 4)}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase text-terminal-muted">Primary RR</p>
          <p className="font-mono text-terminal-text">{fmt(rr, 2)}</p>
        </div>
      </div>

      {tps.length ? (
        <div className="space-y-0.5">
          <p className="text-[10px] uppercase text-terminal-muted">Take profits</p>
          <p className="font-mono text-[11px] text-terminal-long">
            {tps.map((p, i) => `TP${i + 1} ${fmt(p, 4)}`).join(" · ")}
          </p>
        </div>
      ) : null}

      <div className="space-y-1 border-t border-terminal-border/60 pt-2">
        <p className="text-[10px] uppercase tracking-wide text-terminal-muted">
          Hypothetical sizing
        </p>
        <p className="font-mono text-[12px] text-terminal-text">
          Risk {fmt(riskAmt, 2)} · size {fmt(size, 6)}
        </p>
      </div>

      {blockers.length ? (
        <div className="space-y-1 border-t border-terminal-border/60 pt-2">
          <p className="text-[10px] uppercase tracking-wide text-terminal-muted">
            Blocking conditions
          </p>
          <ul className="max-h-24 space-y-1 overflow-y-auto text-[11px]">
            {blockers.slice(0, 8).map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {conflicts.length ? (
        <div className="space-y-1">
          <p className="text-[10px] uppercase tracking-wide text-amber-300/90">Conflicts</p>
          <ul className="text-[11px] text-amber-200/90">
            {conflicts.slice(0, 4).map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="text-[10px] text-terminal-muted">
        Updated {updated ? new Date(updated).toLocaleString() : "—"}
      </p>
    </div>
  );
}
