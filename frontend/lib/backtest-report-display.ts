/** Display helpers for the backtest report panel (Phase 5.2.6). */

export type MetricAvailability = "available" | "unavailable" | "infinite";

export type ReportMetricLike = {
  value?: string | number | null;
  availability: MetricAvailability;
};

export function formatReportMetric(m?: ReportMetricLike | null): string {
  if (!m) return "N/A";
  if (m.availability === "unavailable") return "N/A";
  if (m.availability === "infinite") return "∞";
  if (m.value === null || m.value === undefined) return "N/A";
  const n = Number(m.value);
  if (!Number.isFinite(n)) return String(m.value);
  return n.toFixed(n >= 100 || n <= -100 ? 2 : 5);
}

export function formatReportNumber(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "N/A";
  const n = Number(v);
  if (!Number.isFinite(n)) return "N/A";
  return n.toFixed(5);
}

export function formatReportUtc(iso?: string | null): string {
  if (!iso) return "—";
  return iso.replace("+00:00", "Z");
}

export function pnlTone(v: string | number | null | undefined): "long" | "short" | "muted" {
  if (v === null || v === undefined || v === "") return "muted";
  const n = Number(v);
  if (!Number.isFinite(n) || n === 0) return "muted";
  return n > 0 ? "long" : "short";
}

export const REPORT_DISCLAIMER =
  "HISTORICAL BACKTEST — SIMULATED RESULTS — NOT REAL ORDERS — NOT FINANCIAL ADVICE";

export type ReportExportKind = "summary" | "trades" | "equity" | "drawdown";

export const REPORT_EXPORT_ACTIONS: {
  kind: ReportExportKind | "pdf";
  label: string;
}[] = [
  { kind: "pdf", label: "Export PDF" },
  { kind: "trades", label: "Export Trades CSV" },
  { kind: "equity", label: "Export Equity CSV" },
  { kind: "drawdown", label: "Export Drawdown CSV" },
  { kind: "summary", label: "Export Summary CSV" },
];
