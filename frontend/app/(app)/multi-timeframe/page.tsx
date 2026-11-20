"use client";

import { Activity } from "lucide-react";
import { MtfOverviewPanel } from "@/components/charts/mtf-overview-panel";
import { MarketControls } from "@/components/trading/market-controls";
import { useMarketStore } from "@/stores/market-store";

export default function MultiTimeframePage() {
  const { exchange, marketType, symbol } = useMarketStore();

  return (
    <div className="flex h-full min-h-[calc(100dvh-4rem)] flex-col gap-4 p-4 md:p-5">
      <div className="rounded-lg border border-terminal-border bg-terminal-panel p-4">
        <h1 className="flex items-center gap-2 font-display text-lg font-semibold text-terminal-text">
          <Activity className="h-5 w-5 text-terminal-accent" />
          Multi-Timeframe Data
        </h1>
        <p className="mt-1 text-xs text-terminal-muted">
          Phase 4.1 orchestration — 4H / 1H / 15M / 5M readiness only. No trade signals.
        </p>
        <div className="mt-4 max-w-xl">
          <MarketControls />
        </div>
      </div>

      <MtfOverviewPanel exchange={exchange} marketType={marketType} symbol={symbol} />
    </div>
  );
}
