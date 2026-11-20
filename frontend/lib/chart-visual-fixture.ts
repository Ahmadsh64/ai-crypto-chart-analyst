/**
 * Deterministic Chart Analyzer visual verification fixture.
 * Known candles + structure events with exact timestamps and prices.
 */

import type {
  Candle,
  CHoCHEvent,
  MSSEvent,
  StructureBreakEvent,
  SwingPoint,
} from "@/types/api";

const CFG = "ms-v1.0.0-balanced";
const META = {
  exchange: "binance" as const,
  symbol: "BTC/USDT",
  market_type: "spot" as const,
  timeframe: "1h" as const,
};

function candle(
  iso: string,
  open: number,
  high: number,
  low: number,
  close: number,
  volume: number,
): Candle {
  return {
    ...META,
    timestamp: iso,
    open,
    high,
    low,
    close,
    volume,
    is_closed: true,
  };
}

/** Confirmed swing high at t=03:00 price 120 */
const SWING_HIGH: SwingPoint = {
  ...META,
  event_key: "fixture:swing:high:120",
  kind: "high",
  price: 120,
  candle_timestamp: "2024-06-01T03:00:00.000Z",
  confirmation_timestamp: "2024-06-01T06:00:00.000Z",
  confirmed: true,
  classification: "HH",
  previous_swing_key: null,
  previous_swing_price: null,
  config_version: CFG,
  candle_index: 3,
};

/** Confirmed swing low at t=05:00 price 100 */
const SWING_LOW: SwingPoint = {
  ...META,
  event_key: "fixture:swing:low:100",
  kind: "low",
  price: 100,
  candle_timestamp: "2024-06-01T05:00:00.000Z",
  confirmation_timestamp: "2024-06-01T08:00:00.000Z",
  confirmed: true,
  classification: "LL",
  previous_swing_key: null,
  previous_swing_price: null,
  config_version: CFG,
  candle_index: 5,
};

const BULLISH_BOS: StructureBreakEvent = {
  event_key: "fixture:bos:bull:120",
  break_kind: "bos",
  direction: "bullish",
  broken_level: 120,
  broken_swing_key: SWING_HIGH.event_key,
  broken_swing_timestamp: SWING_HIGH.candle_timestamp,
  close_price: 122,
  candle_timestamp: "2024-06-01T09:00:00.000Z",
  confirmation_timestamp: "2024-06-01T09:00:00.000Z",
  previous_bias: "undefined",
  new_bias: "bullish",
  config_version: CFG,
  segment_active: true,
};

const BEARISH_BOS: StructureBreakEvent = {
  event_key: "fixture:bos:bear:100",
  break_kind: "bos",
  direction: "bearish",
  broken_level: 100,
  broken_swing_key: SWING_LOW.event_key,
  broken_swing_timestamp: SWING_LOW.candle_timestamp,
  close_price: 98,
  candle_timestamp: "2024-06-01T12:00:00.000Z",
  confirmation_timestamp: "2024-06-01T12:00:00.000Z",
  previous_bias: "bullish",
  new_bias: "bearish",
  config_version: CFG,
  segment_active: true,
};

const BULLISH_CHOCH: CHoCHEvent = {
  event_key: "fixture:choch:bull:100",
  direction: "bullish",
  broken_level: 100,
  broken_swing_key: SWING_LOW.event_key,
  close_price: 101.5,
  candle_timestamp: "2024-06-01T14:00:00.000Z",
  confirmation_timestamp: "2024-06-01T14:00:00.000Z",
  previous_bias: "bearish",
  new_bias: "bullish",
  config_version: CFG,
  structure_break_key: "fixture:choch:bull:100",
};

const BEARISH_CHOCH: CHoCHEvent = {
  event_key: "fixture:choch:bear:120",
  direction: "bearish",
  broken_level: 120,
  broken_swing_key: SWING_HIGH.event_key,
  close_price: 118,
  candle_timestamp: "2024-06-01T16:00:00.000Z",
  confirmation_timestamp: "2024-06-01T16:00:00.000Z",
  previous_bias: "bullish",
  new_bias: "bearish",
  config_version: CFG,
  structure_break_key: "fixture:choch:bear:120",
};

const BULLISH_MSS: MSSEvent = {
  event_key: "fixture:mss:bull",
  direction: "bullish",
  choch_event_key: BULLISH_CHOCH.event_key,
  broken_level: 100,
  close_price: 104,
  candle_timestamp: "2024-06-01T14:00:00.000Z",
  confirmation_timestamp: "2024-06-01T14:00:00.000Z",
  body_size: 4,
  atr_value: 2,
  displacement_mult: 2,
  previous_bias: "bearish",
  new_bias: "bullish",
  config_version: CFG,
};

export const VISUAL_FIXTURE = {
  candles: [
    candle("2024-06-01T00:00:00.000Z", 105, 108, 104, 106, 1000),
    candle("2024-06-01T01:00:00.000Z", 106, 110, 105, 109, 1100),
    candle("2024-06-01T02:00:00.000Z", 109, 115, 108, 114, 1200),
    candle("2024-06-01T03:00:00.000Z", 114, 120, 113, 118, 1500), // swing high
    candle("2024-06-01T04:00:00.000Z", 118, 119, 112, 113, 1300),
    candle("2024-06-01T05:00:00.000Z", 113, 114, 100, 102, 1600), // swing low
    candle("2024-06-01T06:00:00.000Z", 102, 108, 101, 107, 1400),
    candle("2024-06-01T07:00:00.000Z", 107, 111, 106, 110, 1250),
    candle("2024-06-01T08:00:00.000Z", 110, 116, 109, 115, 1350),
    candle("2024-06-01T09:00:00.000Z", 115, 123, 114, 122, 1800), // bullish BOS
    candle("2024-06-01T10:00:00.000Z", 122, 124, 118, 119, 1450),
    candle("2024-06-01T11:00:00.000Z", 119, 120, 105, 106, 1550),
    candle("2024-06-01T12:00:00.000Z", 106, 107, 97, 98, 1900), // bearish BOS
    candle("2024-06-01T13:00:00.000Z", 98, 99, 96, 97, 1500),
    candle("2024-06-01T14:00:00.000Z", 97, 105, 96, 104, 2000), // bullish CHoCH + MSS
    candle("2024-06-01T15:00:00.000Z", 104, 112, 103, 111, 1600),
    candle("2024-06-01T16:00:00.000Z", 111, 113, 110, 118, 1700), // bearish CHoCH candle
  ] as Candle[],
  swings: [SWING_HIGH, SWING_LOW] as SwingPoint[],
  bosEvents: [BULLISH_BOS, BEARISH_BOS] as StructureBreakEvent[],
  chochEvents: [BULLISH_CHOCH, BEARISH_CHOCH] as CHoCHEvent[],
  mssEvents: [BULLISH_MSS] as MSSEvent[],
};

export type VisualFixture = typeof VISUAL_FIXTURE;
