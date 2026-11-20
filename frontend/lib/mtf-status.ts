/**
 * Multi-Timeframe card status helpers (Phase 4.1 — data readiness only).
 */

import type { MtfDataQuality, MtfTimeframeSeries } from "@/types/api";

export type MtfCardStatus =
  | "ready"
  | "loading"
  | "stale"
  | "insufficient"
  | "error"
  | "gaps";

export function resolveMtfCardStatus(
  series: MtfTimeframeSeries | null | undefined,
  opts: { loading: boolean; hasError: boolean },
): MtfCardStatus {
  const { loading, hasError } = opts;
  if (loading && !series) return "loading";
  if (hasError && !series) return "error";
  if (!series) return "loading";
  if (series.data_quality === "error" || series.data_quality === "unavailable") {
    return "error";
  }
  if (
    series.data_quality === "insufficient" ||
    (!series.is_ready && series.closed_candles_count === 0)
  ) {
    return "insufficient";
  }
  if (series.is_stale || series.data_quality === "stale") return "stale";
  if (series.data_quality === "gaps") return "gaps";
  if (series.is_ready) return "ready";
  return "insufficient";
}

export function mtfStatusLabel(status: MtfCardStatus): string {
  switch (status) {
    case "ready":
      return "Ready";
    case "loading":
      return "Loading";
    case "stale":
      return "Stale";
    case "insufficient":
      return "Insufficient Data";
    case "error":
      return "Error";
    case "gaps":
      return "Gaps";
  }
}

export function mtfStatusTone(status: MtfCardStatus): string {
  switch (status) {
    case "ready":
      return "border-terminal-long/50 text-terminal-long bg-terminal-long/10";
    case "loading":
      return "border-terminal-border text-terminal-muted bg-terminal-surface/40";
    case "stale":
      return "border-amber-500/50 text-amber-400 bg-amber-500/10";
    case "insufficient":
      return "border-terminal-border text-terminal-muted bg-terminal-surface/50";
    case "error":
      return "border-terminal-short/50 text-terminal-short bg-terminal-short/10";
    case "gaps":
      return "border-sky-500/50 text-sky-300 bg-sky-500/10";
  }
}

export function qualityLabel(q: MtfDataQuality): string {
  return q;
}
