"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import { ScanSearch } from "lucide-react";
import { MarketChartPanel } from "@/components/charts/market-chart-panel";
import type { StructureOverlayId } from "@/components/charts/structure-panel";
import type { LiquidityOverlayId } from "@/lib/liquidity-chart-overlays";
import {
  AiExplanationPanel,
  VisionComparisonPanel,
  VisionObservationsPanel,
} from "@/components/charts/ai-analysis-panels";
import {
  PriceComparisonPanel,
  ScreenshotRecognitionResultsPanel,
} from "@/components/charts/market-analyzer-results";
import { AnalyzerMarketOverview } from "@/components/charts/analyzer-market-overview";
import { AnalyzerDecisionStatus } from "@/components/charts/analyzer-decision-status";
import { AnalyzerTradeLevels } from "@/components/charts/analyzer-trade-levels";
import { SmcAnalysisSections } from "@/components/charts/smc-analysis-sections";
import { AnalysisModeSelector } from "@/components/charts/analysis-mode-selector";
import { ChartImageUpload } from "@/components/charts/chart-image-upload";
import { ChartRecognitionPanel } from "@/components/charts/chart-recognition-panel";
import type { CandlestickChartHandle } from "@/components/charts/candlestick-chart";
import type { ObFvgOverlayId } from "@/lib/ob-fvg-chart-overlays";
import type { TradePlanLegendModel } from "@/lib/trade-plan-chart-visuals";
import { TradePlanChartStatusBadge } from "@/components/charts/trade-plan-chart-overlay";
import { MarketControls } from "@/components/trading/market-controls";
import { useMarketStore } from "@/stores/market-store";
import { useDecision, useTradePlan } from "@/hooks/use-market-data";
import {
  useLiveDecisionSubscription,
  useLiveTradePlanSubscription,
} from "@/hooks/use-market-socket";
import {
  decisionKey,
  tickerKey,
  tradePlanKey,
  useLiveMarketStore,
} from "@/stores/live-market-store";
import {
  asFinalDecision,
  buildAnalyzerTradeLevels,
} from "@/lib/analyzer-dashboard-display";
import { api, ApiError } from "@/services/api";
import type {
  AiAnalyzeResponse,
  AnalysisSnapshot,
  DecisionResponse,
  ExchangeId,
  IndicatorId,
  MarketType,
  Timeframe,
  TradePlanResponse,
  VisionComparisonSummary,
  VisionResult,
} from "@/types/api";
import { cn } from "@/utils/cn";
import { shouldBlockDuplicateSubmit } from "@/lib/ai-analysis-display";
import { exportChartScreenshot, waitForChartPaint } from "@/lib/chart-export";
import {
  analyzerDescription,
  analyzerTitle,
} from "@/lib/market-symbol-search";
import type { AnalysisMode } from "@/lib/analysis-mode";
import {
  draftFromVision,
  type RecognitionDraft,
} from "@/lib/chart-recognition";

export default function ChartAnalyzerPage() {
  const {
    exchange,
    marketType,
    symbol,
    timeframe,
    setExchange,
    setMarketType,
    setSymbol,
    setTimeframe,
  } = useMarketStore();
  const searchParams = useSearchParams();
  const chartHandleRef = useRef<CandlestickChartHandle | null>(null);

  // Open Full Analysis from Market Opportunities — hydrate store only (no layout change).
  useEffect(() => {
    if (searchParams.get("from") !== "opportunities") return;
    const ex = searchParams.get("exchange") as ExchangeId | null;
    const mt = searchParams.get("marketType") as MarketType | null;
    const sym = searchParams.get("symbol");
    const tf = searchParams.get("timeframe") as Timeframe | null;
    if (ex === "binance" || ex === "bybit") setExchange(ex);
    if (mt === "spot" || mt === "usdt_m_futures" || mt === "linear_perpetual") {
      setMarketType(mt);
    }
    if (sym) setSymbol(sym.toUpperCase());
    if (tf && ["1m", "5m", "15m", "30m", "1h", "4h", "1d"].includes(tf)) {
      setTimeframe(tf);
    }
  }, [searchParams, setExchange, setMarketType, setSymbol, setTimeframe]);

  const [mode, setMode] = useState<AnalysisMode>("LIVE_MARKET");
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
  const [recognizeLoading, setRecognizeLoading] = useState(false);
  const [visionPhase, setVisionPhase] = useState<"idle" | "capturing" | "running" | "done">(
    "idle",
  );
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [visionNote, setVisionNote] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [analyzeResult, setAnalyzeResult] = useState<AiAnalyzeResponse | null>(null);
  const [snapshot, setSnapshot] = useState<AnalysisSnapshot | null>(null);
  const [vision, setVision] = useState<VisionResult | null>(null);
  const [comparison, setComparison] = useState<VisionComparisonSummary | null>(null);
  const [recognitionDraft, setRecognitionDraft] = useState<RecognitionDraft>(() =>
    draftFromVision(null, { exchange, marketType, symbol, timeframe }),
  );

  const analyzeSeqRef = useRef(0);
  const analyzeAbortRef = useRef<AbortController | null>(null);
  const recognizeAbortRef = useRef<AbortController | null>(null);

  useLiveTradePlanSubscription(exchange, marketType, symbol, true);
  useLiveDecisionSubscription(exchange, marketType, symbol, true);
  const tradePlanQuery = useTradePlan({ exchange, marketType, symbol });
  const decisionQuery = useDecision({ exchange, marketType, symbol });
  const liveTradePlan = useLiveMarketStore(
    (s) => s.tradePlan[tradePlanKey(exchange, marketType, symbol)],
  );
  const liveDecision = useLiveMarketStore(
    (s) => s.decision[decisionKey(exchange, marketType, symbol)],
  );
  const liveTicker = useLiveMarketStore(
    (s) => s.tickers[tickerKey(exchange, marketType, symbol)],
  );

  const clearAnalyzeState = useCallback(() => {
    analyzeSeqRef.current += 1;
    analyzeAbortRef.current?.abort();
    analyzeAbortRef.current = null;
    setAnalyzeLoading(false);
    setAnalyzeResult(null);
    setSnapshot(null);
    setComparison(null);
    setVision(null);
    setAnalyzeError(null);
    setVisionNote(null);
    setVisionPhase("idle");
  }, []);

  useEffect(() => {
    if (mode !== "LIVE_MARKET") return;
    clearAnalyzeState();
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
  }, [exchange, marketType, symbol, timeframe, mode, clearAnalyzeState]);

  useEffect(() => {
    return () => {
      analyzeAbortRef.current?.abort();
      recognizeAbortRef.current?.abort();
      setPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    };
  }, []);

  const handleModeChange = (next: AnalysisMode) => {
    if (next === mode) return;
    clearAnalyzeState();
    recognizeAbortRef.current?.abort();
    setRecognizeLoading(false);
    setUploadFile(null);
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    setRecognitionDraft(
      draftFromVision(null, { exchange, marketType, symbol, timeframe }),
    );
    setMode(next);
  };

  const handleUploadChange = (file: File | null, url: string | null) => {
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return url;
    });
    setUploadFile(file);
    clearAnalyzeState();
    setVision(null);
    if (file && url) {
      void runRecognize(file);
    } else {
      setRecognitionDraft(
        draftFromVision(null, { exchange, marketType, symbol, timeframe }),
      );
    }
  };

  const runRecognize = async (file: File) => {
    recognizeAbortRef.current?.abort();
    const controller = new AbortController();
    recognizeAbortRef.current = controller;
    setRecognizeLoading(true);
    setAnalyzeError(null);
    try {
      const result = await api.aiVisionAnalyze(file, controller.signal);
      if (controller.signal.aborted) return;
      setVision(result.vision);
      setRecognitionDraft(
        draftFromVision(result.vision, {
          exchange,
          marketType,
          symbol,
          timeframe,
        }),
      );
      if (result.vision.status !== "OK") {
        setVisionNote(
          result.vision.message ||
            "Vision unavailable — confirm symbol and timeframe manually.",
        );
      } else {
        setVisionNote(null);
      }
    } catch (err) {
      if (controller.signal.aborted) return;
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Recognition failed";
      setAnalyzeError(message);
      setVision(null);
      setRecognitionDraft(
        draftFromVision(null, { exchange, marketType, symbol, timeframe }),
      );
    } finally {
      if (!controller.signal.aborted) setRecognizeLoading(false);
    }
  };

  const applyRecognitionToStore = (draft: RecognitionDraft) => {
    setExchange(draft.exchange);
    setMarketType(draft.marketType);
    setSymbol(draft.symbol.trim().toUpperCase());
    setTimeframe(draft.timeframe);
  };

  const runAnalyze = async () => {
    if (shouldBlockDuplicateSubmit(analyzeLoading)) return;

    const useUpload = mode === "UPLOADED_IMAGE";
    const ex = useUpload ? recognitionDraft.exchange : exchange;
    const mt = useUpload ? recognitionDraft.marketType : marketType;
    const sym = useUpload ? recognitionDraft.symbol.trim().toUpperCase() : symbol;
    const tf = useUpload ? recognitionDraft.timeframe : timeframe;

    if (!ex || !mt || !sym) {
      setAnalyzeError("Select exchange, market type, and symbol first.");
      return;
    }
    if (useUpload && !uploadFile) {
      setAnalyzeError("Upload a chart image before Analyze.");
      return;
    }
    if (useUpload && (!recognitionDraft.symbolConfirmed || !recognitionDraft.timeframeConfirmed)) {
      setAnalyzeError(
        "Confirm symbol and timeframe (or correct them) before Analyze. Ambiguous recognition is never guessed silently.",
      );
      return;
    }

    if (useUpload) {
      applyRecognitionToStore(recognitionDraft);
    }

    analyzeAbortRef.current?.abort();
    const controller = new AbortController();
    analyzeAbortRef.current = controller;
    const seq = ++analyzeSeqRef.current;

    setAnalyzeLoading(true);
    setAnalyzeError(null);
    setVisionNote(null);

    let chartFile: File | null = useUpload ? uploadFile : null;
    try {
      if (!useUpload) {
        setVisionPhase("capturing");
        await waitForChartPaint(150);
        if (seq !== analyzeSeqRef.current) return;
        const exported = await exportChartScreenshot({
          chart: chartHandleRef.current,
          exchange: ex,
          marketType: mt,
          symbol: sym,
          timeframe: tf,
        });
        if (exported.ok) {
          chartFile = exported.file;
          setPreviewUrl((prev) => {
            if (prev) URL.revokeObjectURL(prev);
            return exported.previewUrl;
          });
          setVisionPhase("running");
        } else {
          setVisionNote(
            `${exported.error} Deterministic analysis will still run without Vision.`,
          );
          setVisionPhase("idle");
        }
      } else {
        setVisionPhase("running");
      }

      const result = await api.aiAnalyzeWithVision(
        {
          exchange: ex,
          marketType: mt,
          symbol: sym,
          timeframe: tf,
          analysisMode: mode,
          file: chartFile,
        },
        controller.signal,
      );
      if (seq !== analyzeSeqRef.current) return;

      setAnalyzeResult(result);
      setSnapshot(result.snapshot);
      setVision(result.vision ?? vision);
      setComparison(result.explanation?.vision_comparison ?? null);

      if (result.vision_status && result.vision_status !== "ok") {
        setVisionNote(
          result.vision_detail ||
            (result.vision_status === "skipped"
              ? "Vision skipped — chart image unavailable."
              : `Vision ${result.vision_status}. Deterministic results preserved.`),
        );
      } else if (result.vision) {
        setVisionNote(null);
      }
      setVisionPhase("done");
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
      setVisionPhase("idle");
    } finally {
      if (seq === analyzeSeqRef.current) setAnalyzeLoading(false);
    }
  };

  const analyzeLabel =
    analyzeLoading && visionPhase === "capturing"
      ? "Capturing chart…"
      : analyzeLoading && visionPhase === "running"
        ? "Analyzing + Vision…"
        : analyzeLoading
          ? "Analyzing…"
          : "Analyze";

  const chartTitle =
    mode === "UPLOADED_IMAGE"
      ? "Reconstructed chart (verified exchange OHLCV)"
      : undefined;

  const analyzeDisabled =
    analyzeLoading ||
    !symbol ||
    (mode === "UPLOADED_IMAGE" &&
      (!uploadFile ||
        !recognitionDraft.symbol.trim() ||
        !recognitionDraft.symbolConfirmed ||
        !recognitionDraft.timeframeConfirmed));

  const displayExchange = mode === "UPLOADED_IMAGE" ? recognitionDraft.exchange : exchange;
  const displayMarketType =
    mode === "UPLOADED_IMAGE" ? recognitionDraft.marketType : marketType;
  const displaySymbol =
    mode === "UPLOADED_IMAGE"
      ? recognitionDraft.symbol.trim().toUpperCase() || symbol
      : symbol;
  const displayTimeframe =
    mode === "UPLOADED_IMAGE" ? recognitionDraft.timeframe : timeframe;

  const resolvedDecision: DecisionResponse | null =
    analyzeResult?.decision ?? decisionQuery.data ?? null;
  const resolvedTradePlan: TradePlanResponse | null =
    analyzeResult?.trade_plan ?? tradePlanQuery.data ?? null;

  const livePrice =
    liveTicker?.last ??
    liveDecision?.dataQuality?.current_price ??
    liveTradePlan?.dataQuality?.current_price ??
    resolvedDecision?.data_quality?.current_price ??
    resolvedTradePlan?.data_quality?.current_price ??
    null;

  const tradeLevelsModel = useMemo(() => {
    const planFromLive: TradePlanResponse | null = liveTradePlan
      ? ({
          entry: liveTradePlan.entry,
          stop_loss: liveTradePlan.stopLoss,
          take_profit_targets: liveTradePlan.takeProfitTargets ?? [],
          risk: liveTradePlan.risk,
          plan_status: liveTradePlan.planStatus,
          invalidation_conditions: liveTradePlan.invalidationConditions ?? [],
          data_quality: liveTradePlan.dataQuality,
        } as TradePlanResponse)
      : null;

    const decisionFromLive: DecisionResponse | null = liveDecision
      ? ({
          decision: liveDecision.decision,
          decision_reason: liveDecision.decisionReason,
          stop_loss_price: liveDecision.stopLossPrice,
          take_profit_prices: liveDecision.takeProfitPrices ?? [],
          primary_rr: liveDecision.primaryRr,
          entry_confirmation: liveDecision.entryConfirmation,
          entry_zone_summary: liveDecision.entryZoneSummary,
          data_quality: liveDecision.dataQuality,
        } as DecisionResponse)
      : null;

    return buildAnalyzerTradeLevels({
      decision: resolvedDecision ?? decisionFromLive,
      tradePlan: resolvedTradePlan ?? planFromLive,
      snapshotDecision: asFinalDecision(snapshot?.decision),
      snapshotEntryRef: snapshot?.entry_reference_price ?? null,
      snapshotEntryLow: snapshot?.entry_low ?? null,
      snapshotEntryHigh: snapshot?.entry_high ?? null,
      snapshotStop: snapshot?.stop_loss_price ?? null,
      snapshotTps: snapshot?.take_profit_prices ?? null,
      snapshotPrimaryRr: snapshot?.primary_rr ?? null,
      livePrice,
    });
  }, [
    resolvedDecision,
    resolvedTradePlan,
    liveTradePlan,
    liveDecision,
    snapshot,
    livePrice,
  ]);

  const decisionValue =
    resolvedDecision?.decision ??
    liveDecision?.decision ??
    asFinalDecision(snapshot?.decision);
  const decisionReason =
    resolvedDecision?.decision_reason ??
    liveDecision?.decisionReason ??
    snapshot?.decision_reason ??
    null;

  const screenshotObserved =
    analyzeResult?.price_comparison?.screenshot_observed_price ??
    analyzeResult?.recognition?.observed_last_price ??
    vision?.observed_last_price ??
    null;

  return (
    <div className="flex h-full min-h-[calc(100dvh-4rem)] flex-col gap-4 p-4 md:p-5 xl:flex-row">
      <aside className="w-full shrink-0 space-y-4 xl:w-80">
        <div className="rounded-lg border border-terminal-border bg-terminal-panel p-4">
          <h1 className="flex items-center gap-2 font-display text-lg font-semibold text-terminal-text">
            <ScanSearch className="h-5 w-5 text-terminal-accent" />
            {analyzerTitle()}
          </h1>
          <p className="mt-1 text-xs text-terminal-muted">{analyzerDescription()}</p>
          <p className="mt-2 text-[10px] uppercase tracking-[0.14em] text-terminal-muted">
            Analysis only — no order execution
          </p>

          <div className="mt-4 space-y-3">
            <AnalysisModeSelector
              mode={mode}
              onChange={handleModeChange}
              disabled={analyzeLoading || recognizeLoading}
            />

            {mode === "LIVE_MARKET" ? (
              <>
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
                <p className="text-[11px] text-terminal-muted">
                  Analyze captures the live chart image automatically and runs Vision alongside
                  deterministic engines.
                </p>
              </>
            ) : (
              <>
                <ChartImageUpload
                  file={uploadFile}
                  previewUrl={mode === "UPLOADED_IMAGE" ? previewUrl : null}
                  onFileChange={handleUploadChange}
                  disabled={analyzeLoading || recognizeLoading}
                />
                <ChartRecognitionPanel
                  vision={vision}
                  draft={recognitionDraft}
                  onDraftChange={(patch) => {
                    setRecognitionDraft((prev) => {
                      const merged = { ...prev, ...patch };
                      applyRecognitionToStore(merged);
                      return merged;
                    });
                  }}
                  recognizing={recognizeLoading}
                  disabled={analyzeLoading}
                />
                <p className="text-[11px] text-terminal-muted">
                  Deterministic SMC levels come from verified Binance/Bybit OHLCV for the
                  confirmed symbol — never from the screenshot pixels alone.
                </p>
              </>
            )}

            <button
              type="button"
              disabled={analyzeDisabled}
              onClick={() => void runAnalyze()}
              className={cn(
                "h-10 w-full rounded-md text-sm font-medium transition",
                analyzeDisabled
                  ? "cursor-not-allowed bg-terminal-accent/40 text-terminal-bg"
                  : "bg-terminal-accent text-terminal-bg hover:opacity-90",
              )}
              data-testid="analyze-button"
            >
              {analyzeLabel}
            </button>

            {analyzeError ? (
              <p className="text-[11px] text-terminal-short">{analyzeError}</p>
            ) : null}
            {visionNote ? (
              <p className="text-[11px] text-amber-200" data-testid="vision-status">
                {visionNote}
              </p>
            ) : visionPhase === "running" ? (
              <p className="text-[11px] text-terminal-muted" data-testid="vision-status">
                Vision analysis running…
              </p>
            ) : analyzeResult?.vision_status === "ok" ? (
              <p className="text-[11px] text-terminal-long" data-testid="vision-status">
                Vision complete
              </p>
            ) : null}
            {analyzeResult?.persistence_status ? (
              <p className="text-[11px] text-terminal-muted" data-testid="persistence-status">
                {analyzeResult.persistence_status === "saved" ||
                analyzeResult.persistence_status === "idempotent"
                  ? "Saved to history"
                  : analyzeResult.persistence_status === "disabled"
                    ? "Persistence disabled"
                    : analyzeResult.persistence_detail ||
                      "History saving unavailable"}
              </p>
            ) : null}
            {analyzeResult?.analysis_mode ? (
              <p className="text-[10px] uppercase tracking-[0.12em] text-terminal-muted">
                Mode {analyzeResult.analysis_mode.replaceAll("_", " ")}
              </p>
            ) : null}
          </div>
        </div>

        <div className="rounded-lg border border-terminal-border bg-terminal-panel p-3 xl:block">
          <p className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
            Chart plan legend
          </p>
          {planLegend || snapshot ? (
            <div className="mt-2 space-y-2 text-xs text-terminal-text">
              {planLegend ? (
                <TradePlanChartStatusBadge status={planLegend.status} />
              ) : null}
              <p className="text-[10px] text-terminal-muted">
                Overlay lines use deterministic Entry / SL / TP values only.
              </p>
            </div>
          ) : (
            <p className="mt-2 text-sm text-terminal-muted">
              Entry / SL / TP appear on the chart when a plan is available.
            </p>
          )}
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col gap-4">
        <AnalyzerMarketOverview
          exchange={displayExchange}
          marketType={displayMarketType}
          symbol={displaySymbol}
          timeframe={displayTimeframe}
          analysisMode={mode}
          screenshotObservedPrice={screenshotObserved}
          verifiedPriceTimestamp={
            analyzeResult?.price_comparison?.verified_price_timestamp ?? null
          }
          verifiedPriceSource={
            analyzeResult?.price_comparison?.verified_price_source ?? null
          }
          error={
            tradePlanQuery.isError
              ? (tradePlanQuery.error as Error).message
              : decisionQuery.isError
                ? (decisionQuery.error as Error).message
                : null
          }
        />

        <div className="grid gap-4 lg:grid-cols-2">
          <AnalyzerDecisionStatus
            decision={decisionValue}
            reason={decisionReason}
            loading={
              decisionQuery.isLoading &&
              !decisionQuery.isFetched &&
              !liveDecision &&
              !snapshot
            }
          />
          <AnalyzerTradeLevels
            model={tradeLevelsModel}
            loading={
              tradePlanQuery.isLoading &&
              !tradePlanQuery.isFetched &&
              decisionQuery.isLoading &&
              !decisionQuery.isFetched &&
              !liveTradePlan &&
              !liveDecision &&
              !snapshot
            }
          />
        </div>

        <MarketChartPanel
          exchange={exchange}
          marketType={marketType}
          symbol={symbol}
          timeframe={timeframe}
          title={chartTitle}
          heightClass="h-[min(72vh,720px)]"
          chartOverlays={chartOverlays}
          structureOverlays={structureOverlays}
          liquidityOverlays={liquidityOverlays}
          obFvgOverlays={obFvgOverlays}
          enableTradePlanVisuals
          onTradePlanLegendChange={onTradePlanLegendChange}
          chartRef={chartHandleRef}
        />

        <SmcAnalysisSections
          exchange={exchange}
          marketType={marketType}
          symbol={symbol}
          timeframe={timeframe}
          structureOverlays={structureOverlays}
          onStructureOverlaysChange={setStructureOverlays}
          liquidityOverlays={liquidityOverlays}
          onLiquidityOverlaysChange={setLiquidityOverlays}
          obFvgOverlays={obFvgOverlays}
          onObFvgOverlaysChange={setObFvgOverlays}
          chartOverlays={chartOverlays}
          onChartOverlaysChange={setChartOverlays}
          decision={analyzeResult?.decision ?? decisionQuery.data ?? null}
          snapshot={snapshot}
        />

        {mode === "LIVE_MARKET" && previewUrl ? (
          <div className="rounded-lg border border-terminal-border bg-terminal-panel p-3">
            <p className="mb-2 text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
              Auto-captured chart (Vision input)
            </p>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={previewUrl}
              alt="Auto-captured live chart"
              className="max-h-[280px] w-full object-contain"
            />
          </div>
        ) : null}

        <PriceComparisonPanel
          comparison={analyzeResult?.price_comparison}
          analysisMode={analyzeResult?.analysis_mode}
        />

        <div className="grid gap-4 lg:grid-cols-3">
          <div className="space-y-2">
            <p className="text-[11px] uppercase tracking-[0.14em] text-terminal-accent">
              A. Deterministic engine results
            </p>
            <AiExplanationPanel explanation={analyzeResult?.explanation} />
          </div>
          <div className="space-y-2">
            <p className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
              B. AI visual observations
            </p>
            <VisionObservationsPanel vision={vision} />
            <VisionComparisonPanel
              comparison={comparison ?? analyzeResult?.explanation?.vision_comparison}
            />
          </div>
          <div className="space-y-2">
            <p className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
              C. Screenshot recognition / OCR
            </p>
            <ScreenshotRecognitionResultsPanel
              recognition={analyzeResult?.recognition}
              vision={vision}
            />
          </div>
        </div>
      </section>
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
