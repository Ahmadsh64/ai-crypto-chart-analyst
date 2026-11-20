"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type AutoscaleInfo,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import type {
  Candle,
  CHoCHEvent,
  EqualExtremeCluster,
  IndicatorId,
  IndicatorSeriesResult,
  LiquidityLevel,
  LiquiditySweep,
  MSSEvent,
  StructureBreakEvent,
  SwingPoint,
} from "@/types/api";
import type { LiveCandle } from "@/stores/live-market-store";
import type { StructureOverlayId } from "@/components/charts/structure-panel";
import type { LiquidityOverlayId } from "@/lib/liquidity-chart-overlays";
import {
  mapLiquiditySegments,
  mapSweepMarkers,
} from "@/lib/liquidity-chart-overlays";
import type { ObFvgOverlayId } from "@/lib/ob-fvg-chart-overlays";
import { mapObFvgZones } from "@/lib/ob-fvg-chart-overlays";
import { ZonePrimitive, type ZoneDrawSpec } from "@/lib/zone-primitive";
import type { FairValueGap, OrderBlock } from "@/types/api";
import {
  applyLabelCollisionPolicy,
  assertNoDuplicateAnnotationIds,
  buildCandleTimeSet,
  collectAnnotationPrices,
  dedupePriceMarkers,
  mapBosMarkers,
  mapBosSegments,
  mapChochMarkers,
  mapChochSegments,
  mapMssMarkers,
  mapSwingMarkers,
  selectRecentSegments,
  toSegmentDrawSpecs,
} from "@/lib/structure-chart-overlays";
import { StructureSegmentPrimitive } from "@/lib/structure-segment-primitive";
import {
  buildCandleLookup,
  lookupCandleAtTimeSec,
  type OhlcHoverInfo,
} from "@/lib/ohlc-crosshair";
import type { TradeChartMarker, TradeChartPriceLine } from "@/lib/trade-chart-visuals";
import { formatPct, formatPrice, formatVolume } from "@/utils/format";
import { cn } from "@/utils/cn";
import type { IPriceLine, LineStyle } from "lightweight-charts";

export interface ChartOverlaySeries {
  id: IndicatorId;
  series: IndicatorSeriesResult;
}

export interface StructureChartData {
  swings: SwingPoint[];
  bosEvents: StructureBreakEvent[];
  chochEvents: CHoCHEvent[];
  mssEvents: MSSEvent[];
}

export interface LiquidityChartData {
  eqhClusters: EqualExtremeCluster[];
  eqlClusters: EqualExtremeCluster[];
  bslLevels: LiquidityLevel[];
  sslLevels: LiquidityLevel[];
  sweeps: LiquiditySweep[];
}

export interface ObFvgChartData {
  bullishOrderBlocks: OrderBlock[];
  bearishOrderBlocks: OrderBlock[];
  bullishFvgs: FairValueGap[];
  bearishFvgs: FairValueGap[];
}

interface CandlestickChartProps {
  candles: Candle[];
  liveCandle?: LiveCandle | null;
  className?: string;
  showVolume?: boolean;
  /** Reset historical series when the market selection changes. */
  seriesKey: string;
  overlays?: ChartOverlaySeries[];
  structure?: StructureChartData | null;
  structureOverlays?: StructureOverlayId[];
  liquidity?: LiquidityChartData | null;
  liquidityOverlays?: LiquidityOverlayId[];
  obFvg?: ObFvgChartData | null;
  obFvgOverlays?: ObFvgOverlayId[];
  /** Phase 5.2.8 — simulated trade markers (already clock-filtered). */
  tradeMarkers?: TradeChartMarker[];
  /** Phase 5.2.8 — planned Entry/SL/TP price lines (already clock-filtered). */
  tradePriceLines?: TradeChartPriceLine[];
  /** Phase 5.3 — risk/reward (or other) zones for live trade-plan visualization. */
  planZones?: ZoneDrawSpec[];
  /** Fired when the user clicks near a trade marker (marker id = event_id). */
  onTradeMarkerClick?: (markerId: string) => void;
}

const OVERLAY_COLORS: Record<string, string> = {
  ema_9: "#f59e0b",
  ema_20: "#3dd6c6",
  ema_50: "#60a5fa",
  ema_200: "#c084fc",
  bollinger_middle: "#94a3b8",
  bollinger_upper: "#64748b",
  bollinger_lower: "#64748b",
};

function toCandlePoint(c: Pick<Candle, "timestamp" | "open" | "high" | "low" | "close">) {
  return {
    time: Math.floor(new Date(c.timestamp).getTime() / 1000) as UTCTimestamp,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  };
}

function toVolumePoint(c: Pick<Candle, "timestamp" | "open" | "close" | "volume">) {
  return {
    time: Math.floor(new Date(c.timestamp).getTime() / 1000) as UTCTimestamp,
    value: c.volume,
    color: c.close >= c.open ? "rgba(34, 197, 94, 0.35)" : "rgba(239, 68, 68, 0.35)",
  };
}

function toLinePoints(
  series: IndicatorSeriesResult,
  field: string,
): { time: UTCTimestamp; value: number }[] {
  const out: { time: UTCTimestamp; value: number }[] = [];
  for (const point of series.points) {
    const raw = point.values[field];
    if (raw == null || Number.isNaN(raw)) continue;
    out.push({
      time: Math.floor(new Date(point.timestamp).getTime() / 1000) as UTCTimestamp,
      value: raw,
    });
  }
  return out;
}

function formatHoverTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().replace("T", " ").replace(/\.\d{3}Z$/, " UTC");
}

export function CandlestickChart({
  candles,
  liveCandle,
  className,
  showVolume = true,
  seriesKey,
  overlays = [],
  structure = null,
  structureOverlays = [],
  liquidity = null,
  liquidityOverlays = [],
  obFvg = null,
  obFvgOverlays = [],
  tradeMarkers = [],
  tradePriceLines = [],
  planZones = [],
  onTradeMarkerClick,
}: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const overlaySeriesRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const markersApiRef = useRef<{
    setMarkers: (markers: SeriesMarker<Time>[]) => void;
    detach: () => void;
  } | null>(null);
  const structurePrimitiveRef = useRef<StructureSegmentPrimitive | null>(null);
  const liquidityPrimitiveRef = useRef<StructureSegmentPrimitive | null>(null);
  const zonePrimitiveRef = useRef<ZonePrimitive | null>(null);
  const tradePriceLinesRef = useRef<Map<string, IPriceLine>>(new Map());
  const tradeMarkersRef = useRef<TradeChartMarker[]>([]);
  const onTradeMarkerClickRef = useRef(onTradeMarkerClick);
  const annotationPricesRef = useRef<number[]>([]);
  const candleLookupRef = useRef<Map<number, OhlcHoverInfo>>(new Map());
  const fittedKeyRef = useRef<string | null>(null);
  const [hover, setHover] = useState<OhlcHoverInfo | null>(null);

  useEffect(() => {
    onTradeMarkerClickRef.current = onTradeMarkerClick;
  }, [onTradeMarkerClick]);

  useEffect(() => {
    tradeMarkersRef.current = tradeMarkers;
  }, [tradeMarkers]);

  const candleLookup = useMemo(
    () => buildCandleLookup(candles, liveCandle),
    [candles, liveCandle],
  );

  useEffect(() => {
    candleLookupRef.current = candleLookup;
  }, [candleLookup]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#8b9bb0",
        fontFamily: "var(--font-ibm-plex-sans), sans-serif",
      },
      grid: {
        vertLines: { color: "rgba(36, 48, 65, 0.7)" },
        horzLines: { color: "rgba(36, 48, 65, 0.7)" },
      },
      rightPriceScale: { borderColor: "#243041", autoScale: true },
      timeScale: {
        borderColor: "#243041",
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: { color: "rgba(61, 214, 198, 0.45)", labelVisible: true },
        horzLine: { color: "rgba(61, 214, 198, 0.45)", labelVisible: true },
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
      autoscaleInfoProvider: (original: () => AutoscaleInfo | null) => {
        const base = original();
        if (!base?.priceRange) return base;
        const extras = annotationPricesRef.current;
        if (!extras.length) return base;
        let { minValue, maxValue } = base.priceRange;
        for (const p of extras) {
          if (!Number.isFinite(p)) continue;
          minValue = Math.min(minValue, p);
          maxValue = Math.max(maxValue, p);
        }
        const pad = (maxValue - minValue) * 0.02 || 0;
        return {
          ...base,
          priceRange: { minValue: minValue - pad, maxValue: maxValue + pad },
        };
      },
    });

    let volumeSeries: ISeriesApi<"Histogram"> | null = null;
    if (showVolume) {
      volumeSeries = chart.addSeries(HistogramSeries, {
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
      });
      chart.priceScale("volume").applyOptions({
        scaleMargins: { top: 0.8, bottom: 0 },
      });
      chart.priceScale("right").applyOptions({
        scaleMargins: { top: 0.08, bottom: 0.22 },
      });
    }

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;
    markersApiRef.current = createSeriesMarkers(candleSeries, []);

    const structurePrimitive = new StructureSegmentPrimitive();
    candleSeries.attachPrimitive(structurePrimitive);
    structurePrimitiveRef.current = structurePrimitive;
    const liquidityPrimitive = new StructureSegmentPrimitive();
    candleSeries.attachPrimitive(liquidityPrimitive);
    liquidityPrimitiveRef.current = liquidityPrimitive;
    const zonePrimitive = new ZonePrimitive();
    candleSeries.attachPrimitive(zonePrimitive);
    zonePrimitiveRef.current = zonePrimitive;

    const onCrosshair = (param: MouseEventParams<Time>) => {
      if (!param.time || param.point === undefined) {
        setHover(null);
        return;
      }
      const t = typeof param.time === "number" ? param.time : null;
      const info = lookupCandleAtTimeSec(candleLookupRef.current, t);
      setHover(info);
    };
    chart.subscribeCrosshairMove(onCrosshair);

    const onClick = (param: MouseEventParams<Time>) => {
      const handler = onTradeMarkerClickRef.current;
      if (!handler || param.point === undefined) return;
      const t = typeof param.time === "number" ? param.time : null;
      if (t == null) return;
      const yPrice = candleSeries.coordinateToPrice(param.point.y);
      if (yPrice == null || !Number.isFinite(yPrice)) return;
      const candidates = tradeMarkersRef.current.filter((m) => m.time === t);
      if (!candidates.length) return;
      let best = candidates[0]!;
      let bestDist = Math.abs(best.price - yPrice);
      for (const c of candidates.slice(1)) {
        const d = Math.abs(c.price - yPrice);
        if (d < bestDist) {
          best = c;
          bestDist = d;
        }
      }
      // Require a reasonable vertical proximity so OHLC clicks don't always select.
      const range = candleSeries.priceToCoordinate(yPrice);
      if (range == null) {
        handler(best.id);
        return;
      }
      const nearPx = candleSeries.priceToCoordinate(best.price);
      if (nearPx == null || Math.abs(nearPx - param.point.y) > 28) return;
      handler(best.id);
    };
    chart.subscribeClick(onClick);

    return () => {
      chart.unsubscribeCrosshairMove(onCrosshair);
      chart.unsubscribeClick(onClick);
      for (const line of tradePriceLinesRef.current.values()) {
        candleSeries.removePriceLine(line);
      }
      tradePriceLinesRef.current.clear();
      if (structurePrimitiveRef.current) {
        candleSeries.detachPrimitive(structurePrimitiveRef.current);
        structurePrimitiveRef.current = null;
      }
      if (liquidityPrimitiveRef.current) {
        candleSeries.detachPrimitive(liquidityPrimitiveRef.current);
        liquidityPrimitiveRef.current = null;
      }
      if (zonePrimitiveRef.current) {
        candleSeries.detachPrimitive(zonePrimitiveRef.current);
        zonePrimitiveRef.current = null;
      }
      markersApiRef.current?.detach();
      markersApiRef.current = null;
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      overlaySeriesRef.current.clear();
    };
  }, [showVolume]);

  // Historical REST seed — only when seriesKey / candles identity changes.
  useEffect(() => {
    if (!candleSeriesRef.current || candles.length === 0) return;

    candleSeriesRef.current.setData(candles.map(toCandlePoint));
    if (volumeSeriesRef.current) {
      volumeSeriesRef.current.setData(candles.map(toVolumePoint));
    }
    if (fittedKeyRef.current !== seriesKey) {
      chartRef.current?.timeScale().fitContent();
      fittedKeyRef.current = seriesKey;
    }
  }, [candles, seriesKey]);

  // Incremental live candle update — no full redraw.
  // Guard against out-of-order clock jumps (e.g. max-speed replay) that would
  // throw "Cannot update oldest data" from lightweight-charts.
  useEffect(() => {
    if (!liveCandle || !candleSeriesRef.current) return;
    const point = {
      timestamp: liveCandle.timestamp,
      open: liveCandle.open,
      high: liveCandle.high,
      low: liveCandle.low,
      close: liveCandle.close,
      volume: liveCandle.volume,
    };
    try {
      candleSeriesRef.current.update(toCandlePoint(point));
      volumeSeriesRef.current?.update(toVolumePoint(point));
    } catch {
      // Stale/out-of-order live candle — full setData path will resync.
    }
  }, [liveCandle]);

  // Indicator overlays (EMA / Bollinger) from backend series — never client-computed.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const wanted = new Map<string, { color: string; points: { time: UTCTimestamp; value: number }[] }>();
    for (const overlay of overlays) {
      if (overlay.id === "bollinger") {
        wanted.set("bollinger_upper", {
          color: OVERLAY_COLORS.bollinger_upper,
          points: toLinePoints(overlay.series, "upper"),
        });
        wanted.set("bollinger_middle", {
          color: OVERLAY_COLORS.bollinger_middle,
          points: toLinePoints(overlay.series, "middle"),
        });
        wanted.set("bollinger_lower", {
          color: OVERLAY_COLORS.bollinger_lower,
          points: toLinePoints(overlay.series, "lower"),
        });
      } else {
        wanted.set(overlay.id, {
          color: OVERLAY_COLORS[overlay.id] ?? "#3dd6c6",
          points: toLinePoints(overlay.series, "value"),
        });
      }
    }

    for (const [key, series] of overlaySeriesRef.current.entries()) {
      if (!wanted.has(key)) {
        chart.removeSeries(series);
        overlaySeriesRef.current.delete(key);
      }
    }

    for (const [key, spec] of wanted.entries()) {
      let line = overlaySeriesRef.current.get(key);
      if (!line) {
        line = chart.addSeries(LineSeries, {
          color: spec.color,
          lineWidth: key.startsWith("bollinger_") && key !== "bollinger_middle" ? 1 : 2,
          priceLineVisible: false,
          lastValueVisible: true,
          crosshairMarkerVisible: false,
        });
        overlaySeriesRef.current.set(key, line);
      } else {
        line.applyOptions({ color: spec.color });
      }
      line.setData(spec.points);
    }
  }, [overlays, seriesKey]);

  // Market structure + liquidity + OB/FVG + trade markers / primitives.
  useEffect(() => {
    const markersApi = markersApiRef.current;
    const primitive = structurePrimitiveRef.current;
    if (!markersApi) return;

    const hasStructureLayer = Boolean(structure || liquidity || obFvg);
    const hasTradeMarkers = tradeMarkers.length > 0;
    const hasPlanZones = planZones.length > 0;

    if (!hasStructureLayer && !hasTradeMarkers && !hasPlanZones) {
      markersApi.setMarkers([]);
      annotationPricesRef.current = [];
      primitive?.setSegments([]);
      liquidityPrimitiveRef.current?.setSegments([]);
      zonePrimitiveRef.current?.setZones([]);
      return;
    }

    const showSwings = structureOverlays.includes("swings");
    const showHh = structureOverlays.includes("hh");
    const showHl = structureOverlays.includes("hl");
    const showLh = structureOverlays.includes("lh");
    const showLl = structureOverlays.includes("ll");
    const showBos = structureOverlays.includes("bos");
    const showChoch = structureOverlays.includes("choch");
    const showMss = structureOverlays.includes("mss");
    const hideOlderLabels = structureOverlays.includes("recentLabels");

    const candleTimes = buildCandleTimeSet(candles.map((c) => c.timestamp));

    const showEqh = liquidityOverlays.includes("eqh");
    const showEql = liquidityOverlays.includes("eql");
    const showBsl = liquidityOverlays.includes("bsl");
    const showSsl = liquidityOverlays.includes("ssl");
    const showSweeps = liquidityOverlays.includes("sweeps");

    const mappedRaw = hasStructureLayer
      ? applyLabelCollisionPolicy(
          dedupePriceMarkers([
            ...mapSwingMarkers(structure?.swings ?? [], {
              showSwings,
              showHh,
              showHl,
              showLh,
              showLl,
            }),
            ...mapBosMarkers(structure?.bosEvents ?? [], showBos),
            ...mapChochMarkers(structure?.chochEvents ?? [], showChoch),
            ...mapMssMarkers(structure?.mssEvents ?? [], showMss),
            ...mapSweepMarkers(liquidity?.sweeps ?? [], showSweeps).map((m) => ({
              ...m,
              kind: "mss" as const, // reuse priority bucket for collision policy
            })),
          ]),
          { maxLabeledPerCategory: 6, hideOlderLabels },
        )
      : [];

    // Recent-labels mode: drop unlabeled older markers entirely (data remains in panel).
    const mapped = hideOlderLabels
      ? mappedRaw.filter((m) => m.text.length > 0)
      : mappedRaw;

    // Guard against duplicate ids after WS snapshot replace.
    assertNoDuplicateAnnotationIds(mapped);

    const tradeMapped = tradeMarkers.map((m) => ({
      id: m.id,
      time: m.time,
      position: m.position,
      shape: m.shape,
      color: m.color,
      text: m.text,
      price: m.price,
      size: 1.25,
    }));

    markersApi.setMarkers([
      ...mapped.map((m) => ({
        id: m.id,
        time: m.time,
        position: m.position,
        shape: m.shape,
        color: m.color,
        text: m.text,
        price: m.price,
        size: 1.15,
      })),
      ...tradeMapped,
    ]);

    const wantedSegments = hasStructureLayer
      ? selectRecentSegments(
          [
            ...(showBos
              ? mapBosSegments(structure?.bosEvents ?? [], structure?.swings ?? [], candleTimes)
              : []),
            ...(showChoch
              ? mapChochSegments(
                  structure?.chochEvents ?? [],
                  structure?.swings ?? [],
                  true,
                  candleTimes,
                )
              : []),
          ],
          16,
          hideOlderLabels,
        )
      : [];
    const liqSegments = hasStructureLayer
      ? mapLiquiditySegments({
          eqh: liquidity?.eqhClusters ?? [],
          eql: liquidity?.eqlClusters ?? [],
          bsl: liquidity?.bslLevels ?? [],
          ssl: liquidity?.sslLevels ?? [],
          showEqh,
          showEql,
          showBsl,
          showSsl,
          fallbackEndIso: candles.at(-1)?.timestamp ?? null,
        })
      : [];
    const obFvgZones = hasStructureLayer
      ? mapObFvgZones({
          bullishObs: obFvg?.bullishOrderBlocks ?? [],
          bearishObs: obFvg?.bearishOrderBlocks ?? [],
          bullishFvgs: obFvg?.bullishFvgs ?? [],
          bearishFvgs: obFvg?.bearishFvgs ?? [],
          showBullishOb: obFvgOverlays.includes("bullishOb"),
          showBearishOb: obFvgOverlays.includes("bearishOb"),
          showBullishFvg: obFvgOverlays.includes("bullishFvg"),
          showBearishFvg: obFvgOverlays.includes("bearishFvg"),
          recentOnly: obFvgOverlays.includes("recentZones"),
          fallbackEndIso: candles.at(-1)?.timestamp ?? null,
        })
      : [];
    const zones = [...obFvgZones, ...planZones];
    annotationPricesRef.current = collectAnnotationPrices(mapped, wantedSegments)
      .concat(liqSegments.map((s) => s.price))
      .concat(zones.flatMap((z) => [z.priceHigh, z.priceLow]))
      .concat(tradeMarkers.map((m) => m.price))
      .concat(tradePriceLines.map((l) => l.price));
    candleSeriesRef.current?.priceScale().applyOptions({ autoScale: true });

    // Draw via candlestick primitives — same time/price coordinate space as OHLC bars.
    primitive?.setSegments(toSegmentDrawSpecs(wantedSegments));
    liquidityPrimitiveRef.current?.setSegments(liqSegments);
    zonePrimitiveRef.current?.setZones(zones);
  }, [
    structure,
    structureOverlays,
    liquidity,
    liquidityOverlays,
    obFvg,
    obFvgOverlays,
    tradeMarkers,
    tradePriceLines,
    planZones,
    seriesKey,
    candles,
  ]);

  // Phase 5.2.8 — sync planned Entry/SL/TP price lines without recreating the chart.
  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!series) return;

    const nextIds = new Set(tradePriceLines.map((l) => l.id));
    for (const [id, line] of tradePriceLinesRef.current.entries()) {
      if (!nextIds.has(id)) {
        series.removePriceLine(line);
        tradePriceLinesRef.current.delete(id);
      }
    }

    for (const spec of tradePriceLines) {
      const existing = tradePriceLinesRef.current.get(spec.id);
      const opts = {
        price: spec.price,
        color: spec.color,
        lineWidth: spec.lineWidth as 1 | 2 | 3 | 4,
        lineStyle: spec.lineStyle as LineStyle,
        axisLabelVisible: true,
        title: spec.title,
      };
      if (existing) {
        existing.applyOptions(opts);
      } else {
        tradePriceLinesRef.current.set(spec.id, series.createPriceLine(opts));
      }
    }
  }, [tradePriceLines, seriesKey]);

  const display = hover ?? (candles.length ? lookupCandleAtTimeSec(
    candleLookup,
    Math.floor(new Date(candles[candles.length - 1]!.timestamp).getTime() / 1000),
  ) : null);
  const up = display ? display.close >= display.open : true;

  return (
    <div className={cn("flex h-full w-full min-h-[280px] flex-col", className)}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-terminal-border/70 px-3 py-1.5 font-mono text-[11px] text-terminal-muted">
        {display ? (
          <>
            <span className="text-terminal-text">{formatHoverTime(display.timestamp)}</span>
            <OhlcField label="O" value={formatPrice(display.open)} />
            <OhlcField label="H" value={formatPrice(display.high)} />
            <OhlcField label="L" value={formatPrice(display.low)} />
            <OhlcField label="C" value={formatPrice(display.close)} tone={up ? "up" : "down"} />
            <OhlcField label="Vol" value={formatVolume(display.volume)} />
            <OhlcField
              label="Chg"
              value={formatPct(display.changePct)}
              tone={display.changePct >= 0 ? "up" : "down"}
            />
            {!hover ? <span className="text-[10px] text-terminal-muted/70">latest</span> : null}
          </>
        ) : (
          <span>Move crosshair over a candle for OHLC</span>
        )}
      </div>
      <div ref={containerRef} className="min-h-0 flex-1 w-full" />
    </div>
  );
}

function OhlcField({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "up" | "down";
}) {
  return (
    <span>
      <span className="text-terminal-muted">{label} </span>
      <span
        className={cn(
          "text-terminal-text",
          tone === "up" && "text-terminal-long",
          tone === "down" && "text-terminal-short",
        )}
      >
        {value}
      </span>
    </span>
  );
}
