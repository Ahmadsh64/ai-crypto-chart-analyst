/**
 * Pure helpers for Liquidity chart overlays (Phase 3.3.1).
 */

import type { UTCTimestamp } from "lightweight-charts";
import type { EqualExtremeCluster, LiquidityLevel, LiquiditySweep } from "@/types/api";
import type { StructureSegmentDrawSpec } from "@/lib/structure-segment-primitive";
import { toUtcTimestamp } from "@/lib/structure-chart-overlays";

export type LiquidityOverlayId = "eqh" | "eql" | "bsl" | "ssl" | "sweeps";

export interface LiquidityMarker {
  id: string;
  time: UTCTimestamp;
  price: number;
  position: "atPriceTop" | "atPriceBottom" | "atPriceMiddle";
  shape: "circle" | "square" | "arrowUp" | "arrowDown";
  color: string;
  text: string;
}

function segmentEnd(
  level: LiquidityLevel,
  fallbackIso: string | null,
): UTCTimestamp {
  const endIso =
    level.segment_end ??
    level.status_changed_timestamp ??
    fallbackIso ??
    level.detection_timestamp;
  const start = toUtcTimestamp(level.segment_start ?? level.detection_timestamp);
  let end = toUtcTimestamp(endIso);
  if (end < start) end = start;
  return end;
}

function clusterPrice(c: EqualExtremeCluster): number {
  return c.representative_level ?? c.level;
}

/** EQH / EQL / BSL / SSL finite segments at exact prices. */
export function mapLiquiditySegments(
  opts: {
    eqh: EqualExtremeCluster[];
    eql: EqualExtremeCluster[];
    bsl: LiquidityLevel[];
    ssl: LiquidityLevel[];
    showEqh: boolean;
    showEql: boolean;
    showBsl: boolean;
    showSsl: boolean;
    fallbackEndIso: string | null;
  },
): StructureSegmentDrawSpec[] {
  const out: StructureSegmentDrawSpec[] = [];

  if (opts.showEqh) {
    for (const c of opts.eqh) {
      const start = toUtcTimestamp(c.first_detection_timestamp);
      const end = toUtcTimestamp(c.latest_confirmation_timestamp);
      out.push({
        id: c.event_key,
        start,
        end: end < start ? start : end,
        price: clusterPrice(c),
        color: "rgba(249, 115, 22, 0.85)", // orange zone
        lineWidth: 3,
        dashed: false,
      });
    }
  }

  if (opts.showEql) {
    for (const c of opts.eql) {
      const start = toUtcTimestamp(c.first_detection_timestamp);
      const end = toUtcTimestamp(c.latest_confirmation_timestamp);
      out.push({
        id: c.event_key,
        start,
        end: end < start ? start : end,
        price: clusterPrice(c),
        color: "rgba(56, 189, 248, 0.85)", // blue zone
        lineWidth: 3,
        dashed: false,
      });
    }
  }

  if (opts.showBsl) {
    for (const lv of opts.bsl) {
      if (lv.source_type === "eqh") continue; // already drawn as EQH zone
      const start = toUtcTimestamp(lv.segment_start ?? lv.detection_timestamp);
      const end = segmentEnd(lv, opts.fallbackEndIso);
      const active = lv.status === "active";
      out.push({
        id: lv.event_key,
        start,
        end,
        price: lv.price,
        color: active ? "rgba(34, 197, 94, 0.75)" : "rgba(34, 197, 94, 0.3)",
        lineWidth: active ? 2 : 1,
        dashed: lv.status !== "active",
      });
    }
  }

  if (opts.showSsl) {
    for (const lv of opts.ssl) {
      if (lv.source_type === "eql") continue;
      const start = toUtcTimestamp(lv.segment_start ?? lv.detection_timestamp);
      const end = segmentEnd(lv, opts.fallbackEndIso);
      const active = lv.status === "active";
      out.push({
        id: lv.event_key,
        start,
        end,
        price: lv.price,
        color: active ? "rgba(239, 68, 68, 0.75)" : "rgba(239, 68, 68, 0.3)",
        lineWidth: active ? 2 : 1,
        dashed: lv.status !== "active",
      });
    }
  }

  return out;
}

/**
 * Sweep markers: label = liquidity pool; arrow/color = reaction_hint.
 * reaction_hint is contextual only — never presented as a guaranteed reversal.
 */
export function mapSweepMarkers(
  sweeps: LiquiditySweep[],
  enabled: boolean,
): LiquidityMarker[] {
  if (!enabled) return [];
  return sweeps
    .filter((s) => s.confirmed)
    .map((s) => {
      const pool = s.liquidity_type.toUpperCase();
      const hint = s.reaction_hint;
      const bullishHint = hint === "bullish";
      const bearishHint = hint === "bearish";

      if (bullishHint) {
        return {
          id: s.event_key,
          time: toUtcTimestamp(s.candle_timestamp),
          price: s.level_price,
          position: "atPriceBottom" as const,
          shape: "arrowUp" as const,
          color: "#22c55e",
          text: `${pool} ↑`,
        };
      }
      if (bearishHint) {
        return {
          id: s.event_key,
          time: toUtcTimestamp(s.candle_timestamp),
          price: s.level_price,
          position: "atPriceTop" as const,
          shape: "arrowDown" as const,
          color: "#f97316",
          text: `${pool} ↓`,
        };
      }
      // Unavailable hint — still identify the pool without implying reaction.
      return {
        id: s.event_key,
        time: toUtcTimestamp(s.candle_timestamp),
        price: s.level_price,
        position: "atPriceMiddle" as const,
        shape: "circle" as const,
        color: "#94a3b8",
        text: `${pool} sweep`,
      };
    });
}
