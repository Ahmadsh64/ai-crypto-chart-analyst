import type {
  CandlesResponse,
  ExchangesResponse,
  HealthResponse,
  IndicatorsResponse,
  LiquidityResponse,
  ObFvgResponse,
  MultiTimeframeResponse,
  ConfluenceResponse,
  TradePlanResponse,
  DecisionResponse,
  MarketStructureResponse,
  MarketType,
  MarketsResponse,
  ExchangeId,
  TickerResponse,
  Timeframe,
  CreateReplaySessionRequest,
  ReplaySessionResponse,
  ReplayControlResponse,
  ReplaySpeed,
  ReplayAnalysisToggleResponse,
  ReplayAnalysisCurrentResponse,
  HistoricalAnalysisSnapshot,
  ReplaySimulationToggleResponse,
  ReplaySimulationCurrentResponse,
  SimulatedTrade,
  SimulationExecutionEvent,
  ReplayCostToggleResponse,
  ReplayCostCurrentResponse,
  CostSnapshot,
  ExecutionCostConfigPublic,
  LedgerEntry,
  TradeCostSummary,
  ReplayAnalyticsToggleResponse,
  ReplayAnalyticsCurrentResponse,
  AnalyticsConfigPublic,
  AnalyticsSnapshot,
  ReplayReportResponse,
  ReportCsvKind,
  AiAnalyzeResponse,
  AiVisionAnalyzeResponse,
  AiCompareResponse,
  AnalysisSnapshot,
  VisionResult,
  AnalysisHistoryListParams,
  AnalysisHistoryListResponse,
  AnalysisHistoryDetail,
  OpportunityListResponse,
  OpportunityStatus,
  ScannerStatusResponse,
  ScanTriggerResponse,
} from "@/types/api";
import {
  downloadBlob,
  filenameFromContentDisposition,
} from "@/lib/download";
import { getAccessToken } from "@/lib/supabase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function formatApiDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object") {
    const obj = detail as { message?: unknown; code?: unknown; detail?: unknown };
    if (typeof obj.message === "string" && obj.message.trim()) {
      return typeof obj.code === "string" ? `${obj.code}: ${obj.message}` : obj.message;
    }
    if (typeof obj.detail === "string" && obj.detail.trim()) return obj.detail;
  }
  return fallback;
}

async function buildHeaders(
  initHeaders?: HeadersInit,
  options?: { json?: boolean },
): Promise<Record<string, string>> {
  const headers: Record<string, string> = {};
  if (options?.json !== false) {
    headers["Content-Type"] = "application/json";
  }
  if (initHeaders) {
    const extra = new Headers(initHeaders);
    extra.forEach((value, key) => {
      headers[key] = value;
    });
  }
  const token = await getAccessToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: await buildHeaders(init?.headers),
    cache: "no-store",
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      detail = formatApiDetail(body.detail, response.statusText);
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, response.status);
  }

  return response.json() as Promise<T>;
}

function qs(params: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") sp.set(key, String(value));
  }
  const query = sp.toString();
  return query ? `?${query}` : "";
}

export const api = {
  baseUrl: API_URL,
  health: (signal?: AbortSignal) => request<HealthResponse>("/api/v1/health", { signal }),
  exchanges: (signal?: AbortSignal) =>
    request<ExchangesResponse>("/api/v1/exchanges", { signal }),
  markets: (
    exchange: ExchangeId,
    marketType: MarketType,
    search?: string,
    signal?: AbortSignal,
  ) =>
    request<MarketsResponse>(
      `/api/v1/markets${qs({ exchange, market_type: marketType, search })}`,
      { signal },
    ),
  candles: (
    args: {
      exchange: ExchangeId;
      marketType: MarketType;
      symbol: string;
      timeframe: Timeframe;
      limit?: number;
    },
    signal?: AbortSignal,
  ) =>
    request<CandlesResponse>(
      `/api/v1/market/candles${qs({
        exchange: args.exchange,
        market_type: args.marketType,
        symbol: args.symbol,
        timeframe: args.timeframe,
        limit: args.limit ?? 300,
      })}`,
      { signal },
    ),
  ticker: (
    args: { exchange: ExchangeId; marketType: MarketType; symbol: string },
    signal?: AbortSignal,
  ) =>
    request<TickerResponse>(
      `/api/v1/market/ticker${qs({
        exchange: args.exchange,
        market_type: args.marketType,
        symbol: args.symbol,
      })}`,
      { signal },
    ),
  indicators: (
    args: {
      exchange: ExchangeId;
      marketType: MarketType;
      symbol: string;
      timeframe: Timeframe;
      indicators?: string;
      includeForming?: boolean;
      includeSeries?: boolean;
      limit?: number;
    },
    signal?: AbortSignal,
  ) =>
    request<IndicatorsResponse>(
      `/api/v1/indicators${qs({
        exchange: args.exchange,
        market_type: args.marketType,
        symbol: args.symbol,
        timeframe: args.timeframe,
        indicators: args.indicators,
        include_forming: args.includeForming ? "true" : undefined,
        include_series: args.includeSeries ? "true" : undefined,
        limit: args.limit ?? 500,
      })}`,
      { signal },
    ),
  marketStructure: (
    args: {
      exchange: ExchangeId;
      marketType: MarketType;
      symbol: string;
      timeframe: Timeframe;
      limit?: number;
      includeUnconfirmed?: boolean;
    },
    signal?: AbortSignal,
  ) =>
    request<MarketStructureResponse>(
      `/api/v1/market-structure${qs({
        exchange: args.exchange,
        market_type: args.marketType,
        symbol: args.symbol,
        timeframe: args.timeframe,
        limit: args.limit ?? 500,
        include_unconfirmed: args.includeUnconfirmed ? "true" : undefined,
      })}`,
      { signal },
    ),
  liquidity: (
    args: {
      exchange: ExchangeId;
      marketType: MarketType;
      symbol: string;
      timeframe: Timeframe;
      limit?: number;
      includeUnconfirmed?: boolean;
    },
    signal?: AbortSignal,
  ) =>
    request<LiquidityResponse>(
      `/api/v1/liquidity${qs({
        exchange: args.exchange,
        market_type: args.marketType,
        symbol: args.symbol,
        timeframe: args.timeframe,
        limit: args.limit ?? 500,
        include_unconfirmed: args.includeUnconfirmed ? "true" : undefined,
      })}`,
      { signal },
    ),
  obFvg: (
    args: {
      exchange: ExchangeId;
      marketType: MarketType;
      symbol: string;
      timeframe: Timeframe;
      limit?: number;
      includeUnconfirmed?: boolean;
    },
    signal?: AbortSignal,
  ) =>
    request<ObFvgResponse>(
      `/api/v1/ob-fvg${qs({
        exchange: args.exchange,
        market_type: args.marketType,
        symbol: args.symbol,
        timeframe: args.timeframe,
        limit: args.limit ?? 500,
        include_unconfirmed: args.includeUnconfirmed ? "true" : undefined,
      })}`,
      { signal },
    ),
  multiTimeframe: (
    args: {
      exchange: ExchangeId;
      marketType: MarketType;
      symbol: string;
    },
    signal?: AbortSignal,
  ) =>
    request<MultiTimeframeResponse>(
      `/api/v1/multi-timeframe${qs({
        exchange: args.exchange,
        market_type: args.marketType,
        symbol: args.symbol,
      })}`,
      { signal },
    ),
  confluence: (
    args: {
      exchange: ExchangeId;
      marketType: MarketType;
      symbol: string;
    },
    signal?: AbortSignal,
  ) =>
    request<ConfluenceResponse>(
      `/api/v1/confluence${qs({
        exchange: args.exchange,
        market_type: args.marketType,
        symbol: args.symbol,
      })}`,
      { signal },
    ),
  tradePlan: (
    args: {
      exchange: ExchangeId;
      marketType: MarketType;
      symbol: string;
      accountBalance?: number;
      riskPercent?: number;
    },
    signal?: AbortSignal,
  ) =>
    request<TradePlanResponse>(
      `/api/v1/trade-plan${qs({
        exchange: args.exchange,
        market_type: args.marketType,
        symbol: args.symbol,
        account_balance: args.accountBalance,
        risk_percent: args.riskPercent,
      })}`,
      { signal },
    ),
  decision: (
    args: {
      exchange: ExchangeId;
      marketType: MarketType;
      symbol: string;
      accountBalance?: number;
      riskPercent?: number;
    },
    signal?: AbortSignal,
  ) =>
    request<DecisionResponse>(
      `/api/v1/decision${qs({
        exchange: args.exchange,
        market_type: args.marketType,
        symbol: args.symbol,
        account_balance: args.accountBalance,
        risk_percent: args.riskPercent,
      })}`,
      { signal },
    ),
  aiAnalyze: (
    args: {
      exchange: ExchangeId;
      marketType: MarketType;
      symbol: string;
      timeframe?: string;
      accountBalance?: number;
      riskPercent?: number;
      includeExplanation?: boolean;
    },
    signal?: AbortSignal,
  ) =>
    request<AiAnalyzeResponse>("/api/v1/ai/analyze", {
      method: "POST",
      body: JSON.stringify({
        exchange: args.exchange,
        market_type: args.marketType,
        symbol: args.symbol,
        timeframe: args.timeframe,
        account_balance: args.accountBalance,
        risk_percent: args.riskPercent,
        include_explanation: args.includeExplanation ?? true,
      }),
      signal,
    }),
  aiVisionAnalyze: async (file: File, signal?: AbortSignal) => {
    const form = new FormData();
    form.append("file", file);
    const response = await fetch(`${API_URL}/api/v1/ai/vision/analyze`, {
      method: "POST",
      body: form,
      headers: await buildHeaders(undefined, { json: false }),
      signal,
      cache: "no-store",
    });
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = (await response.json()) as {
          detail?: string | { code?: string; message?: string };
        };
        if (typeof body.detail === "string") detail = body.detail;
        else if (body.detail?.message) detail = body.detail.message;
      } catch {
        /* ignore */
      }
      throw new ApiError(detail, response.status);
    }
    return response.json() as Promise<AiVisionAnalyzeResponse>;
  },

  /** Unified deterministic Analyze + optional chart Vision (one persistence bundle). */
  aiAnalyzeWithVision: async (
    args: {
      exchange: ExchangeId;
      marketType: MarketType;
      symbol: string;
      timeframe?: string;
      accountBalance?: number;
      riskPercent?: number;
      analysisMode?: "LIVE_MARKET" | "UPLOADED_IMAGE";
      file?: File | null;
    },
    signal?: AbortSignal,
  ) => {
    const form = new FormData();
    form.append("exchange", args.exchange);
    form.append("market_type", args.marketType);
    form.append("symbol", args.symbol);
    form.append("analysis_mode", args.analysisMode ?? "LIVE_MARKET");
    if (args.timeframe) form.append("timeframe", args.timeframe);
    if (args.accountBalance != null) {
      form.append("account_balance", String(args.accountBalance));
    }
    if (args.riskPercent != null) {
      form.append("risk_percent", String(args.riskPercent));
    }
    if (args.file) form.append("file", args.file);
    const response = await fetch(`${API_URL}/api/v1/ai/analyze-with-vision`, {
      method: "POST",
      body: form,
      headers: await buildHeaders(undefined, { json: false }),
      signal,
      cache: "no-store",
    });
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = (await response.json()) as {
          detail?: string | { code?: string; message?: string };
        };
        detail = formatApiDetail(body.detail, response.statusText);
      } catch {
        /* ignore */
      }
      throw new ApiError(detail, response.status);
    }
    return response.json() as Promise<AiAnalyzeResponse>;
  },
  aiCompare: (
    args: { snapshot: AnalysisSnapshot; vision: VisionResult },
    signal?: AbortSignal,
  ) =>
    request<AiCompareResponse>("/api/v1/ai/compare", {
      method: "POST",
      body: JSON.stringify({
        snapshot: args.snapshot,
        vision: args.vision,
      }),
      signal,
    }),
  createReplaySession: (body: CreateReplaySessionRequest, signal?: AbortSignal) =>
    request<ReplaySessionResponse>("/api/v1/replay/sessions", {
      method: "POST",
      body: JSON.stringify(body),
      signal,
    }),
  getReplaySession: (sessionId: string, signal?: AbortSignal) =>
    request<ReplaySessionResponse>(`/api/v1/replay/sessions/${sessionId}`, { signal }),
  startReplay: (sessionId: string) =>
    request<ReplayControlResponse>(`/api/v1/replay/sessions/${sessionId}/start`, {
      method: "POST",
    }),
  pauseReplay: (sessionId: string) =>
    request<ReplayControlResponse>(`/api/v1/replay/sessions/${sessionId}/pause`, {
      method: "POST",
    }),
  resumeReplay: (sessionId: string) =>
    request<ReplayControlResponse>(`/api/v1/replay/sessions/${sessionId}/resume`, {
      method: "POST",
    }),
  stopReplay: (sessionId: string) =>
    request<ReplayControlResponse>(`/api/v1/replay/sessions/${sessionId}/stop`, {
      method: "POST",
    }),
  stepReplay: (sessionId: string) =>
    request<ReplayControlResponse>(`/api/v1/replay/sessions/${sessionId}/step`, {
      method: "POST",
    }),
  resetReplay: (sessionId: string) =>
    request<ReplayControlResponse>(`/api/v1/replay/sessions/${sessionId}/reset`, {
      method: "POST",
    }),
  setReplaySpeed: (sessionId: string, speed: ReplaySpeed) =>
    request<ReplayControlResponse>(`/api/v1/replay/sessions/${sessionId}/speed`, {
      method: "POST",
      body: JSON.stringify({ speed }),
    }),
  seekReplay: (
    sessionId: string,
    body: { event_index: number } | { timestamp: string },
  ) =>
    request<ReplayControlResponse>(`/api/v1/replay/sessions/${sessionId}/seek`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteReplaySession: (sessionId: string) =>
    request<{ session_id: string; deleted: boolean }>(
      `/api/v1/replay/sessions/${sessionId}`,
      { method: "DELETE" },
    ),
  enableReplayAnalysis: (sessionId: string) =>
    request<ReplayAnalysisToggleResponse>(
      `/api/v1/replay/sessions/${sessionId}/analysis/enable`,
      { method: "POST" },
    ),
  disableReplayAnalysis: (sessionId: string) =>
    request<ReplayAnalysisToggleResponse>(
      `/api/v1/replay/sessions/${sessionId}/analysis/disable`,
      { method: "POST" },
    ),
  getReplayAnalysis: (sessionId: string, signal?: AbortSignal) =>
    request<ReplayAnalysisCurrentResponse>(
      `/api/v1/replay/sessions/${sessionId}/analysis`,
      { signal },
    ),
  getReplayAnalysisHistory: (
    sessionId: string,
    args?: { offset?: number; limit?: number },
    signal?: AbortSignal,
  ) =>
    request<{
      session_id: string;
      count: number;
      offset: number;
      limit: number;
      total: number;
      snapshots: HistoricalAnalysisSnapshot[];
    }>(
      `/api/v1/replay/sessions/${sessionId}/analysis/history${qs({
        offset: args?.offset,
        limit: args?.limit,
      })}`,
      { signal },
    ),
  enableReplaySimulation: (sessionId: string) =>
    request<ReplaySimulationToggleResponse>(
      `/api/v1/replay/sessions/${sessionId}/simulation/enable`,
      { method: "POST" },
    ),
  disableReplaySimulation: (sessionId: string) =>
    request<ReplaySimulationToggleResponse>(
      `/api/v1/replay/sessions/${sessionId}/simulation/disable`,
      { method: "POST" },
    ),
  getReplaySimulation: (sessionId: string, signal?: AbortSignal) =>
    request<ReplaySimulationCurrentResponse>(
      `/api/v1/replay/sessions/${sessionId}/simulation`,
      { signal },
    ),
  getReplaySimulationTrades: (
    sessionId: string,
    args?: { offset?: number; limit?: number; status?: string },
    signal?: AbortSignal,
  ) =>
    request<{
      session_id: string;
      count: number;
      offset: number;
      limit: number;
      total: number;
      trades: SimulatedTrade[];
    }>(
      `/api/v1/replay/sessions/${sessionId}/simulation/trades${qs({
        offset: args?.offset,
        limit: args?.limit,
        status: args?.status,
      })}`,
      { signal },
    ),
  getReplaySimulationTrade: (sessionId: string, tradeId: string, signal?: AbortSignal) =>
    request<SimulatedTrade>(
      `/api/v1/replay/sessions/${sessionId}/simulation/trades/${tradeId}`,
      { signal },
    ),
  getReplaySimulationEvents: (
    sessionId: string,
    args?: { offset?: number; limit?: number },
    signal?: AbortSignal,
  ) =>
    request<{
      session_id: string;
      count: number;
      offset: number;
      limit: number;
      total: number;
      events: SimulationExecutionEvent[];
    }>(
      `/api/v1/replay/sessions/${sessionId}/simulation/events${qs({
        offset: args?.offset,
        limit: args?.limit,
      })}`,
      { signal },
    ),
  resetReplaySimulation: (sessionId: string) =>
    request<ReplaySimulationToggleResponse>(
      `/api/v1/replay/sessions/${sessionId}/simulation/reset`,
      { method: "POST" },
    ),
  enableReplayCosts: (sessionId: string) =>
    request<ReplayCostToggleResponse>(`/api/v1/replay/sessions/${sessionId}/costs/enable`, {
      method: "POST",
    }),
  disableReplayCosts: (sessionId: string) =>
    request<ReplayCostToggleResponse>(`/api/v1/replay/sessions/${sessionId}/costs/disable`, {
      method: "POST",
    }),
  getReplayCosts: (sessionId: string, signal?: AbortSignal) =>
    request<ReplayCostCurrentResponse>(`/api/v1/replay/sessions/${sessionId}/costs`, {
      signal,
    }),
  getReplayCostConfig: (sessionId: string, signal?: AbortSignal) =>
    request<{ session_id: string; costs_enabled: boolean; config: ExecutionCostConfigPublic }>(
      `/api/v1/replay/sessions/${sessionId}/costs/config`,
      { signal },
    ),
  updateReplayCostConfig: (sessionId: string, body: Partial<ExecutionCostConfigPublic>) =>
    request<ReplayCostToggleResponse>(`/api/v1/replay/sessions/${sessionId}/costs/config`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  getReplayCostLedger: (
    sessionId: string,
    args?: { offset?: number; limit?: number; trade_id?: string },
    signal?: AbortSignal,
  ) =>
    request<{
      session_id: string;
      count: number;
      offset: number;
      limit: number;
      total: number;
      entries: LedgerEntry[];
    }>(
      `/api/v1/replay/sessions/${sessionId}/costs/ledger${qs({
        offset: args?.offset,
        limit: args?.limit,
        trade_id: args?.trade_id,
      })}`,
      { signal },
    ),
  getReplayCostTrades: (sessionId: string, signal?: AbortSignal) =>
    request<{ session_id: string; count: number; trades: TradeCostSummary[] }>(
      `/api/v1/replay/sessions/${sessionId}/costs/trades`,
      { signal },
    ),
  resetReplayCosts: (sessionId: string) =>
    request<ReplayCostToggleResponse>(`/api/v1/replay/sessions/${sessionId}/costs/reset`, {
      method: "POST",
    }),

  enableReplayAnalytics: (sessionId: string) =>
    request<ReplayAnalyticsToggleResponse>(
      `/api/v1/replay/sessions/${sessionId}/analytics/enable`,
      { method: "POST" },
    ),
  disableReplayAnalytics: (sessionId: string) =>
    request<ReplayAnalyticsToggleResponse>(
      `/api/v1/replay/sessions/${sessionId}/analytics/disable`,
      { method: "POST" },
    ),
  getReplayAnalytics: (sessionId: string, signal?: AbortSignal) =>
    request<ReplayAnalyticsCurrentResponse>(
      `/api/v1/replay/sessions/${sessionId}/analytics`,
      { signal },
    ),
  getReplayAnalyticsConfig: (sessionId: string, signal?: AbortSignal) =>
    request<{ session_id: string; analytics_enabled: boolean; config: AnalyticsConfigPublic }>(
      `/api/v1/replay/sessions/${sessionId}/analytics/config`,
      { signal },
    ),
  updateReplayAnalyticsConfig: (
    sessionId: string,
    body: Partial<AnalyticsConfigPublic> & { clear_initial_equity?: boolean },
  ) =>
    request<ReplayAnalyticsToggleResponse>(
      `/api/v1/replay/sessions/${sessionId}/analytics/config`,
      { method: "PUT", body: JSON.stringify(body) },
    ),
  updateReplayAnalyticsFilter: (
    sessionId: string,
    body: {
      exchange?: string | null;
      symbol?: string | null;
      market_type?: string | null;
      direction?: string | null;
      exit_type?: string | null;
      start_time?: string | null;
      end_time?: string | null;
    },
  ) =>
    request<ReplayAnalyticsToggleResponse>(
      `/api/v1/replay/sessions/${sessionId}/analytics/filter`,
      { method: "PUT", body: JSON.stringify(body) },
    ),
  getReplayAnalyticsSnapshot: async (sessionId: string): Promise<AnalyticsSnapshot> => {
    const res = await request<ReplayAnalyticsCurrentResponse>(
      `/api/v1/replay/sessions/${sessionId}/analytics`,
    );
    return res.snapshot;
  },

  getReplayReport: (sessionId: string, signal?: AbortSignal) =>
    request<ReplayReportResponse>(`/api/v1/replay/sessions/${sessionId}/report`, {
      signal,
    }),

  downloadReplayReportCsv: async (sessionId: string, kind: ReportCsvKind) => {
    const response = await fetch(
      `${API_URL}/api/v1/replay/sessions/${sessionId}/report/export/csv?kind=${encodeURIComponent(kind)}`,
      {
        cache: "no-store",
        headers: await buildHeaders(undefined, { json: false }),
      },
    );
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = (await response.json()) as { detail?: string };
        if (body.detail) detail = body.detail;
      } catch {
        /* ignore */
      }
      throw new ApiError(detail, response.status);
    }
    const blob = await response.blob();
    const filename = filenameFromContentDisposition(
      response.headers.get("Content-Disposition"),
      `backtest_${kind}.csv`,
    );
    downloadBlob(blob, filename);
  },

  downloadReplayReportPdf: async (sessionId: string) => {
    const response = await fetch(
      `${API_URL}/api/v1/replay/sessions/${sessionId}/report/export/pdf`,
      {
        cache: "no-store",
        headers: await buildHeaders(undefined, { json: false }),
      },
    );
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = (await response.json()) as { detail?: string };
        if (body.detail) detail = body.detail;
      } catch {
        /* ignore */
      }
      throw new ApiError(detail, response.status);
    }
    const blob = await response.blob();
    const filename = filenameFromContentDisposition(
      response.headers.get("Content-Disposition"),
      "backtest_report.pdf",
    );
    downloadBlob(blob, filename);
  },

  historyAnalyses: (params: AnalysisHistoryListParams = {}, signal?: AbortSignal) =>
    request<AnalysisHistoryListResponse>(
      `/api/v1/history/analyses${qs({
        limit: params.limit,
        offset: params.offset,
        exchange: params.exchange,
        market_type: params.market_type,
        symbol: params.symbol,
        timeframe: params.timeframe,
        decision: params.decision,
        consistency_status: params.consistency_status,
        from: params.from,
        to: params.to,
      })}`,
      { signal },
    ),

  historyAnalysisByRun: (analysisRunId: string, signal?: AbortSignal) =>
    request<AnalysisHistoryDetail>(
      `/api/v1/history/analyses/by-run/${encodeURIComponent(analysisRunId)}`,
      { signal },
    ),

  opportunities: (
    params: {
      exchange?: ExchangeId;
      marketType?: MarketType;
      timeframe?: Timeframe;
      direction?: "LONG" | "SHORT";
      status?: OpportunityStatus;
      search?: string;
      actionableOnly?: boolean;
      sort?: "confluence" | "freshness" | "entry_distance" | "rank";
      limit?: number;
      offset?: number;
    } = {},
    signal?: AbortSignal,
  ) =>
    request<OpportunityListResponse>(
      `/api/v1/opportunities${qs({
        exchange: params.exchange,
        market_type: params.marketType,
        timeframe: params.timeframe,
        direction: params.direction,
        status: params.status,
        search: params.search,
        actionable_only: params.actionableOnly ? "true" : undefined,
        sort: params.sort,
        limit: params.limit,
        offset: params.offset,
      })}`,
      { signal },
    ),

  opportunitiesStatus: (signal?: AbortSignal) =>
    request<ScannerStatusResponse>(`/api/v1/opportunities/status`, { signal }),

  opportunitiesScan: (signal?: AbortSignal) =>
    request<ScanTriggerResponse>(`/api/v1/opportunities/scan`, {
      method: "POST",
      signal,
    }),
};
