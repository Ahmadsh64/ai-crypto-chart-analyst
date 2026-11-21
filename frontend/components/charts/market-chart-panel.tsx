"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { format } from "date-fns";
import type { UTCTimestamp } from "lightweight-charts";
import { Maximize2, Minimize2 } from "lucide-react";
import {
  CandlestickChart,
  type CandlestickChartHandle,
  type ChartOverlaySeries,
  type LiquidityChartData,
  type ObFvgChartData,
  type StructureChartData,
} from "@/components/charts/candlestick-chart";
import type { Ref } from "react";
import {
  TradePlanChartControls,
  TradePlanChartLegend,
  TradePlanChartStatusBadge,
} from "@/components/charts/trade-plan-chart-overlay";
import { TradePlanMonitorPanel } from "@/components/charts/trade-plan-monitor-panel";
import type { StructureOverlayId } from "@/components/charts/structure-panel";
import type { LiquidityOverlayId } from "@/lib/liquidity-chart-overlays";
import type { ObFvgOverlayId } from "@/lib/ob-fvg-chart-overlays";
import {
  buildTradePlanChartVisuals,
  DEFAULT_TRADE_PLAN_CHART_TOGGLES,
  marketSelectionKey,
  resolvePlanChartStatus,
  resolveTradePlanVisualSource,
  type TradePlanChartToggleState,
  type TradePlanLegendModel,
  type TradePlanVisualSource,
} from "@/lib/trade-plan-chart-visuals";
import {
  approachingLineIdsFromMonitor,
  applyPlanLineHighlights,
  buildTradePlanMonitor,
  dedupeMonitorAlerts,
  planLevelLineId,
  resolveMarketFreshness,
  type MarketFreshness,
  type PlanLevelKind,
} from "@/lib/trade-plan-monitor";
import {
  useCandles,
  useDecision,
  useIndicators,
  useLiquidity,
  useMarketStructure,
  useObFvg,
  useTradePlan,
} from "@/hooks/use-market-data";
import {
  useLiveChartSubscription,
  useLiveDecisionSubscription,
  useLiveTradePlanSubscription,
} from "@/hooks/use-market-socket";
import {
  candleKey,
  decisionKey,
  indicatorKey,
  tickerKey,
  tradePlanKey,
  useLiveMarketStore,
} from "@/stores/live-market-store";
import { formatPct, formatPrice } from "@/utils/format";
import { cn } from "@/utils/cn";
import type { ExchangeId, IndicatorId, MarketType, Timeframe } from "@/types/api";

interface MarketChartPanelProps {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  timeframe: Timeframe;
  title?: string;
  heightClass?: string;
  limit?: number;
  chartOverlays?: IndicatorId[];
  structureOverlays?: StructureOverlayId[];
  liquidityOverlays?: LiquidityOverlayId[];
  obFvgOverlays?: ObFvgOverlayId[];
  /** Phase 5.3 — overlay planned Entry/SL/TP from Decision + Trade Plan. */
  enableTradePlanVisuals?: boolean;
  /** Optional external legend mirror (e.g. sidebar). */
  onTradePlanLegendChange?: (legend: TradePlanLegendModel) => void;
  /** Phase 5.4.2 — expose Lightweight Charts screenshot handle. */
  chartRef?: Ref<CandlestickChartHandle>;
}

export function MarketChartPanel({
  exchange,
  marketType,
  symbol,
  timeframe,
  title,
  heightClass = "h-[620px]",
  limit = 300,
  chartOverlays = [],
  structureOverlays = [],
  liquidityOverlays = [],
  obFvgOverlays = [],
  enableTradePlanVisuals = false,
  onTradePlanLegendChange,
  chartRef,
}: MarketChartPanelProps) {
  useLiveChartSubscription(exchange, marketType, symbol, timeframe);

  const panelRef = useRef<HTMLDivElement | null>(null);
  const [maximized, setMaximized] = useState(false);
  const [planToggles, setPlanToggles] = useState<TradePlanChartToggleState>(
    DEFAULT_TRADE_PLAN_CHART_TOGGLES,
  );
  /** LABELED_FIXTURE override for browser QA only — never live trading evidence. */
  const [qaFixtureSource, setQaFixtureSource] = useState<TradePlanVisualSource | null>(null);
  const [qaPriceOverride, setQaPriceOverride] = useState<number | null>(null);
  const [qaFreshnessOverride, setQaFreshnessOverride] = useState<MarketFreshness | null>(null);
  const [selectedLevel, setSelectedLevel] = useState<PlanLevelKind | null>(null);
  const [visibleAlerts, setVisibleAlerts] = useState<
    ReturnType<typeof buildTradePlanMonitor>["alerts"]
  >([]);
  const acceptedPlanRef = useRef<{ marketKey: string; analysisTimestamp: string | null } | null>(
    null,
  );
  const lastAppliedVisualsRef = useRef(
    buildTradePlanChartVisuals({ source: null }),
  );
  const alertFiredRef = useRef<Set<string>>(new Set());
  const alertPlanKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!enableTradePlanVisuals || typeof window === "undefined") return;
    const api = {
      injectSource: (source: TradePlanVisualSource | null) => {
        setQaFixtureSource(source);
      },
      setPrice: (price: number | null) => setQaPriceOverride(price),
      setFreshness: (freshness: MarketFreshness | null) => setQaFreshnessOverride(freshness),
      setToggles: (next: TradePlanChartToggleState) => setPlanToggles(next),
      clear: () => {
        setQaFixtureSource(null);
        setQaPriceOverride(null);
        setQaFreshnessOverride(null);
      },
      label: "LABELED_FIXTURE — TEST DATA — NOT LIVE TRADING EVIDENCE",
    };
    (window as unknown as { __PHASE53_TRADE_PLAN_QA__?: typeof api }).__PHASE53_TRADE_PLAN_QA__ =
      api;
    return () => {
      delete (window as unknown as { __PHASE53_TRADE_PLAN_QA__?: typeof api })
        .__PHASE53_TRADE_PLAN_QA__;
    };
  }, [enableTradePlanVisuals]);

  // Clear selection / alert dedupe when market selection changes.
  useEffect(() => {
    setSelectedLevel(null);
    setVisibleAlerts([]);
    alertFiredRef.current = new Set();
    alertPlanKeyRef.current = null;
  }, [exchange, marketType, symbol]);

  // Historical seed only — no short polling interval for live prices.
  const candles = useCandles({
    exchange,
    marketType,
    symbol,
    timeframe,
    limit,
    refetchInterval: false,
  });

  const overlayQuery = useIndicators({
    exchange,
    marketType,
    symbol,
    timeframe,
    indicators: chartOverlays.join(","),
    includeForming: false,
    includeSeries: true,
    limit,
    enabled: chartOverlays.length > 0,
  });

  const structureQuery = useMarketStructure({
    exchange,
    marketType,
    symbol,
    timeframe,
    limit,
    includeUnconfirmed: false,
    enabled: structureOverlays.length > 0,
  });

  const liquidityQuery = useLiquidity({
    exchange,
    marketType,
    symbol,
    timeframe,
    limit,
    includeUnconfirmed: false,
    enabled: liquidityOverlays.length > 0,
  });

  const obFvgQuery = useObFvg({
    exchange,
    marketType,
    symbol,
    timeframe,
    limit,
    includeUnconfirmed: false,
    enabled: obFvgOverlays.some((id) => id !== "recentZones"),
  });

  useLiveTradePlanSubscription(exchange, marketType, symbol, enableTradePlanVisuals);
  useLiveDecisionSubscription(exchange, marketType, symbol, enableTradePlanVisuals);
  const tradePlanQuery = useTradePlan({
    exchange,
    marketType,
    symbol,
    enabled: enableTradePlanVisuals,
  });
  const decisionQuery = useDecision({
    exchange,
    marketType,
    symbol,
    enabled: enableTradePlanVisuals,
  });
  const liveTradePlan = useLiveMarketStore(
    (s) => s.tradePlan[tradePlanKey(exchange, marketType, symbol)],
  );
  const liveDecision = useLiveMarketStore(
    (s) => s.decision[decisionKey(exchange, marketType, symbol)],
  );

  const liveTicker = useLiveMarketStore(
    (s) => s.tickers[tickerKey(exchange, marketType, symbol)],
  );
  const liveCandle = useLiveMarketStore(
    (s) => s.candles[candleKey(exchange, marketType, symbol, timeframe)],
  );
  const liveStructure = useLiveMarketStore(
    (s) => s.structure[indicatorKey(exchange, marketType, symbol, timeframe)],
  );
  const liveLiquidity = useLiveMarketStore(
    (s) => s.liquidity[indicatorKey(exchange, marketType, symbol, timeframe)],
  );
  const liveObFvg = useLiveMarketStore(
    (s) => s.obFvg[indicatorKey(exchange, marketType, symbol, timeframe)],
  );
  const connectionStatus = useLiveMarketStore((s) => s.connectionStatus);

  const seriesMatchesSelection =
    candles.isSuccess &&
    candles.data?.exchange === exchange &&
    candles.data?.market_type === marketType &&
    candles.data?.symbol === symbol &&
    candles.data?.timeframe === timeframe;

  const last =
    liveTicker?.last ??
    liveCandle?.close ??
    candles.data?.latest_price ??
    (seriesMatchesSelection ? candles.data?.candles.at(-1)?.close : undefined);

  const change = liveTicker?.changePct24h;
  const updatedAt =
    liveTicker?.processedAt ?? liveCandle?.processedAt ?? candles.data?.last_updated;
  const isLive = liveTicker?.source === "websocket" || Boolean(liveCandle);

  const overlays: ChartOverlaySeries[] = chartOverlays
    .map((id) => {
      const series = overlayQuery.data?.series?.[id];
      if (!series) return null;
      return { id, series };
    })
    .filter((x): x is ChartOverlaySeries => x != null);

  const structureData: StructureChartData | null =
    structureOverlays.length === 0
      ? null
      : {
          swings: liveStructure?.swings ?? structureQuery.data?.swings ?? [],
          bosEvents: liveStructure?.bosEvents ?? structureQuery.data?.bos_events ?? [],
          chochEvents: liveStructure?.chochEvents ?? structureQuery.data?.choch_events ?? [],
          mssEvents: liveStructure?.mssEvents ?? structureQuery.data?.mss_events ?? [],
        };

  const liquidityData: LiquidityChartData | null =
    liquidityOverlays.length === 0
      ? null
      : {
          eqhClusters: liveLiquidity?.eqhClusters ?? liquidityQuery.data?.eqh_clusters ?? [],
          eqlClusters: liveLiquidity?.eqlClusters ?? liquidityQuery.data?.eql_clusters ?? [],
          bslLevels: liveLiquidity?.bslLevels ?? liquidityQuery.data?.bsl_levels ?? [],
          sslLevels: liveLiquidity?.sslLevels ?? liquidityQuery.data?.ssl_levels ?? [],
          sweeps: liveLiquidity?.sweeps ?? liquidityQuery.data?.sweeps ?? [],
        };

  const showObFvg = obFvgOverlays.some((id) => id !== "recentZones");
  const obFvgData: ObFvgChartData | null = !showObFvg
    ? null
    : {
        bullishOrderBlocks:
          liveObFvg?.bullishOrderBlocks ?? obFvgQuery.data?.bullish_order_blocks ?? [],
        bearishOrderBlocks:
          liveObFvg?.bearishOrderBlocks ?? obFvgQuery.data?.bearish_order_blocks ?? [],
        bullishFvgs: liveObFvg?.bullishFvgs ?? obFvgQuery.data?.bullish_fvgs ?? [],
        bearishFvgs: liveObFvg?.bearishFvgs ?? obFvgQuery.data?.bearish_fvgs ?? [],
      };

  const expectedMarketKey = marketSelectionKey(exchange, marketType, symbol);

  // Reset accepted watermark when market selection changes so new symbol/exchange wins.
  useEffect(() => {
    acceptedPlanRef.current = { marketKey: expectedMarketKey, analysisTimestamp: null };
  }, [expectedMarketKey]);

  const planVisuals = useMemo(() => {
    if (!enableTradePlanVisuals) {
      const cleared = buildTradePlanChartVisuals({ source: null });
      lastAppliedVisualsRef.current = cleared;
      return cleared;
    }

    const source =
      qaFixtureSource ??
      resolveTradePlanVisualSource({
        exchange,
        marketType,
        symbol,
        restPlan: tradePlanQuery.data ?? null,
        livePlan: liveTradePlan ?? null,
        restDecision: decisionQuery.data ?? null,
        liveDecision: liveDecision ?? null,
      });

    const candleRows = seriesMatchesSelection ? (candles.data?.candles ?? []) : [];
    const firstTs = candleRows[0]?.timestamp;
    const lastTs = candleRows.at(-1)?.timestamp;
    const zoneStart = firstTs
      ? (Math.floor(new Date(firstTs).getTime() / 1000) as UTCTimestamp)
      : null;
    const zoneEnd = lastTs
      ? (Math.floor(new Date(lastTs).getTime() / 1000) as UTCTimestamp)
      : null;

    const accepted = acceptedPlanRef.current;
    const visuals = buildTradePlanChartVisuals({
      source,
      toggles: planToggles,
      zoneStart,
      zoneEnd,
      expectedMarketKey,
      // QA fixtures always apply; live path uses analysis_timestamp watermark.
      acceptedAnalysisTimestamp:
        qaFixtureSource != null
          ? null
          : accepted && accepted.marketKey === expectedMarketKey
            ? accepted.analysisTimestamp
            : null,
    });

    if (!visuals.applied) {
      // Outdated payload — keep last applied levels for this market.
      return lastAppliedVisualsRef.current;
    }

    acceptedPlanRef.current = {
      marketKey: expectedMarketKey,
      analysisTimestamp: visuals.analysisTimestamp,
    };
    lastAppliedVisualsRef.current = visuals;
    return visuals;
  }, [
    enableTradePlanVisuals,
    exchange,
    marketType,
    symbol,
    tradePlanQuery.data,
    liveTradePlan,
    decisionQuery.data,
    liveDecision,
    qaFixtureSource,
    seriesMatchesSelection,
    candles.data?.candles,
    planToggles,
    expectedMarketKey,
  ]);

  useEffect(() => {
    if (!enableTradePlanVisuals || !onTradePlanLegendChange) return;
    onTradePlanLegendChange(planVisuals.legend);
  }, [enableTradePlanVisuals, onTradePlanLegendChange, planVisuals.legend]);

  const monitorSource = useMemo(() => {
    if (!enableTradePlanVisuals) return null;
    if (qaFixtureSource) return qaFixtureSource;
    return resolveTradePlanVisualSource({
      exchange,
      marketType,
      symbol,
      restPlan: tradePlanQuery.data ?? null,
      livePlan: liveTradePlan ?? null,
      restDecision: decisionQuery.data ?? null,
      liveDecision: liveDecision ?? null,
    });
  }, [
    enableTradePlanVisuals,
    qaFixtureSource,
    exchange,
    marketType,
    symbol,
    tradePlanQuery.data,
    liveTradePlan,
    decisionQuery.data,
    liveDecision,
  ]);

  const monitorPrice =
    qaPriceOverride != null && Number.isFinite(qaPriceOverride)
      ? qaPriceOverride
      : typeof last === "number" && Number.isFinite(last)
        ? last
        : null;

  const marketFreshness = useMemo(() => {
    if (qaFreshnessOverride) return qaFreshnessOverride;
    return resolveMarketFreshness({
      connectionStatus,
      processedAt: updatedAt ?? null,
      hasPrice: monitorPrice != null,
      source: liveTicker?.source ?? (isLive ? "websocket" : "rest-fallback"),
    });
  }, [
    qaFreshnessOverride,
    connectionStatus,
    updatedAt,
    monitorPrice,
    liveTicker?.source,
    isLive,
  ]);

  const monitorBase = useMemo(() => {
    if (!enableTradePlanVisuals) {
      return buildTradePlanMonitor({
        source: null,
        currentPrice: null,
        freshness: "UNAVAILABLE",
        planActive: false,
      });
    }

    const status = resolvePlanChartStatus(monitorSource);
    const planActive =
      status !== "NO TRADE" &&
      status !== "PLAN UNAVAILABLE" &&
      monitorSource != null &&
      (monitorSource.marketKey === expectedMarketKey);

    const candleRows = seriesMatchesSelection ? (candles.data?.candles ?? []) : [];
    const closedCandles = candleRows.map((c) => ({
      timestamp: c.timestamp,
      high: c.high,
      low: c.low,
      isClosed: c.is_closed,
    }));
    const formingCandle =
      liveCandle &&
      liveCandle.exchange === exchange &&
      liveCandle.marketType === marketType &&
      liveCandle.symbol.toUpperCase() === symbol.toUpperCase()
        ? {
            timestamp: liveCandle.timestamp,
            high: liveCandle.high,
            low: liveCandle.low,
            isClosed: liveCandle.isClosed,
          }
        : null;

    return buildTradePlanMonitor({
      source: monitorSource,
      currentPrice: monitorPrice,
      freshness: marketFreshness,
      formingCandle,
      closedCandles,
      planActive,
    });
  }, [
    enableTradePlanVisuals,
    monitorSource,
    expectedMarketKey,
    seriesMatchesSelection,
    candles.data?.candles,
    liveCandle,
    exchange,
    marketType,
    symbol,
    monitorPrice,
    marketFreshness,
  ]);

  // Alert dedupe + reset when plan identity changes.
  useEffect(() => {
    if (!enableTradePlanVisuals) {
      setVisibleAlerts([]);
      return;
    }
    const planKey = `${monitorSource?.marketKey ?? ""}|${monitorSource?.planId ?? ""}|${monitorSource?.decisionId ?? ""}|${monitorSource?.analysisTimestamp ?? ""}`;
    if (alertPlanKeyRef.current !== planKey) {
      alertPlanKeyRef.current = planKey;
      alertFiredRef.current = new Set();
      setVisibleAlerts([]);
    }
    if (!monitorBase.active) {
      setVisibleAlerts([]);
      alertFiredRef.current = new Set();
      return;
    }
    const { visible, nextFired } = dedupeMonitorAlerts(
      monitorBase.alerts,
      alertFiredRef.current,
    );
    alertFiredRef.current = nextFired;
    if (visible.length) {
      setVisibleAlerts((prev) => {
        const ids = new Set(prev.map((a) => a.id));
        const merged = [...prev];
        for (const a of visible) {
          if (!ids.has(a.id)) merged.push(a);
        }
        return merged.slice(-8);
      });
    }
  }, [enableTradePlanVisuals, monitorBase, monitorSource]);

  // Active proximity badges come from current metrics; visibleAlerts tracks first-fire only.
  const monitor = useMemo(() => {
    const activeIds = new Set(monitorBase.alerts.map((a) => a.id));
    const sticky = visibleAlerts.filter((a) => activeIds.has(a.id));
    const merged = [...monitorBase.alerts];
    for (const a of sticky) {
      if (!merged.some((m) => m.id === a.id)) merged.push(a);
    }
    return { ...monitorBase, alerts: merged };
  }, [monitorBase, visibleAlerts]);

  const planRef =
    monitorSource?.planId ?? monitorSource?.decisionId ?? planVisuals.legend.planId ?? "plan";
  const selectedLineId =
    selectedLevel && monitor.active ? planLevelLineId(planRef, selectedLevel) : null;
  const approachIdsKey = useMemo(() => {
    const ids = approachingLineIdsFromMonitor(monitor, planRef);
    return [...ids].sort().join("|");
  }, [monitor, planRef]);
  const displayPriceLines = useMemo(
    () =>
      applyPlanLineHighlights(planVisuals.priceLines, {
        selectedLineId,
        approachingLineIds: approachIdsKey ? approachIdsKey.split("|") : [],
      }),
    [planVisuals.priceLines, selectedLineId, approachIdsKey],
  );
  const selectedLineLabel =
    displayPriceLines.find((l) => l.id === selectedLineId)?.title ?? null;

  const toggleMaximize = useCallback(async () => {
    const el = panelRef.current;
    if (!el) return;
    try {
      if (!document.fullscreenElement) {
        await el.requestFullscreen();
      } else {
        await document.exitFullscreen();
      }
    } catch {
      setMaximized((v) => !v);
    }
  }, []);

  useEffect(() => {
    const onFs = () => setMaximized(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onFs);
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);

  return (
    <div
      ref={panelRef}
      className={cn(
        "flex flex-col rounded-lg border border-terminal-border bg-terminal-panel",
        maximized && "h-full min-h-[70vh] rounded-none bg-terminal-bg",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-terminal-border px-4 py-3">
        <div>
          <h3 className="text-sm font-medium text-terminal-text">
            {title ?? `${symbol} · ${timeframe}`}
          </h3>
          <p className="text-xs capitalize text-terminal-muted">
            {exchange} · {marketType.replaceAll("_", " ")} · stream {connectionStatus}
          </p>
          {enableTradePlanVisuals ? (
            <div className="mt-2">
              <TradePlanChartStatusBadge status={planVisuals.status} />
            </div>
          ) : null}
        </div>
        <div className="flex items-start gap-3">
          <div className="text-right">
            <p
              className={cn(
                "font-mono text-lg font-semibold transition-colors",
                liveTicker?.direction === "up" && "text-terminal-long",
                liveTicker?.direction === "down" && "text-terminal-short",
                (!liveTicker || liveTicker.direction === "flat") && "text-terminal-text",
              )}
            >
              {formatPrice(last)}
            </p>
            <p
              className={cn(
                "text-xs font-medium",
                change != null && change >= 0 ? "text-terminal-long" : "text-terminal-short",
              )}
            >
              24h {formatPct(change)}
            </p>
            <p className="mt-0.5 text-[10px] text-terminal-muted">
              {isLive ? "LIVE" : "REST seed"}
              {updatedAt ? ` · ${format(new Date(updatedAt), "HH:mm:ss")}` : ""}
              {liveCandle && !liveCandle.isClosed ? " · forming" : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void toggleMaximize()}
            className="rounded border border-terminal-border p-1.5 text-terminal-muted transition hover:border-terminal-accent/50 hover:text-terminal-accent"
            title={maximized ? "Exit fullscreen" : "Maximize chart"}
            aria-label={maximized ? "Exit fullscreen" : "Maximize chart"}
          >
            {maximized ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </button>
        </div>
      </div>

      <div
        className={cn(
          "relative w-full",
          maximized ? "min-h-0 flex-1 h-[calc(100dvh-5rem)]" : heightClass,
        )}
      >
        {candles.isLoading ? (
          <div className="flex h-full items-center justify-center text-sm text-terminal-muted">
            Loading candles…
          </div>
        ) : candles.isError ? (
          <div className="flex h-full items-center justify-center px-6 text-center text-sm text-terminal-short">
            {(candles.error as Error).message || "Failed to load market data"}
          </div>
        ) : seriesMatchesSelection && candles.data?.candles?.length ? (
          <CandlestickChart
            ref={chartRef}
            seriesKey={`${exchange}:${marketType}:${symbol}:${timeframe}`}
            candles={candles.data.candles}
            liveCandle={liveCandle}
            overlays={overlays}
            structure={structureData}
            structureOverlays={structureOverlays}
            liquidity={liquidityData}
            liquidityOverlays={liquidityOverlays}
            obFvg={obFvgData}
            obFvgOverlays={obFvgOverlays}
            tradePriceLines={enableTradePlanVisuals ? displayPriceLines : []}
            planZones={enableTradePlanVisuals ? planVisuals.zones : []}
            className="h-full w-full"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-terminal-muted">
            No candle data
          </div>
        )}
      </div>

      {enableTradePlanVisuals ? (
        <div className="space-y-3 border-t border-terminal-border px-4 py-3">
          {qaFixtureSource || qaPriceOverride != null || qaFreshnessOverride ? (
            <p className="rounded border border-amber-400/40 bg-amber-400/10 px-2 py-1 text-[10px] font-medium uppercase tracking-wide text-amber-200">
              LABELED_FIXTURE — TEST DATA — NOT LIVE TRADING EVIDENCE
            </p>
          ) : null}
          <TradePlanMonitorPanel
            monitor={monitor}
            selectedLevel={selectedLevel}
            onSelectLevel={setSelectedLevel}
            selectedLineLabel={selectedLineLabel}
          />
          <TradePlanChartControls
            toggles={planToggles}
            onChange={setPlanToggles}
            disabled={!seriesMatchesSelection}
          />
          <TradePlanChartLegend legend={planVisuals.legend} currentPrice={monitorPrice} />
        </div>
      ) : null}
    </div>
  );
}
