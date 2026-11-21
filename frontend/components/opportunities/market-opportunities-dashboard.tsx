"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { format } from "date-fns";
import { RefreshCw, Target } from "lucide-react";
import { api, ApiError } from "@/services/api";
import type {
  ExchangeId,
  MarketOpportunity,
  MarketType,
  OpportunityStatus,
  ScannerStatusPayload,
} from "@/types/api";
import {
  analyzerHref,
  isNonExecutableObservation,
  opportunityStatusLabel,
  opportunityStatusTone,
  plannedDirectionLabel,
} from "@/lib/opportunities-display";
import { decisionTone } from "@/lib/decision-display";
import { formatPrice } from "@/utils/format";
import { cn } from "@/utils/cn";

function fmtTs(value?: string | null): string {
  if (!value) return "—";
  try {
    return format(new Date(value), "HH:mm:ss");
  } catch {
    return "—";
  }
}

function Level({
  label,
  price,
  available,
  tone,
}: {
  label: string;
  price?: number | null;
  available?: boolean;
  tone?: string;
}) {
  const ok = available !== false && price != null;
  return (
    <div className="flex justify-between gap-2 text-xs">
      <span className="text-terminal-muted">{label}</span>
      <span className={cn("font-mono", ok ? tone || "text-terminal-text" : "text-terminal-muted")}>
        {ok ? formatPrice(price) : "Unavailable"}
      </span>
    </div>
  );
}

export function MarketOpportunitiesDashboard() {
  const [opportunities, setOpportunities] = useState<MarketOpportunity[]>([]);
  const [status, setStatus] = useState<ScannerStatusPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exchange, setExchange] = useState<ExchangeId | "">("");
  const [marketType, setMarketType] = useState<MarketType | "">("");
  const [direction, setDirection] = useState<"" | "LONG" | "SHORT">("");
  const [oppStatus, setOppStatus] = useState<OpportunityStatus | "">("");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<"rank" | "confluence" | "freshness" | "entry_distance">(
    "rank",
  );
  const [actionableOnly, setActionableOnly] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [list, st] = await Promise.all([
        api.opportunities({
          exchange: exchange || undefined,
          marketType: marketType || undefined,
          direction: direction || undefined,
          status: oppStatus || undefined,
          search: search || undefined,
          actionableOnly,
          sort,
          limit: 100,
        }),
        api.opportunitiesStatus(),
      ]);
      setOpportunities(list.opportunities);
      setStatus(st.status);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load opportunities");
    } finally {
      setLoading(false);
    }
  }, [exchange, marketType, direction, oppStatus, search, actionableOnly, sort]);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 30_000);
    return () => clearInterval(id);
  }, [load]);

  const refreshScan = async () => {
    setScanning(true);
    setError(null);
    try {
      await api.opportunitiesScan();
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  };

  const ready = opportunities.filter((o) => o.actionable && o.status === "READY");
  const other = opportunities.filter((o) => !(o.actionable && o.status === "READY"));

  return (
    <div className="space-y-4 p-4 md:p-5" data-testid="market-opportunities">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 font-display text-xl font-semibold text-terminal-text">
            <Target className="h-5 w-5 text-terminal-accent" />
            Market Opportunities
          </h1>
          <p className="mt-1 text-sm text-terminal-muted">
            Deterministic scanner across Binance and Bybit — analysis only, no order execution.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refreshScan()}
          disabled={scanning || status?.state === "scanning"}
          className={cn(
            "inline-flex h-10 items-center gap-2 rounded-md px-3 text-sm font-medium",
            scanning
              ? "cursor-not-allowed bg-terminal-accent/40 text-terminal-bg"
              : "bg-terminal-accent text-terminal-bg hover:opacity-90",
          )}
        >
          <RefreshCw className={cn("h-4 w-4", scanning && "animate-spin")} />
          {scanning || status?.state === "scanning" ? "Scanning…" : "Refresh scan"}
        </button>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        <Metric label="Pairs scanned" value={status?.pairs_scanned_total ?? "—"} />
        <Metric
          label="READY (actionable)"
          value={status?.ready_opportunities ?? "—"}
          hint="Entry-confirmed only"
        />
        <Metric
          label="WAITING confirmation"
          value={status?.waiting_opportunities ?? "—"}
          hint="Eligible plans pending entry"
        />
        <Metric label="Approaching entry" value={status?.approaching_opportunities ?? "—"} />
        <Metric
          label="READY LONG / SHORT"
          value={`${status?.long_opportunities ?? "—"} / ${status?.short_opportunities ?? "—"}`}
        />
        <Metric label="Monitored" value={status?.pairs_monitored ?? "—"} />
        <Metric label="Last scan" value={fmtTs(status?.last_successful_scan_at)} />
        <Metric label="Next refresh" value={fmtTs(status?.next_scan_at)} />
        <Metric
          label="Scanner"
          value={(status?.state || "—").toUpperCase()}
          hint={status?.message}
        />
      </section>

      <section className="flex flex-wrap gap-2 rounded-lg border border-terminal-border bg-terminal-panel p-3">
        <Select
          label="Exchange"
          value={exchange}
          onChange={(v) => setExchange(v as ExchangeId | "")}
          options={[
            ["", "All"],
            ["binance", "Binance"],
            ["bybit", "Bybit"],
          ]}
        />
        <Select
          label="Market"
          value={marketType}
          onChange={(v) => setMarketType(v as MarketType | "")}
          options={[
            ["", "All"],
            ["spot", "Spot"],
            ["usdt_m_futures", "Binance Futures"],
            ["linear_perpetual", "Bybit Linear"],
          ]}
        />
        <Select
          label="Direction"
          value={direction}
          onChange={(v) => setDirection(v as "" | "LONG" | "SHORT")}
          options={[
            ["", "All"],
            ["LONG", "LONG"],
            ["SHORT", "SHORT"],
          ]}
        />
        <Select
          label="Status"
          value={oppStatus}
          onChange={(v) => setOppStatus(v as OpportunityStatus | "")}
          options={[
            ["", "All"],
            ["READY", "Ready"],
            ["APPROACHING_ENTRY", "Approaching"],
            ["WAITING", "Waiting"],
            ["INVALIDATED", "Invalidated"],
            ["EXPIRED", "Expired"],
            ["DATA_UNAVAILABLE", "Data unavailable"],
          ]}
        />
        <Select
          label="Sort"
          value={sort}
          onChange={(v) => setSort(v as typeof sort)}
          options={[
            ["rank", "Rank"],
            ["confluence", "Confluence"],
            ["freshness", "Freshness"],
            ["entry_distance", "Entry distance"],
          ]}
        />
        <label className="flex items-end gap-2 pb-1 text-xs text-terminal-muted">
          <input
            type="checkbox"
            checked={actionableOnly}
            onChange={(e) => setActionableOnly(e.target.checked)}
          />
          READY only
        </label>
        <label className="min-w-[10rem] flex-1 space-y-1 text-[10px] uppercase tracking-wide text-terminal-muted">
          Search
          <input
            className="h-9 w-full rounded border border-terminal-border bg-terminal-surface px-2 text-sm text-terminal-text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="BTC/USDT"
          />
        </label>
      </section>

      {error ? <p className="text-sm text-terminal-short">{error}</p> : null}
      {loading ? (
        <p className="text-sm text-terminal-muted">Loading opportunities…</p>
      ) : null}

      {!loading && opportunities.length === 0 ? (
        <div className="rounded-lg border border-dashed border-terminal-border bg-terminal-panel p-8 text-center">
          <p className="text-sm text-terminal-muted">
            No opportunities for the current filters. Run a refresh scan or widen filters.
          </p>
        </div>
      ) : null}

      {ready.length > 0 ? (
        <section className="space-y-2">
          <h2 className="text-[11px] uppercase tracking-[0.16em] text-terminal-long">
            Actionable (READY)
          </h2>
          <div className="grid gap-3 lg:grid-cols-2">
            {ready.map((o) => (
              <OpportunityCard key={o.opportunity_id} opportunity={o} />
            ))}
          </div>
        </section>
      ) : null}

      {other.length > 0 ? (
        <section className="space-y-2">
          <h2 className="text-[11px] uppercase tracking-[0.16em] text-terminal-muted">
            Non-actionable / monitoring
          </h2>
          <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
            {other.map((o) => (
              <OpportunityCard key={o.opportunity_id} opportunity={o} muted />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-terminal-border bg-terminal-panel p-3">
      <p className="text-[10px] uppercase tracking-wide text-terminal-muted">{label}</p>
      <p className="mt-1 font-mono text-lg text-terminal-text">{value}</p>
      {hint ? <p className="mt-1 truncate text-[10px] text-terminal-muted">{hint}</p> : null}
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
}) {
  return (
    <label className="space-y-1 text-[10px] uppercase tracking-wide text-terminal-muted">
      {label}
      <select
        className="block h-9 rounded border border-terminal-border bg-terminal-surface px-2 text-sm text-terminal-text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map(([v, lab]) => (
          <option key={v || "all"} value={v}>
            {lab}
          </option>
        ))}
      </select>
    </label>
  );
}

function OpportunityCard({
  opportunity: o,
  muted,
}: {
  opportunity: MarketOpportunity;
  muted?: boolean;
}) {
  const href = analyzerHref({
    exchange: o.exchange,
    marketType: o.market_type,
    symbol: o.symbol,
    timeframe: o.timeframe,
  });
  const tp = (i: number) => o.take_profits.find((t) => t.label === `TP${i}`) || o.take_profits[i - 1];
  const planned = plannedDirectionLabel(o);
  const nonExec = isNonExecutableObservation(o);

  return (
    <article
      className={cn(
        "rounded-lg border border-terminal-border bg-terminal-panel p-4",
        muted && "opacity-90",
        nonExec && "border-amber-500/40",
        o.status === "READY" && o.actionable && "border-terminal-long/40",
      )}
      data-testid="opportunity-card"
      data-status={o.status}
      data-decision={o.decision ?? ""}
      data-planned-direction={planned ?? ""}
      data-actionable={o.actionable ? "true" : "false"}
      data-market-executable={o.market_executable === false ? "false" : "true"}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-display text-lg font-semibold text-terminal-text">
            {o.base}{" "}
            <span className="font-mono text-base text-terminal-accent">{o.symbol}</span>
          </p>
          <p className="text-xs capitalize text-terminal-muted">
            {o.exchange} · {o.market_type.replaceAll("_", " ")} · {o.timeframe}
          </p>
        </div>
        <div className="flex flex-wrap gap-1">
          <span
            className={cn(
              "rounded border px-2 py-0.5 text-[10px] font-medium uppercase",
              opportunityStatusTone(o.status),
            )}
          >
            {opportunityStatusLabel(o.status)}
          </span>
          {planned ? (
            <span
              className={cn(
                "rounded border px-2 py-0.5 text-[10px] font-semibold uppercase",
                planned === "LONG" ? "border-terminal-long/40 text-terminal-long" : "border-terminal-short/40 text-terminal-short",
              )}
            >
              Planned {planned}
            </span>
          ) : null}
          {o.decision ? (
            <span
              className={cn(
                "rounded border px-2 py-0.5 text-[10px] font-semibold uppercase",
                decisionTone(o.decision),
              )}
            >
              Decision {o.decision}
            </span>
          ) : null}
          {o.actionable ? (
            <span className="rounded border border-terminal-long/50 px-2 py-0.5 text-[10px] font-medium uppercase text-terminal-long">
              Actionable
            </span>
          ) : (
            <span className="rounded border border-terminal-border px-2 py-0.5 text-[10px] font-medium uppercase text-terminal-muted">
              Not actionable
            </span>
          )}
          {nonExec ? (
            <span className="rounded border border-amber-400/50 px-2 py-0.5 text-[10px] font-medium uppercase text-amber-200">
              Non-executable on Spot
            </span>
          ) : null}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="text-[10px] uppercase text-terminal-muted">Live price</p>
          <p className="font-mono text-xl text-terminal-accent">{formatPrice(o.current_price)}</p>
          <p className="text-[10px] text-terminal-muted">
            {fmtTs(o.price_updated_at)} · {o.price_source}
          </p>
        </div>
        <div className="text-right text-xs text-terminal-muted">
          <p>Confluence {o.confluence_score != null ? o.confluence_score.toFixed(1) : "—"}</p>
          <p>
            B {o.confluence_bullish?.toFixed(1) ?? "—"} / S {o.confluence_bearish?.toFixed(1) ?? "—"}
          </p>
          <p>R:R {o.primary_rr != null ? o.primary_rr.toFixed(2) : "Unavailable"}</p>
        </div>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <div className="space-y-1 rounded border border-terminal-border/60 bg-terminal-surface/40 p-2">
          <Level
            label="Entry"
            price={o.entry_reference}
            available={o.entry_reference != null}
            tone="text-sky-300"
          />
          {o.entry_low != null && o.entry_high != null ? (
            <p className="font-mono text-[10px] text-sky-300/80">
              Zone {formatPrice(o.entry_low)} – {formatPrice(o.entry_high)}
            </p>
          ) : null}
          <Level label="Stop Loss" price={o.stop_loss} available={o.stop_loss != null} tone="text-terminal-short" />
          <Level
            label="Exit / Invalidation"
            price={o.stop_loss}
            available={o.stop_loss != null}
            tone="text-terminal-short"
          />
        </div>
        <div className="space-y-1 rounded border border-terminal-border/60 bg-terminal-surface/40 p-2">
          <Level label="TP1" price={tp(1)?.price} available={tp(1)?.available} tone="text-terminal-long" />
          <Level label="TP2" price={tp(2)?.price} available={tp(2)?.available} tone="text-terminal-long" />
          <Level label="TP3" price={tp(3)?.price} available={tp(3)?.available} tone="text-terminal-long" />
        </div>
      </div>

      {o.executability_note ? (
        <p className="mt-2 text-xs text-amber-200/90">{o.executability_note}</p>
      ) : null}
      <p className="mt-2 line-clamp-3 text-xs text-terminal-muted">{o.decision_reason || "—"}</p>
      {o.blocking_conditions[0] ? (
        <p className="mt-1 line-clamp-2 text-[11px] text-amber-100/80">
          Blocker: {o.blocking_conditions[0]}
        </p>
      ) : null}
      {o.supporting_evidence[0] ? (
        <p className="mt-1 line-clamp-2 text-[11px] text-terminal-text">
          {o.supporting_evidence[0]}
        </p>
      ) : null}
      <p className="mt-2 text-[10px] text-terminal-muted">
        Analyzed {fmtTs(o.analysis_timestamp)} · {o.planned_not_fills_note}
      </p>

      <Link
        href={href}
        className="mt-3 inline-flex h-9 items-center rounded-md border border-terminal-accent/50 px-3 text-sm text-terminal-accent hover:bg-terminal-accent/10"
      >
        Open Full Analysis
      </Link>
    </article>
  );
}
