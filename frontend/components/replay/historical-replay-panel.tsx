"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronsLeft,
  ChevronsRight,
  History,
  Loader2,
  Pause,
  Play,
  RotateCcw,
  SkipForward,
  Square,
} from "lucide-react";
import { CandlestickChart } from "@/components/charts/candlestick-chart";
import { HistoricalAnalysisPanel } from "@/components/replay/historical-analysis-panel";
import { HistoricalTradeSimulationPanel } from "@/components/replay/historical-trade-simulation-panel";
import { HistoricalExecutionCostsPanel } from "@/components/replay/historical-execution-costs-panel";
import { HistoricalPerformanceAnalyticsPanel } from "@/components/replay/historical-performance-analytics-panel";
import { HistoricalBacktestReportPanel } from "@/components/replay/historical-backtest-report-panel";
import {
  HistoricalTradeDetailsPanel,
  HistoricalTradeOverlayControls,
} from "@/components/replay/historical-trade-overlay";
import { MarketControls } from "@/components/trading/market-controls";
import type { ReportExportKind } from "@/lib/backtest-report-display";
import {
  candlesFromReplaySnapshot,
  clampSeekIndex,
  formatReplayClock,
  replayProgressLabel,
  replayQualityTone,
  replayStatusLabel,
  scrubberEnabled,
  scrubberLabel,
} from "@/lib/replay-display";
import {
  DEFAULT_TRADE_CHART_TOGGLES,
  buildTradeVisuals,
  type TradeChartToggleState,
} from "@/lib/trade-chart-visuals";
import { api, ApiError } from "@/services/api";
import { replayWebsocket } from "@/services/replay-websocket";
import { useMarketStore } from "@/stores/market-store";
import type {
  HistoricalAnalysisSnapshot,
  ReplaySnapshot,
  ReplaySpeed,
  SimulationSnapshot,
  CostSnapshot,
  ExecutionCostConfigPublic,
  AnalyticsSnapshot,
  AnalyticsConfigPublic,
  BacktestReportSnapshot,
  Timeframe,
} from "@/types/api";
import { cn } from "@/utils/cn";

const SPEEDS: ReplaySpeed[] = ["1x", "2x", "5x", "10x", "50x", "100x", "max"];
const REPLAY_TFS: Timeframe[] = ["4h", "1h", "15m", "5m"];

function defaultRange(): { start: string; end: string } {
  const end = new Date();
  const start = new Date(end.getTime() - 3 * 24 * 60 * 60 * 1000);
  const toLocal = (d: Date) => {
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };
  return { start: toLocal(start), end: toLocal(end) };
}

export function HistoricalReplayPanel() {
  const { exchange, marketType, symbol, timeframe, setTimeframe } = useMarketStore();
  // Initialize eagerly so the first paint has a valid range (useEffect-only left empty fields).
  const [startLocal, setStartLocal] = useState(() => defaultRange().start);
  const [endLocal, setEndLocal] = useState(() => defaultRange().end);
  const [speed, setSpeed] = useState<ReplaySpeed>("10x");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<ReplaySnapshot | null>(null);
  const [analysis, setAnalysis] = useState<HistoricalAnalysisSnapshot | null>(null);
  const [analysisEnabled, setAnalysisEnabled] = useState(false);
  const [simulation, setSimulation] = useState<SimulationSnapshot | null>(null);
  const [simulationEnabled, setSimulationEnabled] = useState(false);
  const [costs, setCosts] = useState<CostSnapshot | null>(null);
  const [costsEnabled, setCostsEnabled] = useState(false);
  const [costConfig, setCostConfig] = useState<ExecutionCostConfigPublic | null>(null);
  const [analytics, setAnalytics] = useState<AnalyticsSnapshot | null>(null);
  const [analyticsEnabled, setAnalyticsEnabled] = useState(false);
  const [analyticsConfig, setAnalyticsConfig] = useState<AnalyticsConfigPublic | null>(null);
  const [report, setReport] = useState<BacktestReportSnapshot | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const [exportBusy, setExportBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [scrubIndex, setScrubIndex] = useState(0);
  const [seeking, setSeeking] = useState(false);
  const [tradeToggles, setTradeToggles] = useState<TradeChartToggleState>(
    DEFAULT_TRADE_CHART_TOGGLES,
  );
  const [selectedTradeEventId, setSelectedTradeEventId] = useState<string | null>(null);
  const seekSeqRef = useRef(0);
  const seekingRef = useRef(false);

  const chartTf: Timeframe = REPLAY_TFS.includes(timeframe) ? timeframe : "5m";

  useEffect(() => {
    if (!REPLAY_TFS.includes(timeframe)) setTimeframe("5m");
  }, [timeframe, setTimeframe]);

  useEffect(() => {
    if (!sessionId) return;
    replayWebsocket.connect(sessionId);
    const off = replayWebsocket.onMessage((msg) => {
      if (msg.session_id && msg.session_id !== sessionId) return;
      // Ignore mid-seek WS payloads so an older clock cannot overwrite a newer seek.
      if (seekingRef.current) return;
      if (msg.type === "replay_analysis_update") {
        const payload = msg.payload as HistoricalAnalysisSnapshot | undefined;
        if (payload && typeof payload.decision === "string") {
          setAnalysis(payload as HistoricalAnalysisSnapshot);
        }
        return;
      }
      if (msg.type === "simulation_snapshot" || msg.type === "simulation_enabled") {
        const payload = msg.payload as SimulationSnapshot | { disclaimer?: string } | undefined;
        if (payload && "overview" in payload && payload.overview) {
          setSimulation(payload as SimulationSnapshot);
          setSimulationEnabled(true);
        }
        return;
      }
      if (msg.type === "simulation_disabled") {
        setSimulationEnabled(false);
        return;
      }
      if (msg.type === "cost_model_enabled" || msg.type === "execution_cost_update") {
        const payload = msg.payload as CostSnapshot | { disclaimer?: string } | undefined;
        if (payload && "summary" in payload && payload.summary) {
          setCosts(payload as CostSnapshot);
          setCostsEnabled(true);
        } else if (msg.type === "cost_model_enabled") {
          setCostsEnabled(true);
        }
        return;
      }
      if (msg.type === "cost_model_disabled") {
        setCostsEnabled(false);
        return;
      }
      if (msg.type === "analytics_enabled" || msg.type === "analytics_summary_update") {
        if (msg.type === "analytics_enabled") setAnalyticsEnabled(true);
        if (sessionId) {
          void api.getReplayAnalytics(sessionId).then((res) => {
            if (seekingRef.current) return;
            setAnalytics(res.snapshot);
            setAnalyticsEnabled(res.analytics_enabled);
          });
          void api
            .getReplayReport(sessionId)
            .then((res) => {
              if (seekingRef.current) return;
              setReport(res.report);
              setReportError(null);
            })
            .catch(() => {
              /* ignore transient */
            });
        }
        return;
      }
      if (msg.type === "analytics_disabled") {
        setAnalyticsEnabled(false);
        setReport(null);
        return;
      }
      if (
        msg.type === "analytics_equity_update" ||
        msg.type === "analytics_drawdown_update" ||
        msg.type === "analytics_group_update"
      ) {
        if (sessionId) {
          void api.getReplayAnalytics(sessionId).then((res) => {
            if (seekingRef.current) return;
            setAnalytics(res.snapshot);
          });
          void api
            .getReplayReport(sessionId)
            .then((res) => {
              if (seekingRef.current) return;
              setReport(res.report);
              setReportError(null);
            })
            .catch(() => {
              /* ignore transient */
            });
        }
        return;
      }
      if (msg.type === "trade_pnl_update") {
        if (sessionId) {
          void api.getReplayCosts(sessionId).then((res) => {
            if (seekingRef.current) return;
            setCosts(res.snapshot);
          });
        }
        return;
      }
      if (
        msg.type === "trade_pending" ||
        msg.type === "trade_opened" ||
        msg.type === "trade_partially_closed" ||
        msg.type === "trade_closed" ||
        msg.type === "trade_cancelled" ||
        msg.type === "trade_rejected" ||
        msg.type === "trade_ambiguous"
      ) {
        if (sessionId) {
          void api.getReplaySimulation(sessionId).then((res) => {
            if (seekingRef.current) return;
            setSimulation(res.snapshot);
            setSimulationEnabled(res.simulation_enabled);
          });
        }
        return;
      }
      const payload = msg.payload as { snapshot?: ReplaySnapshot } | undefined;
      if (payload?.snapshot) {
        setSnapshot(payload.snapshot);
        setScrubIndex(payload.snapshot.event_index);
        return;
      }
      if (
        msg.type === "replay_error" ||
        msg.type === "replay_analysis_error" ||
        msg.type === "simulation_error"
      ) {
        setError(String((msg.payload as { error?: string })?.error ?? "Replay error"));
      }
    });
    return () => {
      off();
    };
  }, [sessionId]);

  const refreshAnalysis = useCallback(async (sid: string) => {
    try {
      const res = await api.getReplayAnalysis(sid);
      setAnalysisEnabled(res.analysis_enabled);
      setAnalysis(res.snapshot);
    } catch {
      /* ignore transient */
    }
  }, []);

  const refreshSimulation = useCallback(async (sid: string) => {
    try {
      const res = await api.getReplaySimulation(sid);
      setSimulationEnabled(res.simulation_enabled);
      setSimulation(res.snapshot);
    } catch {
      /* ignore transient */
    }
  }, []);

  const refreshCosts = useCallback(async (sid: string) => {
    try {
      const res = await api.getReplayCosts(sid);
      setCostsEnabled(res.costs_enabled);
      setCosts(res.snapshot);
      const cfg = await api.getReplayCostConfig(sid);
      setCostConfig(cfg.config);
    } catch {
      /* ignore transient */
    }
  }, []);

  const refreshAnalytics = useCallback(async (sid: string) => {
    try {
      const res = await api.getReplayAnalytics(sid);
      setAnalyticsEnabled(res.analytics_enabled);
      setAnalytics(res.snapshot);
      const cfg = await api.getReplayAnalyticsConfig(sid);
      setAnalyticsConfig(cfg.config);
    } catch {
      /* ignore transient */
    }
  }, []);

  const refreshReport = useCallback(async (sid: string) => {
    try {
      const res = await api.getReplayReport(sid);
      setReport(res.report);
      setReportError(null);
    } catch (e) {
      setReport(null);
      setReportError(
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Report failed",
      );
    }
  }, []);

  const applyControl = useCallback(
    async (fn: () => Promise<{ snapshot: ReplaySnapshot }>) => {
      setBusy(true);
      setError(null);
      try {
        const res = await fn();
        setSnapshot(res.snapshot);
        setScrubIndex(res.snapshot.event_index);
        if (sessionId && analysisEnabled) {
          await refreshAnalysis(sessionId);
        }
        if (sessionId && simulationEnabled) {
          await refreshSimulation(sessionId);
        }
        if (sessionId && costsEnabled) {
          await refreshCosts(sessionId);
        }
        if (sessionId && analyticsEnabled) {
          await refreshAnalytics(sessionId);
          await refreshReport(sessionId);
        }
      } catch (e) {
        setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Request failed");
      } finally {
        setBusy(false);
      }
    },
    [
      sessionId,
      analysisEnabled,
      simulationEnabled,
      costsEnabled,
      analyticsEnabled,
      refreshAnalysis,
      refreshSimulation,
      refreshCosts,
      refreshAnalytics,
      refreshReport,
    ],
  );

  const seekToIndex = useCallback(
    async (rawIndex: number) => {
      if (!sessionId || !snapshot) return;
      const target = clampSeekIndex(rawIndex, snapshot.event_count);
      const seq = ++seekSeqRef.current;
      seekingRef.current = true;
      setSeeking(true);
      setBusy(true);
      setError(null);
      setScrubIndex(target);
      setSelectedTradeEventId(null);
      // Drop panel rows immediately so a backward seek never shows future trades/costs.
      if (analysisEnabled) setAnalysis(null);
      if (simulationEnabled) setSimulation(null);
      if (costsEnabled) setCosts(null);
      if (analyticsEnabled) {
        setAnalytics(null);
        setReport(null);
      }
      try {
        const res = await api.seekReplay(sessionId, { event_index: target });
        if (seq !== seekSeqRef.current) return;
        setSnapshot(res.snapshot);
        setScrubIndex(res.snapshot.event_index);
        if (analysisEnabled) await refreshAnalysis(sessionId);
        if (seq !== seekSeqRef.current) return;
        if (simulationEnabled) await refreshSimulation(sessionId);
        if (seq !== seekSeqRef.current) return;
        if (costsEnabled) await refreshCosts(sessionId);
        if (seq !== seekSeqRef.current) return;
        if (analyticsEnabled) {
          await refreshAnalytics(sessionId);
          if (seq !== seekSeqRef.current) return;
          await refreshReport(sessionId);
        }
      } catch (e) {
        if (seq !== seekSeqRef.current) return;
        setError(
          e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Seek failed",
        );
        // Keep prior snapshot — do not clear panels on failure; restore scrub to clock.
        setScrubIndex(snapshot.event_index);
        if (analysisEnabled) await refreshAnalysis(sessionId);
        if (simulationEnabled) await refreshSimulation(sessionId);
        if (costsEnabled) await refreshCosts(sessionId);
        if (analyticsEnabled) {
          await refreshAnalytics(sessionId);
          await refreshReport(sessionId);
        }
      } finally {
        if (seq === seekSeqRef.current) {
          seekingRef.current = false;
          setSeeking(false);
          setBusy(false);
        }
      }
    },
    [
      sessionId,
      snapshot,
      analysisEnabled,
      simulationEnabled,
      costsEnabled,
      analyticsEnabled,
      refreshAnalysis,
      refreshSimulation,
      refreshCosts,
      refreshAnalytics,
      refreshReport,
    ],
  );

  const loadHistorical = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const startDate = new Date(startLocal);
      const endDate = new Date(endLocal);
      if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
        throw new Error("Start and end times are required.");
      }
      if (endDate <= startDate) {
        throw new Error("End time must be after start time.");
      }
      const startIso = startDate.toISOString();
      const endIso = endDate.toISOString();
      if (sessionId) {
        try {
          await api.deleteReplaySession(sessionId);
        } catch {
          /* ignore */
        }
      }
      const res = await api.createReplaySession({
        exchange,
        symbol,
        market_type: marketType,
        start_time: startIso,
        end_time: endIso,
        timeframes: REPLAY_TFS,
        speed,
      });
      setSessionId(res.session.session_id);
      setSnapshot(res.snapshot);
      setScrubIndex(res.snapshot.event_index);
      setSelectedTradeEventId(null);
      setAnalysis(null);
      setAnalysisEnabled(false);
      setSimulation(null);
      setSimulationEnabled(false);
      setCosts(null);
      setCostsEnabled(false);
      setCostConfig(null);
      setAnalytics(null);
      setAnalyticsEnabled(false);
      setAnalyticsConfig(null);
      setReport(null);
      setReportError(null);
      if (res.session.status === "error") {
        setError(res.session.error ?? "Insufficient historical data");
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Load failed");
      setSnapshot(null);
      setSessionId(null);
      setAnalysis(null);
      setAnalysisEnabled(false);
      setSimulation(null);
      setSimulationEnabled(false);
      setCosts(null);
      setCostsEnabled(false);
      setCostConfig(null);
      setAnalytics(null);
      setAnalyticsEnabled(false);
      setAnalyticsConfig(null);
      setReport(null);
      setReportError(null);
    } finally {
      setLoading(false);
    }
  }, [startLocal, endLocal, sessionId, exchange, symbol, marketType, speed]);

  const toggleAnalysis = async () => {
    if (!sessionId) return;
    setBusy(true);
    setError(null);
    try {
      if (analysisEnabled) {
        const res = await api.disableReplayAnalysis(sessionId);
        setAnalysisEnabled(false);
        setAnalysis(res.snapshot);
      } else {
        const res = await api.enableReplayAnalysis(sessionId);
        setAnalysisEnabled(true);
        setAnalysis(res.snapshot);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Analysis toggle failed");
    } finally {
      setBusy(false);
    }
  };

  const toggleSimulation = async () => {
    if (!sessionId) return;
    setBusy(true);
    setError(null);
    try {
      if (simulationEnabled) {
        const res = await api.disableReplaySimulation(sessionId);
        setSimulationEnabled(false);
        setSimulation(res.snapshot);
        setSelectedTradeEventId(null);
      } else {
        const res = await api.enableReplaySimulation(sessionId);
        setSimulationEnabled(true);
        setAnalysisEnabled(res.analysis_enabled);
        setSimulation(res.snapshot);
        await refreshAnalysis(sessionId);
      }
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Simulation toggle failed",
      );
    } finally {
      setBusy(false);
    }
  };

  const toggleCosts = async () => {
    if (!sessionId) return;
    setBusy(true);
    setError(null);
    try {
      if (costsEnabled) {
        const res = await api.disableReplayCosts(sessionId);
        setCostsEnabled(false);
        setCosts(res.snapshot);
      } else {
        const res = await api.enableReplayCosts(sessionId);
        setCostsEnabled(true);
        setSimulationEnabled(res.simulation_enabled);
        setAnalysisEnabled(res.analysis_enabled);
        setCosts(res.snapshot);
        await refreshSimulation(sessionId);
        await refreshAnalysis(sessionId);
        const cfg = await api.getReplayCostConfig(sessionId);
        setCostConfig(cfg.config);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Costs toggle failed");
    } finally {
      setBusy(false);
    }
  };

  const toggleAnalytics = async () => {
    if (!sessionId) return;
    setBusy(true);
    setError(null);
    try {
      if (analyticsEnabled) {
        const res = await api.disableReplayAnalytics(sessionId);
        setAnalyticsEnabled(false);
        setAnalytics(res.snapshot ?? null);
        setReport(null);
        setReportError(null);
      } else {
        const res = await api.enableReplayAnalytics(sessionId);
        setAnalyticsEnabled(true);
        setCostsEnabled(res.costs_enabled);
        setSimulationEnabled(res.simulation_enabled);
        setAnalysisEnabled(res.analysis_enabled);
        setAnalytics(res.snapshot ?? null);
        await refreshCosts(sessionId);
        await refreshSimulation(sessionId);
        await refreshAnalysis(sessionId);
        const cfg = await api.getReplayAnalyticsConfig(sessionId);
        setAnalyticsConfig(cfg.config);
        await refreshReport(sessionId);
      }
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Analytics toggle failed",
      );
    } finally {
      setBusy(false);
    }
  };

  const saveAnalyticsConfig = async (
    patch: Partial<AnalyticsConfigPublic> & { clear_initial_equity?: boolean },
  ) => {
    if (!sessionId) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.updateReplayAnalyticsConfig(sessionId, patch);
      setAnalytics(res.snapshot ?? null);
      setAnalyticsEnabled(res.analytics_enabled);
      const cfg = await api.getReplayAnalyticsConfig(sessionId);
      setAnalyticsConfig(cfg.config);
      if (res.analytics_enabled) await refreshReport(sessionId);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Analytics config failed",
      );
    } finally {
      setBusy(false);
    }
  };

  const applyAnalyticsFilter = async (direction: string | null) => {
    if (!sessionId) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.updateReplayAnalyticsFilter(sessionId, { direction });
      setAnalytics(res.snapshot ?? null);
      if (res.analytics_enabled) await refreshReport(sessionId);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Analytics filter failed",
      );
    } finally {
      setBusy(false);
    }
  };

  const exportReportCsv = async (kind: ReportExportKind) => {
    if (!sessionId) return;
    setExportBusy(true);
    setReportError(null);
    try {
      await api.downloadReplayReportCsv(sessionId, kind);
    } catch (e) {
      setReportError(
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : "CSV export failed",
      );
    } finally {
      setExportBusy(false);
    }
  };

  const exportReportPdf = async () => {
    if (!sessionId) return;
    setExportBusy(true);
    setReportError(null);
    try {
      await api.downloadReplayReportPdf(sessionId);
    } catch (e) {
      setReportError(
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : "PDF export failed",
      );
    } finally {
      setExportBusy(false);
    }
  };

  const saveCostConfig = async (patch: Partial<ExecutionCostConfigPublic>) => {
    if (!sessionId) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.updateReplayCostConfig(sessionId, patch);
      setCosts(res.snapshot);
      setCostsEnabled(res.costs_enabled);
      const cfg = await api.getReplayCostConfig(sessionId);
      setCostConfig(cfg.config);
      if (analyticsEnabled) {
        await refreshAnalytics(sessionId);
        await refreshReport(sessionId);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Config update failed");
    } finally {
      setBusy(false);
    }
  };

  const qaAnchorRef = useRef<HTMLHeadingElement | null>(null);

  const { closed, forming } = candlesFromReplaySnapshot(snapshot, chartTf);
  const status = snapshot?.status ?? null;

  const tradeVisuals = useMemo(() => {
    if (!simulationEnabled || !simulation || seeking) {
      return { markers: [], priceLines: [], visible: [], details: null };
    }
    return buildTradeVisuals({
      trades: simulation.trades,
      replayTimestamp: snapshot?.replay_timestamp ?? null,
      toggles: tradeToggles,
      costs,
      selectedEventId: selectedTradeEventId,
    });
  }, [
    simulationEnabled,
    simulation,
    seeking,
    snapshot?.replay_timestamp,
    tradeToggles,
    costs,
    selectedTradeEventId,
  ]);

  // Attach automation hooks on a DOM node (render-time window writes can be stripped).
  useEffect(() => {
    const el = qaAnchorRef.current as (HTMLHeadingElement & {
      __qa?: Record<string, unknown>;
    }) | null;
    if (!el) return;
    const hooks = {
      loadHistorical,
      toggleAnalysis,
      toggleSimulation,
      toggleCosts,
      toggleAnalytics,
      stepReplay: async () => {
        if (!sessionId) return;
        await applyControl(() => api.stepReplay(sessionId));
      },
      resetReplay: async () => {
        if (!sessionId) return;
        await applyControl(() => api.resetReplay(sessionId));
      },
      seekToIndex,
      saveCostConfig,
      saveAnalyticsConfig,
      getTradeVisuals: () => tradeVisuals,
      setTradeToggles,
    };
    el.__qa = hooks;
    const w = window as Window & { __qaReplay?: typeof hooks };
    w.__qaReplay = hooks;
  });
  const canControl = Boolean(sessionId) && !loading;

  return (
    <div className="flex h-full min-h-[calc(100dvh-4rem)] flex-col gap-4 p-4 md:p-5 xl:flex-row">
      <aside className="w-full shrink-0 space-y-4 xl:w-80">
        <div className="rounded-lg border border-terminal-border bg-terminal-panel p-4">
          <h1
            ref={qaAnchorRef}
            data-qa-hooks="v2"
            className="flex items-center gap-2 font-display text-lg font-semibold text-terminal-text"
          >
            <History className="h-5 w-5 text-terminal-accent" />
            Historical Replay
          </h1>
          <p className="mt-1 text-xs text-terminal-muted">
            Deterministic multi-TF replay, historical analysis, and hypothetical trade simulation.
            Simulation fills are not real orders.
          </p>

          <div className="mt-4 space-y-3">
            <Field label="Exchange / market">
              <div className="rounded-md border border-terminal-border bg-terminal-surface px-3 py-2 text-sm capitalize text-terminal-text">
                {exchange} · {marketType.replaceAll("_", " ")}
              </div>
            </Field>
            <MarketControls showTimeframe={false} />

            <Field label="Start (local)">
              <input
                type="datetime-local"
                value={startLocal}
                onChange={(e) => setStartLocal(e.target.value)}
                className="h-10 w-full rounded-md border border-terminal-border bg-terminal-surface px-3 text-sm text-terminal-text outline-none focus:border-terminal-accent"
              />
            </Field>
            <Field label="End (local)">
              <input
                type="datetime-local"
                value={endLocal}
                onChange={(e) => setEndLocal(e.target.value)}
                className="h-10 w-full rounded-md border border-terminal-border bg-terminal-surface px-3 text-sm text-terminal-text outline-none focus:border-terminal-accent"
              />
            </Field>

            <Field label="Replay speed">
              <select
                value={speed}
                onChange={async (e) => {
                  const next = e.target.value as ReplaySpeed;
                  setSpeed(next);
                  if (sessionId) {
                    await applyControl(() => api.setReplaySpeed(sessionId, next));
                  }
                }}
                className="h-10 w-full rounded-md border border-terminal-border bg-terminal-surface px-3 text-sm text-terminal-text outline-none focus:border-terminal-accent"
              >
                {SPEEDS.map((s) => (
                  <option key={s} value={s}>
                    {s === "max" ? "Max / instant" : s}
                  </option>
                ))}
              </select>
            </Field>

            <button
              type="button"
              onClick={loadHistorical}
              disabled={loading}
              className="flex h-10 w-full items-center justify-center gap-2 rounded-md bg-terminal-accent px-3 text-sm font-medium text-terminal-bg disabled:opacity-50"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Load Historical Data
            </button>

            <button
              type="button"
              onClick={toggleAnalysis}
              disabled={!canControl || busy}
              className={cn(
                "flex h-10 w-full items-center justify-center gap-2 rounded-md border px-3 text-sm disabled:opacity-50",
                analysisEnabled
                  ? "border-terminal-accent/50 bg-terminal-accent/15 text-terminal-accent"
                  : "border-terminal-border bg-terminal-surface text-terminal-text",
              )}
            >
              {analysisEnabled ? "Disable Historical Analysis" : "Enable Historical Analysis"}
            </button>

            <button
              type="button"
              onClick={toggleSimulation}
              disabled={!canControl || busy}
              className={cn(
                "flex h-10 w-full items-center justify-center gap-2 rounded-md border px-3 text-sm disabled:opacity-50",
                simulationEnabled
                  ? "border-amber-400/50 bg-amber-400/10 text-amber-200"
                  : "border-terminal-border bg-terminal-surface text-terminal-text",
              )}
            >
              {simulationEnabled ? "Disable Trade Simulation" : "Enable Trade Simulation"}
            </button>

            <button
              type="button"
              onClick={toggleCosts}
              disabled={!canControl || busy}
              className={cn(
                "flex h-10 w-full items-center justify-center gap-2 rounded-md border px-3 text-sm disabled:opacity-50",
                costsEnabled
                  ? "border-emerald-400/50 bg-emerald-400/10 text-emerald-200"
                  : "border-terminal-border bg-terminal-surface text-terminal-text",
              )}
            >
              {costsEnabled ? "Disable Execution Costs" : "Enable Execution Costs"}
            </button>

            <button
              type="button"
              onClick={toggleAnalytics}
              disabled={!canControl || busy}
              className={cn(
                "flex h-10 w-full items-center justify-center gap-2 rounded-md border px-3 text-sm disabled:opacity-50",
                analyticsEnabled
                  ? "border-sky-400/50 bg-sky-400/10 text-sky-200"
                  : "border-terminal-border bg-terminal-surface text-terminal-text",
              )}
            >
              {analyticsEnabled ? "Disable Performance Analytics" : "Enable Performance Analytics"}
            </button>

            <div className="grid grid-cols-2 gap-2">
              <ControlBtn
                disabled={!canControl || busy || status === "running"}
                onClick={() => sessionId && applyControl(() => api.startReplay(sessionId))}
                icon={<Play className="h-3.5 w-3.5" />}
                label="Start"
              />
              <ControlBtn
                disabled={!canControl || busy || status !== "running"}
                onClick={() => sessionId && applyControl(() => api.pauseReplay(sessionId))}
                icon={<Pause className="h-3.5 w-3.5" />}
                label="Pause"
              />
              <ControlBtn
                disabled={!canControl || busy || status !== "paused"}
                onClick={() => sessionId && applyControl(() => api.resumeReplay(sessionId))}
                icon={<Play className="h-3.5 w-3.5" />}
                label="Resume"
              />
              <ControlBtn
                disabled={!canControl || busy}
                onClick={() => sessionId && applyControl(() => api.stepReplay(sessionId))}
                icon={<SkipForward className="h-3.5 w-3.5" />}
                label="Step"
              />
              <ControlBtn
                disabled={!canControl || busy}
                onClick={() => sessionId && applyControl(() => api.resetReplay(sessionId))}
                icon={<RotateCcw className="h-3.5 w-3.5" />}
                label="Reset"
              />
              <ControlBtn
                disabled={!canControl || busy}
                onClick={() => sessionId && applyControl(() => api.stopReplay(sessionId))}
                icon={<Square className="h-3.5 w-3.5" />}
                label="Stop"
              />
            </div>

            {/* Phase 5.2.7 — Timeline scrubber (seek). Commits on release to avoid request storms. */}
            <div className="space-y-2 rounded-md border border-terminal-border/70 bg-terminal-bg/40 p-3">
              <div className="flex items-center justify-between gap-2 text-[11px] text-terminal-muted">
                <span className="inline-flex items-center gap-1.5">
                  Timeline scrub
                  {seeking ? <Loader2 className="h-3 w-3 animate-spin text-emerald-400" /> : null}
                </span>
                <span className="font-mono text-terminal-text">
                  {scrubberLabel(scrubIndex, snapshot?.event_count ?? 0)}
                  {seeking ? " · seeking…" : ""}
                </span>
              </div>
              <div className="font-mono text-[10px] text-terminal-muted">
                Clock: {formatReplayClock(snapshot?.replay_timestamp)}
              </div>
              <input
                type="range"
                min={0}
                max={Math.max(0, (snapshot?.event_count ?? 1) - 1)}
                step={1}
                value={scrubIndex}
                disabled={
                  !scrubberEnabled(snapshot, {
                    sessionReady: Boolean(canControl),
                    busy: busy && !seeking,
                  })
                }
                onChange={(e) => setScrubIndex(Number(e.target.value))}
                onMouseUp={() => void seekToIndex(scrubIndex)}
                onTouchEnd={() => void seekToIndex(scrubIndex)}
                onKeyUp={(e) => {
                  if (e.key === "ArrowLeft" || e.key === "ArrowRight" || e.key === "Home" || e.key === "End") {
                    void seekToIndex(scrubIndex);
                  }
                }}
                aria-label="Replay timeline scrubber"
                className="w-full accent-emerald-400 disabled:opacity-40"
              />
              <div className="grid grid-cols-3 gap-2">
                <ControlBtn
                  disabled={!scrubberEnabled(snapshot, { sessionReady: Boolean(canControl), busy })}
                  onClick={() => void seekToIndex(0)}
                  icon={<ChevronsLeft className="h-3.5 w-3.5" />}
                  label="Start"
                />
                <ControlBtn
                  disabled={!scrubberEnabled(snapshot, { sessionReady: Boolean(canControl), busy })}
                  onClick={() =>
                    void seekToIndex(
                      clampSeekIndex(
                        Math.floor(((snapshot?.event_count ?? 1) - 1) / 2),
                        snapshot?.event_count ?? 0,
                      ),
                    )
                  }
                  icon={<SkipForward className="h-3.5 w-3.5" />}
                  label="Middle"
                />
                <ControlBtn
                  disabled={!scrubberEnabled(snapshot, { sessionReady: Boolean(canControl), busy })}
                  onClick={() =>
                    void seekToIndex(
                      clampSeekIndex(
                        (snapshot?.event_count ?? 1) - 1,
                        snapshot?.event_count ?? 0,
                      ),
                    )
                  }
                  icon={<ChevronsRight className="h-3.5 w-3.5" />}
                  label="End"
                />
              </div>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-terminal-border bg-terminal-panel p-4 text-sm">
          <Row label="Status" value={replayStatusLabel(status)} />
          <Row label="Replay clock" value={formatReplayClock(snapshot?.replay_timestamp)} />
          <Row label="Progress" value={replayProgressLabel(snapshot)} />
          <Row
            label="Data quality"
            value={
              <span className={cn(replayQualityTone(snapshot?.data_quality))}>
                {snapshot?.data_quality ?? "—"}
              </span>
            }
          />
          <Row
            label="Closed / forming"
            value={
              snapshot
                ? `${snapshot.timeframes[chartTf]?.closed_count ?? 0} closed · ${
                    forming ? "forming" : "—"
                  }`
                : "—"
            }
          />
          {snapshot?.limitations?.length ? (
            <ul className="mt-3 space-y-1 text-[11px] text-amber-400">
              {snapshot.limitations.slice(0, 6).map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          ) : null}
          {error ? <p className="mt-3 text-xs text-terminal-short">{error}</p> : null}
        </div>

        <HistoricalAnalysisPanel
          analysis={analysis}
          enabled={analysisEnabled}
          busy={busy && analysisEnabled}
        />

        <HistoricalTradeSimulationPanel
          snapshot={simulation}
          enabled={simulationEnabled}
          busy={busy && simulationEnabled}
        />

        <HistoricalExecutionCostsPanel
          snapshot={costs}
          enabled={costsEnabled}
          busy={busy && costsEnabled}
          config={costConfig}
          onSaveConfig={saveCostConfig}
        />

        <HistoricalPerformanceAnalyticsPanel
          snapshot={analytics}
          enabled={analyticsEnabled}
          busy={busy && analyticsEnabled}
          config={analyticsConfig}
          onSaveConfig={saveAnalyticsConfig}
          onFilter={applyAnalyticsFilter}
        />

        <HistoricalBacktestReportPanel
          report={report}
          enabled={analyticsEnabled}
          busy={busy && analyticsEnabled}
          exportBusy={exportBusy}
          error={reportError}
          onRefresh={sessionId ? () => refreshReport(sessionId) : undefined}
          onFilterDirection={applyAnalyticsFilter}
          onExportCsv={exportReportCsv}
          onExportPdf={exportReportPdf}
        />
      </aside>

      <main className="min-w-0 flex-1 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-terminal-border bg-terminal-panel px-4 py-3">
          <div>
            <p className="text-sm font-medium text-terminal-text">
              {symbol} · {chartTf} · historical
            </p>
            <p className="text-[11px] text-terminal-muted">
              Chart shows only candles known at the replay clock. Future bars are hidden.
            </p>
          </div>
          <div className="flex gap-1">
            {REPLAY_TFS.map((tf) => (
              <button
                key={tf}
                type="button"
                onClick={() => setTimeframe(tf)}
                className={cn(
                  "rounded px-2 py-1 text-xs",
                  chartTf === tf
                    ? "bg-terminal-accent/20 text-terminal-accent"
                    : "text-terminal-muted hover:text-terminal-text",
                )}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>

        <div className="min-h-[420px] overflow-hidden rounded-lg border border-terminal-border bg-terminal-panel">
          {loading ? (
            <div className="flex h-[420px] items-center justify-center text-sm text-terminal-muted">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading historical candles…
            </div>
          ) : closed.length === 0 && !forming ? (
            <div className="flex h-[420px] items-center justify-center text-sm text-terminal-muted">
              Load a historical range to begin replay.
            </div>
          ) : (
            <CandlestickChart
              candles={closed}
              liveCandle={
                forming
                  ? {
                      exchange: forming.exchange,
                      marketType: forming.market_type,
                      symbol: forming.symbol,
                      timeframe: chartTf,
                      timestamp: forming.timestamp,
                      open: forming.open,
                      high: forming.high,
                      low: forming.low,
                      close: forming.close,
                      volume: forming.volume,
                      isClosed: false,
                      processedAt: snapshot?.replay_timestamp ?? forming.timestamp,
                    }
                  : null
              }
              seriesKey={`${sessionId ?? "none"}:${chartTf}:${snapshot?.event_index ?? 0}`}
              className="h-[520px] w-full"
              tradeMarkers={tradeVisuals.markers}
              tradePriceLines={tradeVisuals.priceLines}
              onTradeMarkerClick={(id) => setSelectedTradeEventId(id)}
            />
          )}
        </div>

        {simulationEnabled ? (
          <HistoricalTradeOverlayControls
            toggles={tradeToggles}
            onChange={setTradeToggles}
            disabled={!simulation || seeking}
          />
        ) : null}

        <HistoricalTradeDetailsPanel
          details={tradeVisuals.details}
          onClose={() => setSelectedTradeEventId(null)}
        />

        {simulationEnabled && simulation ? (
          <SimulationChartLegend
            simulation={simulation}
            replayTimestamp={snapshot?.replay_timestamp ?? null}
          />
        ) : null}

        {status === "completed" ? (
          <p className="text-center text-xs text-terminal-long">Replay completed — end of range.</p>
        ) : null}
      </main>
    </div>
  );
}

function SimulationChartLegend({
  simulation,
  replayTimestamp,
}: {
  simulation: SimulationSnapshot;
  replayTimestamp: string | null;
}) {
  const clockMs = replayTimestamp ? new Date(replayTimestamp).getTime() : Number.POSITIVE_INFINITY;
  const visible = simulation.trades.filter((t) => {
    if (t.lifecycle_status === "rejected" || t.lifecycle_status === "cancelled") return false;
    const decisionMs = new Date(t.decision_timestamp).getTime();
    return decisionMs <= clockMs;
  });
  if (!visible.length) return null;
  return (
    <div className="rounded-lg border border-amber-400/30 bg-terminal-panel px-4 py-3 text-xs">
      <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.14em] text-amber-300/90">
        HISTORICAL SIMULATION — NOT REAL ORDERS
      </p>
      <div className="space-y-2">
        {visible.slice(0, 6).map((t) => {
          const entryKnown =
            t.entry_timestamp != null && new Date(t.entry_timestamp).getTime() <= clockMs;
          const exitKnown =
            t.exit_timestamp != null && new Date(t.exit_timestamp).getTime() <= clockMs;
          return (
            <div key={t.trade_id} className="flex flex-wrap gap-x-4 gap-y-1 text-terminal-muted">
              <span className="text-terminal-text">
                {t.direction} · {t.lifecycle_status}
              </span>
              <span>
                Entry zone / limit: {t.entry_limit_price ?? "—"}
                {entryKnown ? ` → filled ${t.entry_price}` : " (pending)"}
              </span>
              <span>SL {t.current_stop_loss}</span>
              <span>TP {t.take_profit_levels.join(", ") || "—"}</span>
              {exitKnown ? <span>Exit @ {formatReplayClock(t.exit_timestamp)}</span> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">{label}</span>
      {children}
    </label>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-terminal-border/60 py-2 last:border-0">
      <span className="text-[11px] uppercase tracking-[0.12em] text-terminal-muted">{label}</span>
      <span className="text-right text-xs text-terminal-text">{value}</span>
    </div>
  );
}

function ControlBtn({
  label,
  icon,
  onClick,
  disabled,
}: {
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="flex h-9 items-center justify-center gap-1.5 rounded-md border border-terminal-border bg-terminal-surface text-xs text-terminal-text disabled:opacity-40"
    >
      {icon}
      {label}
    </button>
  );
}
