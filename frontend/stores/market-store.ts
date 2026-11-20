"use client";

import { create } from "zustand";
import type { ExchangeId, MarketType, Timeframe } from "@/types/api";

interface MarketState {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  timeframe: Timeframe;
  searchQuery: string;
  setExchange: (exchange: ExchangeId) => void;
  setMarketType: (marketType: MarketType) => void;
  setSymbol: (symbol: string) => void;
  setTimeframe: (timeframe: Timeframe) => void;
  setSearchQuery: (query: string) => void;
}

export const useMarketStore = create<MarketState>((set) => ({
  exchange: "binance",
  marketType: "spot",
  symbol: "BTC/USDT",
  timeframe: "1h",
  searchQuery: "",
  setExchange: (exchange) =>
    set((state) => {
      const compatible =
        exchange === "binance"
          ? state.marketType === "spot" || state.marketType === "usdt_m_futures"
          : state.marketType === "spot" || state.marketType === "linear_perpetual";
      return {
        exchange,
        marketType: compatible ? state.marketType : "spot",
      };
    }),
  setMarketType: (marketType) => set({ marketType }),
  setSymbol: (symbol) => set({ symbol }),
  setTimeframe: (timeframe) => set({ timeframe }),
  setSearchQuery: (searchQuery) => set({ searchQuery }),
}));
