/**
 * Map OB/FVG API models to zone draw specs (Phase 3.4).
 */

import type { UTCTimestamp } from "lightweight-charts";
import type { FairValueGap, OrderBlock } from "@/types/api";
import type { ZoneDrawSpec } from "@/lib/zone-primitive";
import { toUtcTimestamp } from "@/lib/structure-chart-overlays";

export type ObFvgOverlayId =
  | "bullishOb"
  | "bearishOb"
  | "bullishFvg"
  | "bearishFvg"
  | "recentZones";

function zoneEnd(isoStart: string, isoEnd: string | null | undefined, fallback: string | null): UTCTimestamp {
  const start = toUtcTimestamp(isoStart);
  let end = toUtcTimestamp(isoEnd ?? fallback ?? isoStart);
  if (end < start) end = start;
  return end;
}

function activeStyle(status: string): { fill: string; stroke: string; dashed: boolean } {
  const terminal = status === "mitigated" || status === "filled" || status === "invalidated";
  return {
    fill: terminal ? "rgba(148, 163, 184, 0.12)" : "",
    stroke: terminal ? "rgba(148, 163, 184, 0.5)" : "",
    dashed: terminal,
  };
}

export function mapObFvgZones(opts: {
  bullishObs: OrderBlock[];
  bearishObs: OrderBlock[];
  bullishFvgs: FairValueGap[];
  bearishFvgs: FairValueGap[];
  showBullishOb: boolean;
  showBearishOb: boolean;
  showBullishFvg: boolean;
  showBearishFvg: boolean;
  recentOnly: boolean;
  recentLimit?: number;
  fallbackEndIso: string | null;
}): ZoneDrawSpec[] {
  const out: ZoneDrawSpec[] = [];
  const limit = opts.recentLimit ?? 12;

  const pushOb = (blocks: OrderBlock[], bull: boolean) => {
    let list = [...blocks].sort(
      (a, b) =>
        Date.parse(b.detection_timestamp) - Date.parse(a.detection_timestamp),
    );
    if (opts.recentOnly) list = list.slice(0, limit);
    for (const ob of list) {
      const term = activeStyle(ob.status);
      const fill = bull
        ? term.dashed
          ? "rgba(34, 197, 94, 0.08)"
          : "rgba(34, 197, 94, 0.18)"
        : term.dashed
          ? "rgba(239, 68, 68, 0.08)"
          : "rgba(239, 68, 68, 0.18)";
      const stroke = bull ? "rgba(34, 197, 94, 0.85)" : "rgba(239, 68, 68, 0.85)";
      out.push({
        id: ob.event_key,
        start: toUtcTimestamp(ob.segment_start ?? ob.detection_timestamp),
        end: zoneEnd(
          ob.segment_start ?? ob.detection_timestamp,
          ob.segment_end,
          opts.fallbackEndIso,
        ),
        priceHigh: ob.zone_high,
        priceLow: ob.zone_low,
        fillColor: fill,
        strokeColor: stroke,
        dashed: term.dashed,
      });
    }
  };

  const pushFvg = (gaps: FairValueGap[], bull: boolean) => {
    let list = [...gaps].sort(
      (a, b) =>
        Date.parse(b.detection_timestamp) - Date.parse(a.detection_timestamp),
    );
    if (opts.recentOnly) list = list.slice(0, limit);
    for (const fvg of list) {
      const term = activeStyle(fvg.status);
      const fill = bull
        ? term.dashed
          ? "rgba(45, 212, 191, 0.08)"
          : "rgba(45, 212, 191, 0.2)"
        : term.dashed
          ? "rgba(249, 115, 22, 0.08)"
          : "rgba(249, 115, 22, 0.2)";
      const stroke = bull ? "rgba(45, 212, 191, 0.9)" : "rgba(249, 115, 22, 0.9)";
      out.push({
        id: fvg.event_key,
        start: toUtcTimestamp(fvg.segment_start ?? fvg.detection_timestamp),
        end: zoneEnd(
          fvg.segment_start ?? fvg.detection_timestamp,
          fvg.segment_end,
          opts.fallbackEndIso,
        ),
        priceHigh: fvg.zone_high,
        priceLow: fvg.zone_low,
        fillColor: fill,
        strokeColor: stroke,
        dashed: term.dashed,
      });
    }
  };

  if (opts.showBullishOb) pushOb(opts.bullishObs, true);
  if (opts.showBearishOb) pushOb(opts.bearishObs, false);
  if (opts.showBullishFvg) pushFvg(opts.bullishFvgs, true);
  if (opts.showBearishFvg) pushFvg(opts.bearishFvgs, false);
  return out;
}
