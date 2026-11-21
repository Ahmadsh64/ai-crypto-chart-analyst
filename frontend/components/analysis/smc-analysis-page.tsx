"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Layers } from "lucide-react";
import { IndicatorsPanel } from "@/components/charts/indicators-panel";
import { LiquidityPanel } from "@/components/charts/liquidity-panel";
import { MarketChartPanel } from "@/components/charts/market-chart-panel";
import { MtfOverviewPanel } from "@/components/charts/mtf-overview-panel";
import { ObFvgPanel } from "@/components/charts/ob-fvg-panel";
import {
  StructurePanel,
  type StructureOverlayId,
} from "@/components/charts/structure-panel";
import { StreamStatusBadge } from "@/components/common/stream-status";
import { MarketControls } from "@/components/trading/market-controls";
import type { LiquidityOverlayId } from "@/lib/liquidity-chart-overlays";
import type { ObFvgOverlayId } from "@/lib/ob-fvg-chart-overlays";
import { useMarketStore } from "@/stores/market-store";
import type { IndicatorId } from "@/types/api";

const DEFAULT_STRUCTURE: StructureOverlayId[] = ["swings", "bos", "choch", "mss"];
const DEFAULT_LIQUIDITY: LiquidityOverlayId[] = ["eqh", "eql", "bsl", "ssl", "sweeps"];
const DEFAULT_OB_FVG: ObFvgOverlayId[] = [
  "bullishOb",
  "bearishOb",
  "bullishFvg",
  "bearishFvg",
];
const DEFAULT_INDICATORS: IndicatorId[] = ["ema_20", "ema_50", "ema_200"];

/**
 * Phase 3 technical workspace — structure / liquidity / OB-FVG / indicators / MTF.
 * ICT sessions & kill zones are not implemented yet. Decision / Vision stay on Analyzer.
 */
export function SmcAnalysisPage() {
  const { exchange, marketType, symbol, timeframe } = useMarketStore();
  const [structureOverlays, setStructureOverlays] =
    useState<StructureOverlayId[]>(DEFAULT_STRUCTURE);
  const [liquidityOverlays, setLiquidityOverlays] =
    useState<LiquidityOverlayId[]>(DEFAULT_LIQUIDITY);
  const [obFvgOverlays, setObFvgOverlays] = useState<ObFvgOverlayId[]>(DEFAULT_OB_FVG);
  const [chartOverlays, setChartOverlays] = useState<IndicatorId[]>(DEFAULT_INDICATORS);

  return (
    <div className="space-y-4 p-4 md:p-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Layers className="h-5 w-5 text-terminal-accent" strokeWidth={1.75} />
            <h1 className="font-display text-2xl font-semibold text-terminal-text">
              SMC / ICT Analysis
            </h1>
          </div>
          <p className="mt-1 max-w-2xl text-sm text-terminal-muted">
            Market structure, liquidity, order blocks, FVGs, indicators, and MTF readiness.
            ICT sessions / kill zones are not implemented yet.
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

      <MarketChartPanel
        exchange={exchange}
        marketType={marketType}
        symbol={symbol}
        timeframe={timeframe}
        heightClass="h-[420px]"
        structureOverlays={structureOverlays}
        liquidityOverlays={liquidityOverlays}
        obFvgOverlays={obFvgOverlays}
        chartOverlays={chartOverlays}
      />

      <div className="grid gap-4 xl:grid-cols-2">
        <StructurePanel
          exchange={exchange}
          marketType={marketType}
          symbol={symbol}
          timeframe={timeframe}
          overlays={structureOverlays}
          onOverlaysChange={setStructureOverlays}
        />
        <LiquidityPanel
          exchange={exchange}
          marketType={marketType}
          symbol={symbol}
          timeframe={timeframe}
          overlays={liquidityOverlays}
          onOverlaysChange={setLiquidityOverlays}
        />
        <ObFvgPanel
          exchange={exchange}
          marketType={marketType}
          symbol={symbol}
          timeframe={timeframe}
          overlays={obFvgOverlays}
          onOverlaysChange={setObFvgOverlays}
        />
        <IndicatorsPanel
          exchange={exchange}
          marketType={marketType}
          symbol={symbol}
          timeframe={timeframe}
          chartOverlays={chartOverlays}
          onChartOverlaysChange={setChartOverlays}
        />
      </div>

      <MtfOverviewPanel exchange={exchange} marketType={marketType} symbol={symbol} />

      <p className="text-xs text-terminal-muted">
        For confluence scoring, final decision, and AI vision, use{" "}
        <Link href="/chart-analyzer" className="text-terminal-accent hover:underline">
          AI Market Analyzer
        </Link>
        . For entry / SL / TP plans, use{" "}
        <Link href="/trade-setups" className="text-terminal-accent hover:underline">
          Trade Setups
        </Link>
        .
      </p>
    </div>
  );
}
