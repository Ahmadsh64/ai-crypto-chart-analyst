/**
 * Phase 5.4.2 — export the live Lightweight Charts canvas for Vision analysis.
 */

import type { CandlestickChartHandle } from "@/components/charts/candlestick-chart";
import { validateChartScreenshotFile } from "@/lib/ai-analysis-display";

export type ChartExportResult =
  | { ok: true; file: File; previewUrl: string; capturedAt: string }
  | { ok: false; error: string };

export function chartExportFilename(args: {
  exchange: string;
  marketType: string;
  symbol: string;
  timeframe: string;
  capturedAt?: Date;
}): string {
  const ts = (args.capturedAt ?? new Date()).toISOString().replace(/[:.]/g, "-");
  const sym = args.symbol.replace("/", "");
  return `${args.exchange}_${args.marketType}_${sym}_${args.timeframe}_${ts}.png`;
}

export async function canvasToPngFile(
  canvas: HTMLCanvasElement,
  filename: string,
): Promise<File> {
  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error("Chart export produced an empty image."))),
      "image/png",
    );
  });
  return new File([blob], filename, { type: "image/png" });
}

export async function exportChartScreenshot(args: {
  chart: CandlestickChartHandle | null;
  exchange: string;
  marketType: string;
  symbol: string;
  timeframe: string;
}): Promise<ChartExportResult> {
  if (!args.chart?.isReady()) {
    return { ok: false, error: "Chart is not ready for export yet." };
  }
  const canvas = args.chart.takeScreenshot();
  if (!canvas || canvas.width < 8 || canvas.height < 8) {
    return { ok: false, error: "Chart screenshot failed — try again after the chart loads." };
  }
  const capturedAt = new Date();
  const filename = chartExportFilename({ ...args, capturedAt });
  try {
    const file = await canvasToPngFile(canvas, filename);
    const validation = validateChartScreenshotFile(file);
    if (!validation.ok) {
      return { ok: false, error: validation.error };
    }
    return {
      ok: true,
      file,
      previewUrl: URL.createObjectURL(file),
      capturedAt: capturedAt.toISOString(),
    };
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : "Chart export failed.",
    };
  }
}

/** Wait briefly for the chart paint cycle after data/overlay updates. */
export function waitForChartPaint(ms = 120): Promise<void> {
  return new Promise((resolve) => {
    window.requestAnimationFrame(() => {
      window.setTimeout(resolve, ms);
    });
  });
}
