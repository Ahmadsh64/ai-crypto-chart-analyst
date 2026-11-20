"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/services/api";
import type { ExchangeId, MarketType, Timeframe } from "@/types/api";

/**
 * Market data hooks.
 * - Query keys always include exchange + marketType + symbol + timeframe.
 * - No keepPreviousData / placeholderData: changing selection clears old series
 *   so stale candles never render as the new market.
 * - AbortSignal cancels in-flight fetches when the selection changes.
 */

export function useExchanges() {
  return useQuery({
    queryKey: ["exchanges"],
    queryFn: ({ signal }) => api.exchanges(signal),
    staleTime: 60_000,
  });
}

export function useMarkets(exchange: ExchangeId, marketType: MarketType, search?: string) {
  return useQuery({
    queryKey: ["markets", exchange, marketType, search ?? ""],
    queryFn: ({ signal }) => api.markets(exchange, marketType, search, signal),
    staleTime: 60_000,
  });
}

export function useCandles(args: {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  timeframe: Timeframe;
  limit?: number;
  enabled?: boolean;
  /** Set false when WebSocket owns live updates (Phase 2.5). */
  refetchInterval?: number | false;
}) {
  const { enabled = true, refetchInterval = false, ...params } = args;
  return useQuery({
    queryKey: [
      "candles",
      params.exchange,
      params.marketType,
      params.symbol,
      params.timeframe,
      params.limit ?? 300,
    ],
    queryFn: ({ signal }) => api.candles(params, signal),
    enabled: enabled && Boolean(params.symbol),
    refetchInterval,
    placeholderData: undefined,
  });
}

export function useTicker(args: {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  enabled?: boolean;
  /** Prefer WebSocket live tickers; REST is seed/fallback only. */
  refetchInterval?: number | false;
}) {
  const { enabled = true, refetchInterval = false, ...params } = args;
  return useQuery({
    queryKey: ["ticker", params.exchange, params.marketType, params.symbol],
    queryFn: ({ signal }) => api.ticker(params, signal),
    enabled: enabled && Boolean(params.symbol),
    refetchInterval,
    placeholderData: undefined,
  });
}

export function useMarketStructure(args: {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  timeframe: Timeframe;
  limit?: number;
  includeUnconfirmed?: boolean;
  enabled?: boolean;
}) {
  const { enabled = true, ...params } = args;
  return useQuery({
    queryKey: [
      "market-structure",
      params.exchange,
      params.marketType,
      params.symbol,
      params.timeframe,
      params.limit ?? 500,
      params.includeUnconfirmed ?? false,
    ],
    queryFn: ({ signal }) => api.marketStructure(params, signal),
    enabled: enabled && Boolean(params.symbol),
    placeholderData: undefined,
    staleTime: 15_000,
  });
}

export function useLiquidity(args: {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  timeframe: Timeframe;
  limit?: number;
  includeUnconfirmed?: boolean;
  enabled?: boolean;
}) {
  const { enabled = true, ...params } = args;
  return useQuery({
    queryKey: [
      "liquidity",
      params.exchange,
      params.marketType,
      params.symbol,
      params.timeframe,
      params.limit ?? 500,
      params.includeUnconfirmed ?? false,
    ],
    queryFn: ({ signal }) => api.liquidity(params, signal),
    enabled: enabled && Boolean(params.symbol),
    placeholderData: undefined,
    staleTime: 15_000,
  });
}

export function useObFvg(args: {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  timeframe: Timeframe;
  limit?: number;
  includeUnconfirmed?: boolean;
  enabled?: boolean;
}) {
  const { enabled = true, ...params } = args;
  return useQuery({
    queryKey: [
      "ob-fvg",
      params.exchange,
      params.marketType,
      params.symbol,
      params.timeframe,
      params.limit ?? 500,
      params.includeUnconfirmed ?? false,
    ],
    queryFn: ({ signal }) => api.obFvg(params, signal),
    enabled: enabled && Boolean(params.symbol),
    placeholderData: undefined,
    staleTime: 15_000,
  });
}

export function useMultiTimeframe(args: {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  enabled?: boolean;
}) {
  const { enabled = true, ...params } = args;
  return useQuery({
    queryKey: ["multi-timeframe", params.exchange, params.marketType, params.symbol],
    queryFn: ({ signal }) => api.multiTimeframe(params, signal),
    enabled: enabled && Boolean(params.symbol),
    placeholderData: undefined,
    staleTime: 15_000,
  });
}

export function useConfluence(args: {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  enabled?: boolean;
}) {
  const { enabled = true, ...params } = args;
  return useQuery({
    queryKey: ["confluence", params.exchange, params.marketType, params.symbol],
    queryFn: ({ signal }) => api.confluence(params, signal),
    enabled: enabled && Boolean(params.symbol),
    placeholderData: undefined,
    staleTime: 20_000,
  });
}

export function useTradePlan(args: {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  accountBalance?: number;
  riskPercent?: number;
  enabled?: boolean;
}) {
  const { enabled = true, ...params } = args;
  return useQuery({
    queryKey: [
      "trade-plan",
      params.exchange,
      params.marketType,
      params.symbol,
      params.accountBalance ?? null,
      params.riskPercent ?? null,
    ],
    queryFn: ({ signal }) => api.tradePlan(params, signal),
    enabled: enabled && Boolean(params.symbol),
    placeholderData: undefined,
    staleTime: 20_000,
  });
}

export function useDecision(args: {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  accountBalance?: number;
  riskPercent?: number;
  enabled?: boolean;
}) {
  const { enabled = true, ...params } = args;
  return useQuery({
    queryKey: [
      "decision",
      params.exchange,
      params.marketType,
      params.symbol,
      params.accountBalance ?? null,
      params.riskPercent ?? null,
    ],
    queryFn: ({ signal }) => api.decision(params, signal),
    enabled: enabled && Boolean(params.symbol),
    placeholderData: undefined,
    staleTime: 20_000,
  });
}

export function useIndicators(args: {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  timeframe: Timeframe;
  indicators?: string;
  includeForming?: boolean;
  includeSeries?: boolean;
  limit?: number;
  enabled?: boolean;
}) {
  const { enabled = true, ...params } = args;
  return useQuery({
    queryKey: [
      "indicators",
      params.exchange,
      params.marketType,
      params.symbol,
      params.timeframe,
      params.indicators ?? "all",
      params.includeForming ?? false,
      params.includeSeries ?? false,
      params.limit ?? 500,
    ],
    queryFn: ({ signal }) => api.indicators(params, signal),
    enabled: enabled && Boolean(params.symbol),
    placeholderData: undefined,
    staleTime: 15_000,
  });
}
