/**
 * OHLC crosshair lookup helpers — exact candle values only, never fabricated.
 */

import type { Candle } from "@/types/api";
import type { LiveCandle } from "@/stores/live-market-store";

export interface OhlcHoverInfo {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  changePct: number;
  timeSec: number;
}

export function candleChangePct(open: number, close: number): number {
  if (!Number.isFinite(open) || open === 0) return 0;
  return ((close - open) / open) * 100;
}

export function toOhlcHoverInfo(
  c: Pick<Candle, "timestamp" | "open" | "high" | "low" | "close" | "volume">,
): OhlcHoverInfo {
  return {
    timestamp: c.timestamp,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
    volume: c.volume,
    changePct: candleChangePct(c.open, c.close),
    timeSec: Math.floor(new Date(c.timestamp).getTime() / 1000),
  };
}

/** Build a timestamp→candle map; live candle overrides historical at the same second. */
export function buildCandleLookup(
  candles: Candle[],
  liveCandle?: LiveCandle | null,
): Map<number, OhlcHoverInfo> {
  const map = new Map<number, OhlcHoverInfo>();
  for (const c of candles) {
    const info = toOhlcHoverInfo(c);
    map.set(info.timeSec, info);
  }
  if (liveCandle) {
    const info = toOhlcHoverInfo({
      timestamp: liveCandle.timestamp,
      open: liveCandle.open,
      high: liveCandle.high,
      low: liveCandle.low,
      close: liveCandle.close,
      volume: liveCandle.volume,
    });
    map.set(info.timeSec, info);
  }
  return map;
}

export function lookupCandleAtTimeSec(
  lookup: Map<number, OhlcHoverInfo>,
  timeSec: number | null | undefined,
): OhlcHoverInfo | null {
  if (timeSec == null || !Number.isFinite(timeSec)) return null;
  return lookup.get(Math.floor(timeSec)) ?? null;
}
