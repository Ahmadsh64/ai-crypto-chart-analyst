/**
 * Pure helpers for Market Structure chart overlays.
 * Kept free of React so mapping can be unit-tested.
 */

import type { UTCTimestamp } from "lightweight-charts";
import type {
  CHoCHEvent,
  MSSEvent,
  StructureBreakEvent,
  StructureLabel,
  SwingPoint,
} from "@/types/api";
import type { StructureSegmentDrawSpec } from "@/lib/structure-segment-primitive";

export type PriceMarkerPosition = "atPriceTop" | "atPriceBottom" | "atPriceMiddle";

export interface PriceAnchoredMarker {
  id: string;
  time: UTCTimestamp;
  position: PriceMarkerPosition;
  shape: "circle" | "square" | "arrowUp" | "arrowDown";
  color: string;
  text: string;
  price: number;
  kind: "swing" | "bos" | "choch" | "mss";
}

export interface BosSegmentPoints {
  id: string;
  price: number;
  start: UTCTimestamp;
  end: UTCTimestamp;
  active: boolean;
  direction: "bullish" | "bearish";
  label: string;
  style: "bos" | "choch";
  points: { time: UTCTimestamp; value: number }[];
}

export interface StructureOverlayOptions {
  showSwings: boolean;
  showHh: boolean;
  showHl: boolean;
  showLh: boolean;
  showLl: boolean;
  showBos: boolean;
  showChoch: boolean;
  showMss: boolean;
  /** Max labeled events per category (most recent). Older swings keep markers without text. */
  maxLabeledPerCategory: number;
  /** When true, hide label text on older events beyond maxLabeledPerCategory. */
  hideOlderLabels: boolean;
}

export const DEFAULT_OVERLAY_OPTIONS: StructureOverlayOptions = {
  showSwings: true,
  showHh: true,
  showHl: true,
  showLh: true,
  showLl: true,
  showBos: true,
  showChoch: true,
  showMss: false,
  maxLabeledPerCategory: 8,
  hideOlderLabels: true,
};

export function toUtcTimestamp(iso: string): UTCTimestamp {
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) {
    throw new Error(`Invalid ISO timestamp for chart mapping: ${iso}`);
  }
  // Lightweight Charts UTCTimestamp is seconds since epoch — never pass ms.
  return Math.floor(ms / 1000) as UTCTimestamp;
}

/** Build a set of candle open times (seconds) for snapping structure endpoints. */
export function buildCandleTimeSet(candleTimestampsIso: string[]): Set<number> {
  const set = new Set<number>();
  for (const iso of candleTimestampsIso) {
    set.add(Number(toUtcTimestamp(iso)));
  }
  return set;
}

/**
 * Snap a structure timestamp onto an existing candle open time.
 * Prefer exact match; otherwise nearest candle time (guards against Z vs +00:00 drift).
 */
export function snapToCandleTime(
  iso: string,
  candleTimes: Set<number>,
): UTCTimestamp | null {
  const t = Number(toUtcTimestamp(iso));
  if (candleTimes.has(t)) return t as UTCTimestamp;
  if (candleTimes.size === 0) return t as UTCTimestamp;

  let best: number | null = null;
  let bestDist = Number.POSITIVE_INFINITY;
  for (const ct of candleTimes) {
    const d = Math.abs(ct - t);
    if (d < bestDist) {
      bestDist = d;
      best = ct;
    }
  }
  // Only accept snaps within 1 hour — otherwise the event is outside the series.
  if (best == null || bestDist > 3600) return null;
  return best as UTCTimestamp;
}

/** Resolve original swing candle time for a structure break (API field or swing lookup). */
export function resolveBrokenSwingTimestamp(
  ev: Pick<StructureBreakEvent, "broken_swing_timestamp" | "broken_swing_key" | "candle_timestamp">,
  swings: SwingPoint[] = [],
): string {
  if (ev.broken_swing_timestamp) return ev.broken_swing_timestamp;
  const swing = swings.find((s) => s.event_key === ev.broken_swing_key);
  if (swing?.candle_timestamp) return swing.candle_timestamp;
  return ev.candle_timestamp;
}

function isClassificationEnabled(
  classification: StructureLabel,
  opts: Pick<StructureOverlayOptions, "showHh" | "showHl" | "showLh" | "showLl">,
): boolean {
  if (classification === "HH") return opts.showHh;
  if (classification === "HL") return opts.showHl;
  if (classification === "LH") return opts.showLh;
  return opts.showLl;
}

export function mapSwingMarkers(
  swings: SwingPoint[],
  opts: Pick<
    StructureOverlayOptions,
    "showSwings" | "showHh" | "showHl" | "showLh" | "showLl"
  >,
): PriceAnchoredMarker[] {
  const anyClass = opts.showHh || opts.showHl || opts.showLh || opts.showLl;
  if (!opts.showSwings && !anyClass) return [];
  const out: PriceAnchoredMarker[] = [];
  for (const swing of swings) {
    if (!swing.confirmed) continue;
    const isHigh = swing.kind === "high";
    const classLabel = swing.classification ?? null;

    if (classLabel) {
      if (!isClassificationEnabled(classLabel, opts)) continue;
    } else if (!opts.showSwings) {
      continue;
    }

    out.push({
      id: swing.event_key,
      time: toUtcTimestamp(swing.candle_timestamp),
      position: isHigh ? "atPriceTop" : "atPriceBottom",
      shape: isHigh ? "arrowDown" : "arrowUp",
      color: isHigh ? "#f59e0b" : "#38bdf8",
      text: classLabel ?? (isHigh ? "SH" : "SL"),
      price: swing.price,
      kind: "swing",
    });
  }
  return out;
}

export function mapChochMarkers(events: CHoCHEvent[], enabled: boolean): PriceAnchoredMarker[] {
  if (!enabled) return [];
  return events.map((ev) => {
    const bull = ev.direction === "bullish";
    return {
      id: ev.event_key,
      time: toUtcTimestamp(ev.candle_timestamp),
      // Place text away from candle bodies: bullish below level, bearish above.
      position: bull ? ("atPriceBottom" as const) : ("atPriceTop" as const),
      shape: "square" as const,
      color: bull ? "#a3e635" : "#fb7185",
      text: bull ? "CHoCH↑" : "CHoCH↓",
      price: ev.broken_level,
      kind: "choch" as const,
    };
  });
}

export function mapMssMarkers(events: MSSEvent[], enabled: boolean): PriceAnchoredMarker[] {
  if (!enabled) return [];
  return events.map((ev) => {
    const bull = ev.direction === "bullish";
    return {
      id: ev.event_key,
      time: toUtcTimestamp(ev.candle_timestamp),
      position: "atPriceMiddle" as const,
      shape: "circle" as const,
      color: bull ? "#c084fc" : "#e879f9",
      text: bull ? "MSS↑" : "MSS↓",
      price: ev.broken_level,
      kind: "mss" as const,
    };
  });
}

/** BOS labels at breakout candle + exact broken_level (distinct from CHoCH). */
export function mapBosMarkers(
  events: StructureBreakEvent[],
  enabled: boolean,
): PriceAnchoredMarker[] {
  if (!enabled) return [];
  return events.map((ev) => {
    const bull = ev.direction === "bullish";
    return {
      id: `${ev.event_key}:label`,
      time: toUtcTimestamp(ev.candle_timestamp),
      // Bullish: label above the broken high; bearish: below the broken low.
      position: bull ? ("atPriceTop" as const) : ("atPriceBottom" as const),
      shape: bull ? ("arrowUp" as const) : ("arrowDown" as const),
      color: bull ? "#16a34a" : "#dc2626",
      text: bull ? "BOS↑" : "BOS↓",
      price: ev.broken_level,
      kind: "bos" as const,
    };
  });
}

/** Deduplicate while keeping distinct prices/ids at the same timestamp. */
export function dedupePriceMarkers(markers: PriceAnchoredMarker[]): PriceAnchoredMarker[] {
  const seen = new Set<string>();
  const unique: PriceAnchoredMarker[] = [];
  for (const m of markers) {
    const key = `${m.id}|${m.time}|${m.price}|${m.text}`;
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(m);
  }
  unique.sort((a, b) => Number(a.time) - Number(b.time) || a.price - b.price);
  return unique;
}

/**
 * Collision policy: keep exact prices; strip text from older events so markers
 * don't stack unreadable labels. Never mutates price/time.
 *
 * Swings share one recent budget (not 4× HH/HL/LH/LL) to avoid stacked labels.
 */
export function applyLabelCollisionPolicy(
  markers: PriceAnchoredMarker[],
  opts: Pick<StructureOverlayOptions, "maxLabeledPerCategory" | "hideOlderLabels">,
): PriceAnchoredMarker[] {
  if (!opts.hideOlderLabels) return markers;

  const byCategory = new Map<string, PriceAnchoredMarker[]>();
  for (const m of markers) {
    const cat =
      m.kind === "swing"
        ? "swing"
        : m.kind === "bos"
          ? "bos"
          : m.kind === "choch"
            ? "choch"
            : "mss";
    const list = byCategory.get(cat) ?? [];
    list.push(m);
    byCategory.set(cat, list);
  }

  const keepText = new Set<string>();
  const limits: Record<string, number> = {
    swing: Math.max(4, opts.maxLabeledPerCategory),
    bos: Math.max(3, Math.floor(opts.maxLabeledPerCategory / 2)),
    choch: Math.max(3, Math.floor(opts.maxLabeledPerCategory / 2)),
    mss: Math.max(2, Math.floor(opts.maxLabeledPerCategory / 3)),
  };

  for (const [cat, list] of byCategory) {
    const sorted = [...list].sort((a, b) => Number(b.time) - Number(a.time));
    const limit = limits[cat] ?? opts.maxLabeledPerCategory;
    for (const m of sorted.slice(0, limit)) {
      keepText.add(m.id);
    }
  }

  // Second pass: suppress text when two labeled markers share the same bar time.
  const labeledAtTime = new Map<number, string>();
  const blocked = new Set<string>();
  const priority = { bos: 0, choch: 1, mss: 2, swing: 3 } as const;
  const labeled = markers
    .filter((m) => keepText.has(m.id))
    .sort(
      (a, b) =>
        (priority[a.kind] ?? 9) - (priority[b.kind] ?? 9) || Number(b.time) - Number(a.time),
    );
  for (const m of labeled) {
    const t = Number(m.time);
    if (labeledAtTime.has(t)) {
      blocked.add(m.id);
      continue;
    }
    labeledAtTime.set(t, m.id);
  }

  return markers.map((m) => {
    if (keepText.has(m.id) && !blocked.has(m.id)) return m;
    return { ...m, text: "" };
  });
}

/** When decluttering, keep newest segments for drawing; historical data stays in the store/panel. */
export function selectRecentSegments<T extends { end: number } | { end: UTCTimestamp }>(
  segments: T[],
  maxCount: number,
  enabled: boolean,
): T[] {
  if (!enabled || segments.length <= maxCount) return segments;
  return [...segments]
    .sort((a, b) => Number(b.end) - Number(a.end))
    .slice(0, maxCount)
    .sort((a, b) => Number(a.end) - Number(b.end));
}

/**
 * Horizontal BOS segments: original swing candle → breakout candle at broken_level.
 * Endpoints are snapped onto the candlestick time set so LWC coordinates align.
 */
export function mapBosSegments(
  events: StructureBreakEvent[],
  swings: SwingPoint[] = [],
  candleTimes?: Set<number>,
): BosSegmentPoints[] {
  const out: BosSegmentPoints[] = [];
  for (const ev of events) {
    const startIso = resolveBrokenSwingTimestamp(ev, swings);
    const endIso = ev.candle_timestamp;
    let start = toUtcTimestamp(startIso);
    let end = toUtcTimestamp(endIso);
    if (candleTimes) {
      const snappedStart = snapToCandleTime(startIso, candleTimes);
      const snappedEnd = snapToCandleTime(endIso, candleTimes);
      if (snappedStart == null || snappedEnd == null) continue;
      start = snappedStart;
      end = snappedEnd;
    }
    if (end < start) end = start;
    const bull = ev.direction === "bullish";
    out.push({
      id: ev.event_key,
      price: ev.broken_level,
      start,
      end,
      active: Boolean(ev.segment_active),
      direction: ev.direction,
      label: bull ? "BOS↑" : "BOS↓",
      style: "bos",
      points: [
        { time: start, value: ev.broken_level },
        { time: end, value: ev.broken_level },
      ],
    });
  }
  return out;
}

/** CHoCH swing→break segments at exact broken_level. */
export function mapChochSegments(
  events: CHoCHEvent[],
  swings: SwingPoint[] = [],
  enabled = true,
  candleTimes?: Set<number>,
): BosSegmentPoints[] {
  if (!enabled) return [];
  const out: BosSegmentPoints[] = [];
  for (const ev of events) {
    const startIso = resolveBrokenSwingTimestamp(
      {
        broken_swing_timestamp: null,
        broken_swing_key: ev.broken_swing_key,
        candle_timestamp: ev.candle_timestamp,
      },
      swings,
    );
    let start = toUtcTimestamp(startIso);
    let end = toUtcTimestamp(ev.candle_timestamp);
    if (candleTimes) {
      const snappedStart = snapToCandleTime(startIso, candleTimes);
      const snappedEnd = snapToCandleTime(ev.candle_timestamp, candleTimes);
      if (snappedStart == null || snappedEnd == null) continue;
      start = snappedStart;
      end = snappedEnd;
    }
    if (end < start) end = start;
    const bull = ev.direction === "bullish";
    out.push({
      id: `${ev.event_key}:seg`,
      price: ev.broken_level,
      start,
      end,
      active: false,
      direction: ev.direction,
      label: bull ? "CHoCH↑" : "CHoCH↓",
      style: "choch",
      points: [
        { time: start, value: ev.broken_level },
        { time: end, value: ev.broken_level },
      ],
    });
  }
  return out;
}

/** Convert mapped segments into candle-series primitive draw specs. */
export function toSegmentDrawSpecs(segments: BosSegmentPoints[]): StructureSegmentDrawSpec[] {
  return segments.map((seg) => {
    const bull = seg.direction === "bullish";
    const isBos = seg.style === "bos";
    return {
      id: seg.id,
      start: seg.start,
      end: seg.end,
      price: seg.price,
      color: isBos
        ? bull
          ? "rgba(22, 163, 74, 0.95)"
          : "rgba(220, 38, 38, 0.95)"
        : bull
          ? "rgba(163, 230, 53, 0.75)"
          : "rgba(251, 113, 133, 0.75)",
      lineWidth: isBos ? 2 : 1,
      dashed: !isBos,
    };
  });
}

export function collectAnnotationPrices(
  markers: PriceAnchoredMarker[],
  segments: BosSegmentPoints[],
): number[] {
  const prices: number[] = [];
  for (const m of markers) prices.push(m.price);
  for (const s of segments) prices.push(s.price);
  return prices;
}

/** Simulate remapping after WS snapshot replace — ids must stay unique. */
export function assertNoDuplicateAnnotationIds(markers: PriceAnchoredMarker[]): string[] {
  const seen = new Set<string>();
  const dupes: string[] = [];
  for (const m of markers) {
    if (seen.has(m.id)) dupes.push(m.id);
    seen.add(m.id);
  }
  return dupes;
}
