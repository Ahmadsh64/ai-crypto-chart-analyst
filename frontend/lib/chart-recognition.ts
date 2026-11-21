/**
 * Screenshot recognition helpers (Phase 5.4.2.2).
 * OCR/visual estimates only — never invent verified market data.
 */

import type { ExchangeId, MarketType, Timeframe, VisionResult } from "@/types/api";

export const RECOGNITION_CONFIRM_THRESHOLD = 0.7;

export const SUPPORTED_TIMEFRAMES: Timeframe[] = [
  "1m",
  "5m",
  "15m",
  "30m",
  "1h",
  "4h",
  "1d",
];

export type RecognitionDraft = {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
  timeframe: Timeframe;
  symbolConfirmed: boolean;
  timeframeConfirmed: boolean;
};

export function normalizeDetectedSymbol(raw: string | null | undefined): string {
  if (!raw) return "";
  let s = raw.trim().toUpperCase().replace(/-/g, "/").replace(/\s+/g, "");
  if (!s.includes("/") && s.endsWith("USDT") && s.length > 4) {
    s = `${s.slice(0, -4)}/USDT`;
  }
  return s;
}

export function normalizeDetectedTimeframe(
  raw: string | null | undefined,
): Timeframe | null {
  if (!raw) return null;
  const t = raw.trim().toLowerCase().replace(/\s+/g, "");
  const aliases: Record<string, Timeframe> = {
    "1": "1m",
    "1min": "1m",
    "1m": "1m",
    "5": "5m",
    "5min": "5m",
    "5m": "5m",
    "15": "15m",
    "15min": "15m",
    "15m": "15m",
    "30": "30m",
    "30min": "30m",
    "30m": "30m",
    "60": "1h",
    "1h": "1h",
    "60m": "1h",
    "4h": "4h",
    "240": "4h",
    "1d": "1d",
    d: "1d",
    day: "1d",
    daily: "1d",
  };
  return aliases[t] ?? null;
}

export function normalizeDetectedExchange(
  raw: string | null | undefined,
): ExchangeId | null {
  if (!raw) return null;
  const e = raw.trim().toLowerCase();
  if (e.includes("binance")) return "binance";
  if (e.includes("bybit")) return "bybit";
  return null;
}

export function needsSymbolConfirmation(vision: VisionResult | null | undefined): boolean {
  if (!vision) return true;
  const symbol = normalizeDetectedSymbol(vision.detected_symbol);
  if (!symbol) return true;
  const conf = vision.symbol_confidence;
  if (typeof conf !== "number") return true;
  return conf < RECOGNITION_CONFIRM_THRESHOLD;
}

export function needsTimeframeConfirmation(
  vision: VisionResult | null | undefined,
): boolean {
  if (!vision) return true;
  const tf = normalizeDetectedTimeframe(vision.detected_timeframe);
  if (!tf) return true;
  const conf = vision.timeframe_confidence;
  if (typeof conf !== "number") return true;
  return conf < RECOGNITION_CONFIRM_THRESHOLD;
}

export function draftFromVision(
  vision: VisionResult | null | undefined,
  fallback: {
    exchange: ExchangeId;
    marketType: MarketType;
    symbol: string;
    timeframe: Timeframe;
  },
): RecognitionDraft {
  const symbol = normalizeDetectedSymbol(vision?.detected_symbol) || fallback.symbol;
  const timeframe =
    normalizeDetectedTimeframe(vision?.detected_timeframe) || fallback.timeframe;
  const exchange = normalizeDetectedExchange(vision?.detected_exchange) || fallback.exchange;
  return {
    exchange,
    marketType: fallback.marketType,
    symbol,
    timeframe,
    symbolConfirmed: !needsSymbolConfirmation(vision),
    timeframeConfirmed: !needsTimeframeConfirmation(vision),
  };
}

export function formatConfidence(value: number | null | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "unavailable";
  return `${Math.round(value * 100)}%`;
}

export function formatDiscrepancyPct(value: number | null | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "unavailable";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}
