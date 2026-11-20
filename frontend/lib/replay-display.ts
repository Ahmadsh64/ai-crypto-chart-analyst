import type { Candle, ReplaySnapshot, ReplayStatus, Timeframe } from "@/types/api";

/** Build chart candles visible at replay clock — closed + optional forming, no future. */
export function candlesFromReplaySnapshot(
  snapshot: ReplaySnapshot | null,
  timeframe: Timeframe,
): { closed: Candle[]; forming: Candle | null } {
  if (!snapshot) return { closed: [], forming: null };
  const state = snapshot.timeframes[timeframe];
  if (!state) return { closed: [], forming: null };
  const forming =
    state.forming_candle && state.forming_candle.open > 0 ? state.forming_candle : null;
  return { closed: state.closed_candles ?? [], forming };
}

export function replayProgressLabel(snapshot: ReplaySnapshot | null): string {
  if (!snapshot) return "—";
  return `${snapshot.event_index + 1} / ${snapshot.event_count} (${snapshot.progress_pct.toFixed(1)}%)`;
}

export function replayStatusLabel(status: ReplayStatus | null | undefined): string {
  if (!status) return "Idle";
  const map: Record<ReplayStatus, string> = {
    created: "Created",
    loading: "Loading",
    ready: "Ready",
    running: "Playing",
    paused: "Paused",
    completed: "Completed",
    stopped: "Stopped",
    error: "Error",
  };
  return map[status] ?? status;
}

export function replayQualityTone(quality: string | undefined): string {
  if (quality === "ok") return "text-terminal-long";
  if (quality === "partial" || quality === "gaps") return "text-amber-400";
  if (quality === "insufficient" || quality === "empty") return "text-terminal-short";
  return "text-terminal-muted";
}

export function formatReplayClock(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().replace("T", " ").replace(/\.\d{3}Z$/, " UTC");
}

/** Scrubber is usable only when a loaded timeline exists. */
export function scrubberEnabled(
  snapshot: ReplaySnapshot | null,
  opts: { sessionReady: boolean; busy: boolean },
): boolean {
  if (!opts.sessionReady || opts.busy) return false;
  if (!snapshot) return false;
  return snapshot.event_count > 0;
}

/** Clamp a requested seek index into [0, event_count - 1]. */
export function clampSeekIndex(index: number, eventCount: number): number {
  if (eventCount <= 0) return 0;
  return Math.max(0, Math.min(Math.trunc(index), eventCount - 1));
}

export function scrubberLabel(eventIndex: number, eventCount: number): string {
  if (eventCount <= 0) return "No events";
  return `Event ${eventIndex + 1} / ${eventCount}`;
}
