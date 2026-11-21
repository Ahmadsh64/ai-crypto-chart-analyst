/** Phase 5.4.2.2 — dual analysis modes for AI Market Analyzer. */

export type AnalysisMode = "LIVE_MARKET" | "UPLOADED_IMAGE";

export const ANALYSIS_MODE_LABELS: Record<AnalysisMode, string> = {
  LIVE_MARKET: "Live Market Analysis",
  UPLOADED_IMAGE: "Upload Chart Image",
};

export function isAnalysisMode(value: string | null | undefined): value is AnalysisMode {
  return value === "LIVE_MARKET" || value === "UPLOADED_IMAGE";
}
