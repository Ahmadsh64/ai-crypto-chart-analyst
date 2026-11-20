"use client";

import { create } from "zustand";
import type {
  CHoCHEvent,
  EqualExtremeCluster,
  ExchangeId,
  FairValueGap,
  IndicatorLatest,
  LiquidityLevel,
  LiquiditySnapshot,
  LiquiditySweep,
  MarketStructureSnapshot,
  MarketType,
  MSSEvent,
  ObFvgSnapshot,
  OrderBlock,
  MultiTimeframeSnapshot,
  MtfTimeframeSeries,
  ConfluenceEvidence,
  ConfluenceConflict,
  ConfluenceCategoryScore,
  ConfluenceDataQuality,
  PreliminaryAssessment,
  PlanDirection,
  PlanStatus,
  TradePlanEntry,
  TradePlanStopLoss,
  TradePlanTarget,
  TradePlanRisk,
  TradePlanSizing,
  TradePlanValidation,
  TradePlanEligibility,
  TradePlanDataQuality,
  FinalDecision,
  SetupLifecycle,
  DecisionConfluenceScores,
  DecisionEntryConfirmation,
  DecisionDataQuality,
  StructureBreakEvent,
  SwingPoint,
  Timeframe,
} from "@/types/api";
import type { MarketWsMessage, WsConnectionStatus } from "@/services/market-websocket";

export interface LiveTicker {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  last: number;
  changePct24h?: number | null;
  volume24h?: number | null;
  high24h?: number | null;
  low24h?: number | null;
  exchangeTs?: string | null;
  processedAt: string;
  direction: "up" | "down" | "flat";
  source: "websocket" | "rest-fallback";
}

export interface LiveCandle {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  timeframe: Timeframe;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  isClosed: boolean;
  exchangeTs?: string | null;
  processedAt: string;
}

export interface LiveIndicators {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  timeframe: Timeframe;
  includeForming: boolean;
  closedCandlesUsed: number;
  indicators: Record<string, IndicatorLatest>;
  processedAt: string;
  exchangeTs?: string | null;
}

export interface LiveStructure {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  timeframe: Timeframe;
  snapshot: MarketStructureSnapshot;
  swings: SwingPoint[];
  bosEvents: StructureBreakEvent[];
  chochEvents: CHoCHEvent[];
  mssEvents: MSSEvent[];
  processedAt: string;
}

export interface LiveLiquidity {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  timeframe: Timeframe;
  snapshot: LiquiditySnapshot;
  eqhClusters: EqualExtremeCluster[];
  eqlClusters: EqualExtremeCluster[];
  bslLevels: LiquidityLevel[];
  sslLevels: LiquidityLevel[];
  sweeps: LiquiditySweep[];
  processedAt: string;
}

export interface LiveObFvg {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  timeframe: Timeframe;
  snapshot: ObFvgSnapshot;
  bullishOrderBlocks: OrderBlock[];
  bearishOrderBlocks: OrderBlock[];
  bullishFvgs: FairValueGap[];
  bearishFvgs: FairValueGap[];
  processedAt: string;
}

export interface LiveMultiTimeframe {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  snapshot: MultiTimeframeSnapshot;
  timeframes: MtfTimeframeSeries[];
  processedAt: string;
}

export interface LiveConfluence {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  bullishScore: number;
  bearishScore: number;
  categoryScores: ConfluenceCategoryScore[];
  evidence: ConfluenceEvidence[];
  conflicts: ConfluenceConflict[];
  preliminaryAssessment: PreliminaryAssessment;
  assessmentStrength: "strong" | "moderate" | "none";
  dataQuality: ConfluenceDataQuality;
  summary: string;
  configurationVersion: string;
  analysisTimestamp: string;
  processedAt: string;
}

export interface LiveTradePlan {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  planId: string;
  direction?: PlanDirection | null;
  planStatus: PlanStatus;
  entry?: TradePlanEntry | null;
  stopLoss?: TradePlanStopLoss | null;
  takeProfitTargets: TradePlanTarget[];
  risk?: TradePlanRisk | null;
  positionSizing?: TradePlanSizing | null;
  validation: TradePlanValidation;
  eligibility: TradePlanEligibility;
  invalidationConditions: string[];
  explanations: string[];
  configurationVersion: string;
  analysisTimestamp: string;
  dataQuality: TradePlanDataQuality;
  confluenceAssessment?: string | null;
  spotShortWarning?: string | null;
  analysisOnlyDisclaimer: string;
  bullishScore?: number | null;
  bearishScore?: number | null;
  processedAt: string;
}

export interface LiveDecision {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  decisionId: string;
  decision: FinalDecision;
  decisionReason: string;
  direction?: PlanDirection | null;
  lifecycle: SetupLifecycle;
  confluenceScores: DecisionConfluenceScores;
  tradePlanStatus?: string | null;
  entryConfirmation: DecisionEntryConfirmation;
  entryZoneSummary?: Record<string, unknown> | null;
  stopLossPrice?: number | null;
  takeProfitPrices: number[];
  primaryRr?: number | null;
  riskAmount?: number | null;
  positionSize?: number | null;
  priceInsideEntryZone?: boolean | null;
  supportingEvidence: string[];
  blockingConditions: string[];
  conflictIds: string[];
  dataQuality: DecisionDataQuality;
  spotRestriction?: string | null;
  analysisOnlyDisclaimer: string;
  configurationVersion: string;
  analysisTimestamp: string;
  expiresAt?: string | null;
  processedAt: string;
}

interface LiveMarketState {
  connectionStatus: WsConnectionStatus;
  lastMessageAt: number | null;
  tickers: Record<string, LiveTicker>;
  candles: Record<string, LiveCandle>;
  indicators: Record<string, LiveIndicators>;
  structure: Record<string, LiveStructure>;
  liquidity: Record<string, LiveLiquidity>;
  obFvg: Record<string, LiveObFvg>;
  multiTimeframe: Record<string, LiveMultiTimeframe>;
  confluence: Record<string, LiveConfluence>;
  tradePlan: Record<string, LiveTradePlan>;
  decision: Record<string, LiveDecision>;
  setConnectionStatus: (status: WsConnectionStatus) => void;
  setLastMessageAt: (ts: number | null) => void;
  applyMessage: (message: MarketWsMessage) => void;
}

export function tickerKey(exchange: ExchangeId, marketType: MarketType, symbol: string) {
  return `${exchange}:${marketType}:${symbol.toUpperCase()}`;
}

export function mtfKey(exchange: ExchangeId, marketType: MarketType, symbol: string) {
  return tickerKey(exchange, marketType, symbol);
}

export function confluenceKey(exchange: ExchangeId, marketType: MarketType, symbol: string) {
  return tickerKey(exchange, marketType, symbol);
}

export function tradePlanKey(exchange: ExchangeId, marketType: MarketType, symbol: string) {
  return tickerKey(exchange, marketType, symbol);
}

export function decisionKey(exchange: ExchangeId, marketType: MarketType, symbol: string) {
  return tickerKey(exchange, marketType, symbol);
}

export function candleKey(
  exchange: ExchangeId,
  marketType: MarketType,
  symbol: string,
  timeframe: Timeframe,
) {
  return `${exchange}:${marketType}:${symbol.toUpperCase()}:${timeframe}`;
}

export function indicatorKey(
  exchange: ExchangeId,
  marketType: MarketType,
  symbol: string,
  timeframe: Timeframe,
) {
  return candleKey(exchange, marketType, symbol, timeframe);
}

export const useLiveMarketStore = create<LiveMarketState>((set, get) => ({
  connectionStatus: "disconnected",
  lastMessageAt: null,
  tickers: {},
  candles: {},
  indicators: {},
  structure: {},
  liquidity: {},
  obFvg: {},
  multiTimeframe: {},
  confluence: {},
  tradePlan: {},
  decision: {},
  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),
  setLastMessageAt: (lastMessageAt) => set({ lastMessageAt }),
  applyMessage: (message) => {
    if (message.type === "ticker_update" && message.exchange && message.symbol && message.market_type) {
      const data = (message.data ?? {}) as Record<string, unknown>;
      const last = Number(data.last);
      if (!Number.isFinite(last)) return;
      const key = tickerKey(message.exchange, message.market_type, message.symbol);
      const prev = get().tickers[key];
      const direction =
        prev == null ? "flat" : last > prev.last ? "up" : last < prev.last ? "down" : "flat";
      set((state) => ({
        tickers: {
          ...state.tickers,
          [key]: {
            exchange: message.exchange!,
            marketType: message.market_type!,
            symbol: message.symbol!.toUpperCase(),
            last,
            changePct24h:
              data.change_pct_24h == null ? prev?.changePct24h : Number(data.change_pct_24h),
            volume24h: data.volume_24h == null ? prev?.volume24h : Number(data.volume_24h),
            high24h: data.high_24h == null ? prev?.high24h : Number(data.high_24h),
            low24h: data.low_24h == null ? prev?.low24h : Number(data.low_24h),
            exchangeTs: message.exchange_ts,
            processedAt: message.processed_at,
            direction,
            source: "websocket",
          },
        },
        lastMessageAt: Date.now(),
      }));
      return;
    }

    if (message.type === "candle_update" && message.exchange && message.symbol && message.market_type) {
      const data = (message.data ?? {}) as Record<string, unknown>;
      const timeframe = (message.timeframe ?? data.timeframe) as Timeframe | undefined;
      if (!timeframe) return;
      const key = candleKey(message.exchange, message.market_type, message.symbol, timeframe);
      set((state) => ({
        candles: {
          ...state.candles,
          [key]: {
            exchange: message.exchange!,
            marketType: message.market_type!,
            symbol: message.symbol!.toUpperCase(),
            timeframe,
            timestamp: String(data.timestamp),
            open: Number(data.open),
            high: Number(data.high),
            low: Number(data.low),
            close: Number(data.close),
            volume: Number(data.volume),
            isClosed: Boolean(data.is_closed),
            exchangeTs: message.exchange_ts,
            processedAt: message.processed_at,
          },
        },
        lastMessageAt: Date.now(),
      }));
      return;
    }

    if (
      message.type === "indicator_update" &&
      message.exchange &&
      message.symbol &&
      message.market_type &&
      message.timeframe
    ) {
      const data = (message.data ?? {}) as Record<string, unknown>;
      const raw = (data.indicators ?? {}) as Record<string, IndicatorLatest>;
      const key = indicatorKey(
        message.exchange,
        message.market_type,
        message.symbol,
        message.timeframe,
      );
      set((state) => ({
        indicators: {
          ...state.indicators,
          [key]: {
            exchange: message.exchange!,
            marketType: message.market_type!,
            symbol: message.symbol!.toUpperCase(),
            timeframe: message.timeframe!,
            includeForming: Boolean(data.include_forming),
            closedCandlesUsed: Number(data.closed_candles_used ?? 0),
            indicators: raw,
            processedAt: message.processed_at,
            exchangeTs: message.exchange_ts,
          },
        },
        lastMessageAt: Date.now(),
      }));
      return;
    }

    if (
      message.type === "structure_update" &&
      message.exchange &&
      message.symbol &&
      message.market_type &&
      message.timeframe
    ) {
      const data = (message.data ?? {}) as Record<string, unknown>;
      const key = indicatorKey(
        message.exchange,
        message.market_type,
        message.symbol,
        message.timeframe,
      );
      set((state) => ({
        structure: {
          ...state.structure,
          [key]: {
            exchange: message.exchange!,
            marketType: message.market_type!,
            symbol: message.symbol!.toUpperCase(),
            timeframe: message.timeframe!,
            snapshot: data.snapshot as MarketStructureSnapshot,
            swings: (data.swings as SwingPoint[]) ?? [],
            bosEvents: (data.bos_events as StructureBreakEvent[]) ?? [],
            chochEvents: (data.choch_events as CHoCHEvent[]) ?? [],
            mssEvents: (data.mss_events as MSSEvent[]) ?? [],
            processedAt: message.processed_at,
          },
        },
        lastMessageAt: Date.now(),
      }));
    }

    if (
      message.type === "liquidity_update" &&
      message.exchange &&
      message.symbol &&
      message.market_type &&
      message.timeframe
    ) {
      const data = (message.data ?? {}) as Record<string, unknown>;
      const key = indicatorKey(
        message.exchange,
        message.market_type,
        message.symbol,
        message.timeframe,
      );
      set((state) => ({
        liquidity: {
          ...state.liquidity,
          [key]: {
            exchange: message.exchange!,
            marketType: message.market_type!,
            symbol: message.symbol!.toUpperCase(),
            timeframe: message.timeframe!,
            snapshot: data.snapshot as LiquiditySnapshot,
            eqhClusters: (data.eqh_clusters as EqualExtremeCluster[]) ?? [],
            eqlClusters: (data.eql_clusters as EqualExtremeCluster[]) ?? [],
            bslLevels: (data.bsl_levels as LiquidityLevel[]) ?? [],
            sslLevels: (data.ssl_levels as LiquidityLevel[]) ?? [],
            sweeps: (data.sweeps as LiquiditySweep[]) ?? [],
            processedAt: message.processed_at,
          },
        },
        lastMessageAt: Date.now(),
      }));
    }

    if (
      message.type === "ob_fvg_update" &&
      message.exchange &&
      message.symbol &&
      message.market_type &&
      message.timeframe
    ) {
      const data = (message.data ?? {}) as Record<string, unknown>;
      const key = indicatorKey(
        message.exchange,
        message.market_type,
        message.symbol,
        message.timeframe,
      );
      set((state) => ({
        obFvg: {
          ...state.obFvg,
          [key]: {
            exchange: message.exchange!,
            marketType: message.market_type!,
            symbol: message.symbol!.toUpperCase(),
            timeframe: message.timeframe!,
            snapshot: data.snapshot as ObFvgSnapshot,
            bullishOrderBlocks: (data.bullish_order_blocks as OrderBlock[]) ?? [],
            bearishOrderBlocks: (data.bearish_order_blocks as OrderBlock[]) ?? [],
            bullishFvgs: (data.bullish_fvgs as FairValueGap[]) ?? [],
            bearishFvgs: (data.bearish_fvgs as FairValueGap[]) ?? [],
            processedAt: message.processed_at,
          },
        },
        lastMessageAt: Date.now(),
      }));
    }

    if (
      message.type === "multi_timeframe_update" &&
      message.exchange &&
      message.symbol &&
      message.market_type
    ) {
      const data = (message.data ?? {}) as Record<string, unknown>;
      const key = mtfKey(message.exchange, message.market_type, message.symbol);
      const snapshot = data.snapshot as MultiTimeframeSnapshot;
      set((state) => ({
        multiTimeframe: {
          ...state.multiTimeframe,
          [key]: {
            exchange: message.exchange!,
            marketType: message.market_type!,
            symbol: message.symbol!.toUpperCase(),
            snapshot,
            timeframes:
              (data.timeframes as MtfTimeframeSeries[]) ?? snapshot?.timeframes ?? [],
            processedAt: message.processed_at,
          },
        },
        lastMessageAt: Date.now(),
      }));
    }

    if (
      message.type === "confluence_update" &&
      message.exchange &&
      message.symbol &&
      message.market_type
    ) {
      const data = (message.data ?? {}) as Record<string, unknown>;
      const key = confluenceKey(message.exchange, message.market_type, message.symbol);
      set((state) => ({
        confluence: {
          ...state.confluence,
          [key]: {
            exchange: message.exchange!,
            marketType: message.market_type!,
            symbol: message.symbol!.toUpperCase(),
            bullishScore: Number(data.bullish_score ?? 0),
            bearishScore: Number(data.bearish_score ?? 0),
            categoryScores: (data.category_scores as ConfluenceCategoryScore[]) ?? [],
            evidence: (data.evidence as ConfluenceEvidence[]) ?? [],
            conflicts: (data.conflicts as ConfluenceConflict[]) ?? [],
            preliminaryAssessment: data.preliminary_assessment as PreliminaryAssessment,
            assessmentStrength: (data.assessment_strength as "strong" | "moderate" | "none") ?? "none",
            dataQuality: data.data_quality as ConfluenceDataQuality,
            summary: String(data.summary ?? ""),
            configurationVersion: String(data.configuration_version ?? ""),
            analysisTimestamp: String(data.analysis_timestamp ?? message.processed_at),
            processedAt: message.processed_at,
          },
        },
        lastMessageAt: Date.now(),
      }));
    }

    if (
      message.type === "trade_plan_update" &&
      message.exchange &&
      message.symbol &&
      message.market_type
    ) {
      const data = (message.data ?? {}) as Record<string, unknown>;
      const key = tradePlanKey(message.exchange, message.market_type, message.symbol);
      set((state) => ({
        tradePlan: {
          ...state.tradePlan,
          [key]: {
            exchange: message.exchange!,
            marketType: message.market_type!,
            symbol: message.symbol!.toUpperCase(),
            planId: String(data.plan_id ?? ""),
            direction: (data.direction as PlanDirection | null) ?? null,
            planStatus: (data.plan_status as PlanStatus) ?? "blocked",
            entry: (data.entry as TradePlanEntry | null) ?? null,
            stopLoss: (data.stop_loss as TradePlanStopLoss | null) ?? null,
            takeProfitTargets: (data.take_profit_targets as TradePlanTarget[]) ?? [],
            risk: (data.risk as TradePlanRisk | null) ?? null,
            positionSizing: (data.position_sizing as TradePlanSizing | null) ?? null,
            validation: (data.validation as TradePlanValidation) ?? {
              is_valid: false,
              validation_errors: [],
              warnings: [],
              blocking_reasons: [],
            },
            eligibility: (data.eligibility as TradePlanEligibility) ?? {
              is_eligible: false,
              blocking_reasons: [],
            },
            invalidationConditions: (data.invalidation_conditions as string[]) ?? [],
            explanations: (data.explanations as string[]) ?? [],
            configurationVersion: String(data.configuration_version ?? ""),
            analysisTimestamp: String(data.analysis_timestamp ?? message.processed_at),
            dataQuality: data.data_quality as TradePlanDataQuality,
            confluenceAssessment: (data.confluence_assessment as string | null) ?? null,
            spotShortWarning: (data.spot_short_warning as string | null) ?? null,
            analysisOnlyDisclaimer: String(
              data.analysis_only_disclaimer ??
                "Analysis only — no orders are executed. Prices are analytical levels, not guaranteed fills.",
            ),
            bullishScore:
              data.bullish_score == null ? null : Number(data.bullish_score),
            bearishScore:
              data.bearish_score == null ? null : Number(data.bearish_score),
            processedAt: message.processed_at,
          },
        },
        lastMessageAt: Date.now(),
      }));
    }

    if (
      message.type === "decision_update" &&
      message.exchange &&
      message.symbol &&
      message.market_type
    ) {
      const data = (message.data ?? {}) as Record<string, unknown>;
      const key = decisionKey(message.exchange, message.market_type, message.symbol);
      set((state) => ({
        decision: {
          ...state.decision,
          [key]: {
            exchange: message.exchange!,
            marketType: message.market_type!,
            symbol: message.symbol!.toUpperCase(),
            decisionId: String(data.decision_id ?? ""),
            decision: (data.decision as FinalDecision) ?? "NO TRADE",
            decisionReason: String(data.decision_reason ?? ""),
            direction: (data.direction as PlanDirection | null) ?? null,
            lifecycle: (data.lifecycle as SetupLifecycle) ?? "invalidated",
            confluenceScores: (data.confluence_scores as DecisionConfluenceScores) ?? {
              bullish_score: 0,
              bearish_score: 0,
            },
            tradePlanStatus: (data.trade_plan_status as string | null) ?? null,
            entryConfirmation: (data.entry_confirmation as DecisionEntryConfirmation) ?? {
              status: "unavailable",
              is_confirmed: false,
              explanation: "",
            },
            entryZoneSummary: (data.entry_zone_summary as Record<string, unknown> | null) ?? null,
            stopLossPrice:
              data.stop_loss_price == null ? null : Number(data.stop_loss_price),
            takeProfitPrices: (data.take_profit_prices as number[]) ?? [],
            primaryRr: data.primary_rr == null ? null : Number(data.primary_rr),
            riskAmount: data.risk_amount == null ? null : Number(data.risk_amount),
            positionSize: data.position_size == null ? null : Number(data.position_size),
            priceInsideEntryZone:
              data.price_inside_entry_zone == null
                ? null
                : Boolean(data.price_inside_entry_zone),
            supportingEvidence: (data.supporting_evidence as string[]) ?? [],
            blockingConditions: (data.blocking_conditions as string[]) ?? [],
            conflictIds: (data.conflict_ids as string[]) ?? [],
            dataQuality: data.data_quality as DecisionDataQuality,
            spotRestriction: (data.spot_restriction as string | null) ?? null,
            analysisOnlyDisclaimer: String(
              data.analysis_only_disclaimer ??
                "Analysis only — no orders are executed. Analytical conditions do not guarantee execution or profit.",
            ),
            configurationVersion: String(data.configuration_version ?? ""),
            analysisTimestamp: String(data.analysis_timestamp ?? message.processed_at),
            expiresAt: (data.expires_at as string | null) ?? null,
            processedAt: message.processed_at,
          },
        },
        lastMessageAt: Date.now(),
      }));
    }
  },
}));
