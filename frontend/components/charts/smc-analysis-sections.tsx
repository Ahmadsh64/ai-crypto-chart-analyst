"use client";

import { useState, type ReactNode } from "react";
import { StructurePanel, type StructureOverlayId } from "@/components/charts/structure-panel";
import { LiquidityPanel } from "@/components/charts/liquidity-panel";
import type { LiquidityOverlayId } from "@/lib/liquidity-chart-overlays";
import { ObFvgPanel } from "@/components/charts/ob-fvg-panel";
import type { ObFvgOverlayId } from "@/lib/ob-fvg-chart-overlays";
import { MtfOverviewPanel } from "@/components/charts/mtf-overview-panel";
import { ConfluencePanel } from "@/components/charts/confluence-panel";
import { TradePlanPanel } from "@/components/charts/trade-plan-panel";
import { DecisionPanel } from "@/components/charts/decision-panel";
import { IndicatorsPanel } from "@/components/charts/indicators-panel";
import { SmcEvidencePanel } from "@/components/charts/market-analyzer-results";
import type {
  DecisionResponse,
  ExchangeId,
  IndicatorId,
  MarketType,
  AnalysisSnapshot,
  Timeframe,
} from "@/types/api";

function SmcSection({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <details
      className="group rounded-lg border border-terminal-border bg-terminal-panel open:shadow-[inset_0_1px_0_0_rgba(61,214,198,0.08)]"
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary className="cursor-pointer list-none px-4 py-3 marker:content-none [&::-webkit-details-marker]:hidden">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-terminal-text">{title}</p>
            {subtitle ? (
              <p className="mt-0.5 text-[11px] text-terminal-muted">{subtitle}</p>
            ) : null}
          </div>
          <span className="text-[10px] uppercase tracking-wide text-terminal-muted">
            {open ? "Collapse" : "Expand"}
          </span>
        </div>
      </summary>
      {open ? (
        <div className="space-y-3 border-t border-terminal-border px-3 pb-3 pt-3">{children}</div>
      ) : null}
    </details>
  );
}

interface SmcAnalysisSectionsProps {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  timeframe: Timeframe;
  structureOverlays: StructureOverlayId[];
  onStructureOverlaysChange: (ids: StructureOverlayId[]) => void;
  liquidityOverlays: LiquidityOverlayId[];
  onLiquidityOverlaysChange: (ids: LiquidityOverlayId[]) => void;
  obFvgOverlays: ObFvgOverlayId[];
  onObFvgOverlaysChange: (ids: ObFvgOverlayId[]) => void;
  chartOverlays: IndicatorId[];
  onChartOverlaysChange: (ids: IndicatorId[]) => void;
  decision?: DecisionResponse | null;
  snapshot?: AnalysisSnapshot | null;
}

export function SmcAnalysisSections({
  exchange,
  marketType,
  symbol,
  timeframe,
  structureOverlays,
  onStructureOverlaysChange,
  liquidityOverlays,
  onLiquidityOverlaysChange,
  obFvgOverlays,
  onObFvgOverlaysChange,
  chartOverlays,
  onChartOverlaysChange,
  decision,
  snapshot,
}: SmcAnalysisSectionsProps) {
  return (
    <div className="space-y-2" data-testid="smc-sections">
      <div className="px-0.5">
        <h3 className="text-[11px] uppercase tracking-[0.16em] text-terminal-muted">
          SMC analysis
        </h3>
        <p className="mt-1 text-xs text-terminal-muted">
          Detailed structure and confluence — market overview and trade levels stay above.
        </p>
      </div>

      <SmcSection
        title="1. Market structure"
        subtitle="Swings, BOS, CHOCH, MSS overlays"
      >
        <StructurePanel
          exchange={exchange}
          marketType={marketType}
          symbol={symbol}
          timeframe={timeframe}
          overlays={structureOverlays}
          onOverlaysChange={onStructureOverlaysChange}
        />
      </SmcSection>

      <SmcSection
        title="2. Liquidity analysis"
        subtitle="EQH / EQL, BSL / SSL, sweeps"
      >
        <LiquidityPanel
          exchange={exchange}
          marketType={marketType}
          symbol={symbol}
          timeframe={timeframe}
          overlays={liquidityOverlays}
          onOverlaysChange={onLiquidityOverlaysChange}
        />
      </SmcSection>

      <SmcSection title="3. Order blocks" subtitle="Bullish and bearish OB zones on chart">
        <ObFvgPanel
          exchange={exchange}
          marketType={marketType}
          symbol={symbol}
          timeframe={timeframe}
          overlays={obFvgOverlays}
          onOverlaysChange={onObFvgOverlaysChange}
        />
      </SmcSection>

      <SmcSection
        title="4. Fair value gaps"
        subtitle="Use Bull/Bear FVG toggles in Order Blocks above"
      >
        <p className="text-sm text-terminal-muted">
          Fair Value Gaps share the Order Blocks / FVG engine panel. Enable Bull FVG and Bear
          FVG overlays there — chart zones use exact deterministic engine prices.
        </p>
      </SmcSection>

      <SmcSection
        title="5. Premium / discount"
        subtitle="Relative to dealing range when engine exposes it"
      >
        <p className="text-sm text-terminal-muted">
          Premium / discount labeling is shown when available in confluence or MTF context.
          No synthetic premium/discount values are invented here.
        </p>
        <SmcEvidencePanel decision={decision} snapshot={snapshot} />
      </SmcSection>

      <SmcSection title="6. Multi-timeframe analysis" subtitle="HTF context through entry TF">
        <MtfOverviewPanel exchange={exchange} marketType={marketType} symbol={symbol} />
      </SmcSection>

      <SmcSection title="7. Confluence summary" subtitle="Weighted evidence scores">
        <ConfluencePanel exchange={exchange} marketType={marketType} symbol={symbol} />
      </SmcSection>

      <SmcSection
        title="Indicators & advanced plan"
        subtitle="EMA overlays, full trade plan and decision details"
      >
        <IndicatorsPanel
          exchange={exchange}
          marketType={marketType}
          symbol={symbol}
          timeframe={timeframe}
          chartOverlays={chartOverlays}
          onChartOverlaysChange={onChartOverlaysChange}
        />
        <TradePlanPanel exchange={exchange} marketType={marketType} symbol={symbol} />
        <DecisionPanel exchange={exchange} marketType={marketType} symbol={symbol} />
      </SmcSection>
    </div>
  );
}
