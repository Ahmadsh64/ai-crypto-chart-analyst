"use client";

import { useEffect } from "react";
import { marketWebsocket, type SubscribeRequest } from "@/services/market-websocket";
import { useLiveMarketStore } from "@/stores/live-market-store";
import type { ExchangeId, MarketType, Timeframe } from "@/types/api";

/** Ensure the shared market websocket is connected and store stays in sync. */
export function useMarketSocketBridge() {
  const applyMessage = useLiveMarketStore((s) => s.applyMessage);
  const setConnectionStatus = useLiveMarketStore((s) => s.setConnectionStatus);
  const setLastMessageAt = useLiveMarketStore((s) => s.setLastMessageAt);

  useEffect(() => {
    marketWebsocket.connect();
    const offMsg = marketWebsocket.onMessage((message) => {
      applyMessage(message);
      setLastMessageAt(Date.now());
    });
    const offStatus = marketWebsocket.onStatus(setConnectionStatus);
    return () => {
      offMsg();
      offStatus();
    };
  }, [applyMessage, setConnectionStatus, setLastMessageAt]);
}

export function useLiveSubscription(req: SubscribeRequest | null) {
  useMarketSocketBridge();

  useEffect(() => {
    if (!req) return;
    return marketWebsocket.subscribe(req);
  }, [
    req?.exchange,
    req?.marketType,
    req?.symbol,
    req?.timeframe,
    req?.tickerOnly,
  ]);
}

export function useLiveTickerSubscription(
  exchange: ExchangeId,
  marketType: MarketType,
  symbols: string[],
) {
  useMarketSocketBridge();

  useEffect(() => {
    const unsubs = symbols.map((symbol) =>
      marketWebsocket.subscribe({
        exchange,
        marketType,
        symbol,
        tickerOnly: true,
      }),
    );
    return () => {
      unsubs.forEach((unsub) => unsub());
    };
  }, [exchange, marketType, symbols.join("|")]);
}

export function useLiveChartSubscription(
  exchange: ExchangeId,
  marketType: MarketType,
  symbol: string,
  timeframe: Timeframe,
) {
  useLiveSubscription({
    exchange,
    marketType,
    symbol,
    timeframe,
    tickerOnly: false,
  });
}

export function useLiveIndicatorSubscription(
  exchange: ExchangeId,
  marketType: MarketType,
  symbol: string,
  timeframe: Timeframe,
  indicators?: string[],
  enabled = true,
) {
  useMarketSocketBridge();

  useEffect(() => {
    if (!enabled || !symbol) return;
    return marketWebsocket.subscribeIndicators({
      exchange,
      marketType,
      symbol,
      timeframe,
      indicators,
    });
  }, [enabled, exchange, marketType, symbol, timeframe, indicators?.join(",")]);
}

export function useLiveStructureSubscription(
  exchange: ExchangeId,
  marketType: MarketType,
  symbol: string,
  timeframe: Timeframe,
  enabled = true,
) {
  useMarketSocketBridge();

  useEffect(() => {
    if (!enabled || !symbol) return;
    return marketWebsocket.subscribeStructure({
      exchange,
      marketType,
      symbol,
      timeframe,
    });
  }, [enabled, exchange, marketType, symbol, timeframe]);
}

export function useLiveLiquiditySubscription(
  exchange: ExchangeId,
  marketType: MarketType,
  symbol: string,
  timeframe: Timeframe,
  enabled = true,
) {
  useMarketSocketBridge();

  useEffect(() => {
    if (!enabled || !symbol) return;
    return marketWebsocket.subscribeLiquidity({
      exchange,
      marketType,
      symbol,
      timeframe,
    });
  }, [enabled, exchange, marketType, symbol, timeframe]);
}

export function useLiveObFvgSubscription(
  exchange: ExchangeId,
  marketType: MarketType,
  symbol: string,
  timeframe: Timeframe,
  enabled = true,
) {
  useMarketSocketBridge();

  useEffect(() => {
    if (!enabled || !symbol) return;
    return marketWebsocket.subscribeObFvg({
      exchange,
      marketType,
      symbol,
      timeframe,
    });
  }, [enabled, exchange, marketType, symbol, timeframe]);
}

export function useLiveMultiTimeframeSubscription(
  exchange: ExchangeId,
  marketType: MarketType,
  symbol: string,
  enabled = true,
) {
  useMarketSocketBridge();

  useEffect(() => {
    if (!enabled || !symbol) return;
    return marketWebsocket.subscribeMultiTimeframe({
      exchange,
      marketType,
      symbol,
    });
  }, [enabled, exchange, marketType, symbol]);
}

export function useLiveConfluenceSubscription(
  exchange: ExchangeId,
  marketType: MarketType,
  symbol: string,
  enabled = true,
) {
  useMarketSocketBridge();

  useEffect(() => {
    if (!enabled || !symbol) return;
    return marketWebsocket.subscribeConfluence({
      exchange,
      marketType,
      symbol,
    });
  }, [enabled, exchange, marketType, symbol]);
}

export function useLiveTradePlanSubscription(
  exchange: ExchangeId,
  marketType: MarketType,
  symbol: string,
  enabled = true,
  accountBalance?: number,
  riskPercent?: number,
) {
  useMarketSocketBridge();

  useEffect(() => {
    if (!enabled || !symbol) return;
    return marketWebsocket.subscribeTradePlan({
      exchange,
      marketType,
      symbol,
      accountBalance,
      riskPercent,
    });
  }, [enabled, exchange, marketType, symbol, accountBalance, riskPercent]);
}

export function useLiveDecisionSubscription(
  exchange: ExchangeId,
  marketType: MarketType,
  symbol: string,
  enabled = true,
  accountBalance?: number,
  riskPercent?: number,
) {
  useMarketSocketBridge();

  useEffect(() => {
    if (!enabled || !symbol) return;
    return marketWebsocket.subscribeDecision({
      exchange,
      marketType,
      symbol,
      accountBalance,
      riskPercent,
    });
  }, [enabled, exchange, marketType, symbol, accountBalance, riskPercent]);
}
