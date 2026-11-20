"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ScanSearch, Upload, X } from "lucide-react";
import { IndicatorsPanel } from "@/components/charts/indicators-panel";
import { MarketChartPanel } from "@/components/charts/market-chart-panel";
import {
  StructurePanel,
  type StructureOverlayId,
} from "@/components/charts/structure-panel";
import { LiquidityPanel } from "@/components/charts/liquidity-panel";
import type { LiquidityOverlayId } from "@/lib/liquidity-chart-overlays";
import { ObFvgPanel } from "@/components/charts/ob-fvg-panel";
import { MtfOverviewPanel } from "@/components/charts/mtf-overview-panel";
import { ConfluencePanel } from "@/components/charts/confluence-panel";
import { TradePlanPanel } from "@/components/charts/trade-plan-panel";
import { DecisionPanel } from "@/components/charts/decision-panel";
import { TradePlanChartStatusBadge } from "@/components/charts/trade-plan-chart-overlay";
import {
  AiExplanationPanel,
  DeterministicSnapshotPanel,
  VisionComparisonPanel,
  VisionObservationsPanel,
} from "@/components/charts/ai-analysis-panels";
import type { ObFvgOverlayId } from "@/lib/ob-fvg-chart-overlays";
import type { TradePlanLegendModel } from "@/lib/trade-plan-chart-visuals";
import { MarketControls } from "@/components/trading/market-controls";
import { useMarketStore } from "@/stores/market-store";
import { api, ApiError } from "@/services/api";
import type {
  AiAnalyzeResponse,
  AnalysisSnapshot,
  IndicatorId,
  VisionComparisonSummary,
  VisionResult,
} from "@/types/api";
import type { ReactNode } from "react";
import { cn } from "@/utils/cn";
import {
  formatFileSize,
  shouldBlockDuplicateSubmit,
  validateChartScreenshotFile,
} from "@/lib/ai-analysis-display";

export default function ChartAnalyzerPage() {
  const { exchange, marketType, symbol, timeframe } = useMarketStore();
  const [preview, setPreview] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [fileSize, setFileSize] = useState<number | null>(null);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [planLegend, setPlanLegend] = useState<TradePlanLegendModel | null>(null);
  const onTradePlanLegendChange = useCallback((legend: TradePlanLegendModel) => {
    setPlanLegend(legend);
  }, []);

  const [chartOverlays, setChartOverlays] = useState<IndicatorId[]>(["ema_20", "ema_50"]);
  const [structureOverlays, setStructureOverlays] = useState<StructureOverlayId[]>([
    "swings",
    "hh",
    "hl",
    "lh",
    "ll",
    "bos",
    "choch",
    "recentLabels",
  ]);
  const [liquidityOverlays, setLiquidityOverlays] = useState<LiquidityOverlayId[]>([
    "eqh",
    "eql",
    "bsl",
    "ssl",
    "sweeps",
  ]);
  const [obFvgOverlays, setObFvgOverlays] = useState<ObFvgOverlayId[]>([
    "bullishOb",
    "bearishOb",
    "bullishFvg",
    "bearishFvg",
    "recentZones",
  ]);

  const [analyzeLoading, setAnalyzeLoading] = useState(false);
  const [visionLoading, setVisionLoading] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [visionError, setVisionError] = useState<string | null>(null);
  const [analyzeResult, setAnalyzeResult] = useState<AiAnalyzeResponse | null>(null);
  const [snapshot, setSnapshot] = useState<AnalysisSnapshot | null>(null);
  const [vision, setVision] = useState<VisionResult | null>(null);
  const [comparison, setComparison] = useState<VisionComparisonSummary | null>(null);

  const analyzeSeqRef = useRef(0);
  const visionSeqRef = useRef(0);
  const analyzeAbortRef = useRef<AbortController | null>(null);
  const visionAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    // Clear AI results that belong to a previous market selection.
    setAnalyzeResult(null);
    setSnapshot(null);
    setComparison(null);
    setAnalyzeError(null);
  }, [exchange, marketType, symbol]);

  const clearImage = useCallback(() => {
    setPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    setFileName(null);
    setFileSize(null);
    setImageFile(null);
    setUploadError(null);
    setVision(null);
    setComparison(null);
    setVisionError(null);
  }, []);

  const onPickImage = (file: File | undefined) => {
    if (!file) return;
    const validation = validateChartScreenshotFile(file);
    if (!validation.ok) {
      setUploadError(validation.error);
      return;
    }
    setUploadError(null);
    setFileName(file.name);
    setFileSize(file.size);
    setImageFile(file);
    const url = URL.createObjectURL(file);
    setPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return url;
    });
  };

  const runAnalyze = async () => {
    if (shouldBlockDuplicateSubmit(analyzeLoading)) return;
    if (!exchange || !marketType || !symbol) {
      setAnalyzeError("Select exchange, market type, and symbol first.");
      return;
    }
    analyzeAbortRef.current?.abort();
    const controller = new AbortController();
    analyzeAbortRef.current = controller;
    const seq = ++analyzeSeqRef.current;
    setAnalyzeLoading(true);
    setAnalyzeError(null);
    try {
      const result = await api.aiAnalyze(
        {
          exchange,
          marketType,
          symbol,
          timeframe,
          includeExplanation: true,
        },
        controller.signal,
      );
      if (seq !== analyzeSeqRef.current) return;
      setAnalyzeResult(result);
      setSnapshot(result.snapshot);
      if (vision && result.snapshot) {
        try {
          const cmp = await api.aiCompare(
            { snapshot: result.snapshot, vision },
            controller.signal,
          );
          if (seq === analyzeSeqRef.current) setComparison(cmp.comparison);
        } catch {
          /* comparison optional */
        }
      }
    } catch (err) {
      if (controller.signal.aborted) return;
      if (seq !== analyzeSeqRef.current) return;
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Analyze failed";
      setAnalyzeError(message);
    } finally {
      if (seq === analyzeSeqRef.current) setAnalyzeLoading(false);
    }
  };

  const runVision = async () => {
    if (shouldBlockDuplicateSubmit(visionLoading) || !imageFile) return;
    visionAbortRef.current?.abort();
    const controller = new AbortController();
    visionAbortRef.current = controller;
    const seq = ++visionSeqRef.current;
    setVisionLoading(true);
    setVisionError(null);
    try {
      const result = await api.aiVisionAnalyze(imageFile, controller.signal);
      if (seq !== visionSeqRef.current) return;
      setVision(result.vision);
      if (snapshot) {
        const cmp = await api.aiCompare(
          { snapshot, vision: result.vision },
          controller.signal,
        );
        if (seq === visionSeqRef.current) setComparison(cmp.comparison);
      }
    } catch (err) {
      if (controller.signal.aborted) return;
      if (seq !== visionSeqRef.current) return;
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Vision analysis failed";
      setVisionError(message);
    } finally {
      if (seq === visionSeqRef.current) setVisionLoading(false);
    }
  };

  return (
    <div className="flex h-full min-h-[calc(100dvh-4rem)] flex-col gap-4 p-4 md:p-5 xl:flex-row">
      <aside className="w-full shrink-0 space-y-4 xl:w-72">
        <div className="rounded-lg border border-terminal-border bg-terminal-panel p-4">
          <h1 className="flex items-center gap-2 font-display text-lg font-semibold text-terminal-text">
            <ScanSearch className="h-5 w-5 text-terminal-accent" />
            AI Chart Analyzer
          </h1>
          <p className="mt-1 text-xs text-terminal-muted">
            Live engines + AI explanation / vision (Phase 5.4). Analysis only.
          </p>

          <div className="mt-4 space-y-3">
            <Field label="Exchange">
              <div className="rounded-md border border-terminal-border bg-terminal-surface px-3 py-2 text-sm capitalize text-terminal-text">
                {exchange}
              </div>
            </Field>
            <Field label="Market type">
              <div className="rounded-md border border-terminal-border bg-terminal-surface px-3 py-2 text-sm text-terminal-text">
                {marketType.replaceAll("_", " ")}
              </div>
            </Field>

            <MarketControls />

            <Field label="Chart screenshot">
              <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border border-dashed border-terminal-border bg-terminal-surface/60 px-3 py-6 text-center transition hover:border-terminal-accent/50">
                <Upload className="h-5 w-5 text-terminal-muted" />
                <span className="text-xs text-terminal-muted">
                  PNG / JPEG / WebP — optional vision
                </span>
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/jpg,image/webp"
                  className="hidden"
                  onChange={(e) => {
                    onPickImage(e.target.files?.[0]);
                    e.target.value = "";
                  }}
                />
              </label>
              {fileName ? (
                <div className="mt-2 flex items-start justify-between gap-2 text-[11px] text-terminal-muted">
                  <div className="min-w-0">
                    <p className="truncate">{fileName}</p>
                    <p>{fileSize != null ? formatFileSize(fileSize) : ""}</p>
                  </div>
                  <button
                    type="button"
                    onClick={clearImage}
                    className="rounded border border-terminal-border p-1 hover:text-terminal-text"
                    aria-label="Remove image"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ) : null}
              {uploadError ? (
                <p className="mt-1 text-[11px] text-terminal-short">{uploadError}</p>
              ) : null}
            </Field>

            <button
              type="button"
              disabled={analyzeLoading || !symbol}
              onClick={() => void runAnalyze()}
              className={cn(
                "h-10 w-full rounded-md text-sm font-medium transition",
                analyzeLoading || !symbol
                  ? "cursor-not-allowed bg-terminal-accent/40 text-terminal-bg"
                  : "bg-terminal-accent text-terminal-bg hover:opacity-90",
              )}
            >
              {analyzeLoading ? "Analyzing…" : "Analyze"}
            </button>

            <button
              type="button"
              disabled={visionLoading || !imageFile}
              onClick={() => void runVision()}
              className={cn(
                "h-9 w-full rounded-md border text-sm transition",
                visionLoading || !imageFile
                  ? "cursor-not-allowed border-terminal-border text-terminal-muted"
                  : "border-terminal-accent/50 text-terminal-text hover:border-terminal-accent",
              )}
            >
              {visionLoading ? "Vision…" : "Run Vision on screenshot"}
            </button>

            {analyzeError ? (
              <p className="text-[11px] text-terminal-short">{analyzeError}</p>
            ) : null}
            {visionError ? (
              <p className="text-[11px] text-terminal-short">{visionError}</p>
            ) : null}
          </div>
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col gap-4">
        <MarketChartPanel
          exchange={exchange}
          marketType={marketType}
          symbol={symbol}
          timeframe={timeframe}
          heightClass="h-[min(72vh,720px)]"
          chartOverlays={chartOverlays}
          structureOverlays={structureOverlays}
          liquidityOverlays={liquidityOverlays}
          obFvgOverlays={obFvgOverlays}
          enableTradePlanVisuals
          onTradePlanLegendChange={onTradePlanLegendChange}
        />

        <MtfOverviewPanel
          exchange={exchange}
          marketType={marketType}
          symbol={symbol}
        />

        <ConfluencePanel
          exchange={exchange}
          marketType={marketType}
          symbol={symbol}
        />

        <TradePlanPanel
          exchange={exchange}
          marketType={marketType}
          symbol={symbol}
        />

        <DecisionPanel
          exchange={exchange}
          marketType={marketType}
          symbol={symbol}
        />

        {preview ? (
          <div className="rounded-lg border border-terminal-border bg-terminal-panel p-3">
            <p className="mb-2 text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
              Screenshot preview
            </p>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={preview}
              alt="Uploaded chart preview"
              className="max-h-[280px] w-full object-contain"
            />
          </div>
        ) : null}

        {snapshot ? <DeterministicSnapshotPanel snapshot={snapshot} /> : null}
        <AiExplanationPanel explanation={analyzeResult?.explanation} />
        <VisionObservationsPanel vision={vision} />
        <VisionComparisonPanel
          comparison={comparison ?? analyzeResult?.explanation?.vision_comparison}
        />
      </section>

      <aside className="w-full shrink-0 space-y-3 xl:w-80">
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
        <Panel title="AI Analysis Summary">
          {analyzeResult?.explanation?.summary ? (
            <p className="text-sm text-terminal-text">{analyzeResult.explanation.summary}</p>
          ) : (
            <Empty>Press Analyze to generate an explanation from engine output.</Empty>
          )}
        </Panel>
        <Panel title="Trade Decision">
          <p className="mt-1 text-xs text-terminal-muted">
            {snapshot
              ? `${snapshot.decision} — analysis only, no order execution.`
              : "See Final Decision panel — analysis only, no order execution."}
          </p>
        </Panel>
        <Panel title="Plan levels">
          {planLegend || snapshot ? (
            <div className="space-y-2 text-xs text-terminal-text">
              {planLegend ? (
                <TradePlanChartStatusBadge status={planLegend.status} />
              ) : null}
              <p className="font-mono text-[11px] text-terminal-muted">
                Entry{" "}
                {snapshot?.entry_reference_price ?? planLegend?.entry ?? "—"} · SL{" "}
                {snapshot?.stop_loss_price ?? planLegend?.stopLoss ?? "—"}
              </p>
              <p className="font-mono text-[11px] text-terminal-muted">
                TPs{" "}
                {(snapshot?.take_profit_prices?.length
                  ? snapshot.take_profit_prices.join(" · ")
                  : null) ??
                  `TP1 ${planLegend?.tp1 ?? "—"} · TP2 ${planLegend?.tp2 ?? "—"} · TP3 ${planLegend?.tp3 ?? "—"}`}
              </p>
              <p className="text-[10px] text-terminal-muted">
                Backend-sourced levels only — not AI-invented prices.
              </p>
            </div>
          ) : (
            <Empty>Entry / SL / TP appear on the chart when a plan is available.</Empty>
          )}
        </Panel>
        <Panel title="Confluence Score">
          {snapshot ? (
            <p className="font-mono text-xs text-terminal-text">
              B {snapshot.confluence_bullish ?? "—"} / S {snapshot.confluence_bearish ?? "—"}
            </p>
          ) : (
            <Empty>See Confluence panel (Phase 4.2) — preliminary only</Empty>
          )}
        </Panel>
      </aside>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">{label}</span>
      {children}
    </label>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-terminal-border bg-terminal-panel p-3">
      <h3 className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">{title}</h3>
      <div className="mt-2">{children}</div>
    </div>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="text-sm text-terminal-muted">{children}</p>;
}
