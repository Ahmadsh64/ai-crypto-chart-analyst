"use client";

import Link from "next/link";
import { ArrowRight, Target } from "lucide-react";
import { DecisionPanel } from "@/components/charts/decision-panel";
import { MarketChartPanel } from "@/components/charts/market-chart-panel";
import { TradePlanPanel } from "@/components/charts/trade-plan-panel";
import { StreamStatusBadge } from "@/components/common/stream-status";
import { MarketControls } from "@/components/trading/market-controls";
import { useMarketStore } from "@/stores/market-store";

/**
 * Focused Phase 4.3 / 4.4 workspace: entry / SL / TP / sizing + decision.
 * Deep Vision / full SMC stay on AI Market Analyzer (protected layout).
 */
export function TradeSetupsPage() {
  const { exchange, marketType, symbol, timeframe } = useMarketStore();

  return (
    <div className="space-y-4 p-4 md:p-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Target className="h-5 w-5 text-terminal-accent" strokeWidth={1.75} />
            <h1 className="font-display text-2xl font-semibold text-terminal-text">
              Trade Setups
            </h1>
          </div>
          <p className="mt-1 max-w-2xl text-sm text-terminal-muted">
            Structured LONG / SHORT plans with entry, stop, targets, and risk sizing.
            Analysis only — levels are hypothetical, not fills.
          </p>
          <div className="mt-2">
            <StreamStatusBadge exchange={exchange} />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="rounded-lg border border-terminal-border bg-terminal-panel p-3">
            <MarketControls compact />
          </div>
          <Link
            href={`/chart-analyzer?symbol=${encodeURIComponent(symbol)}`}
            className="inline-flex items-center gap-2 rounded-md bg-terminal-accent px-4 py-2 text-sm font-medium text-terminal-bg transition hover:bg-terminal-accent/90"
          >
            Open in AI Market Analyzer
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(320px,0.9fr)]">
        <MarketChartPanel
          exchange={exchange}
          marketType={marketType}
          symbol={symbol}
          timeframe={timeframe}
          heightClass="h-[480px]"
          enableTradePlanVisuals
        />
        <div className="space-y-4">
          <DecisionPanel exchange={exchange} marketType={marketType} symbol={symbol} />
          <TradePlanPanel exchange={exchange} marketType={marketType} symbol={symbol} />
        </div>
      </div>
    </div>
  );
}
