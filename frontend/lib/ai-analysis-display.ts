/**
 * Phase 5.4.0 — client helpers for Analyze / Vision UI (no trading logic).
 */

export const AI_ALLOWED_MIME = new Set([
  "image/png",
  "image/jpeg",
  "image/jpg",
  "image/webp",
]);

export const AI_MAX_UPLOAD_MB = 10;

export type UploadValidation =
  | { ok: true }
  | { ok: false; error: string };

export function validateChartScreenshotFile(
  file: Pick<File, "type" | "size">,
  maxMb = AI_MAX_UPLOAD_MB,
): UploadValidation {
  if (!AI_ALLOWED_MIME.has(file.type)) {
    return { ok: false, error: "Unsupported format. Use PNG, JPEG, or WebP." };
  }
  if (file.size > maxMb * 1024 * 1024) {
    return { ok: false, error: `Image exceeds ${maxMb} MB.` };
  }
  return { ok: true };
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

/** Stale-response guard: accept only if sequence still current. */
export function isCurrentRequest(seq: number, current: number): boolean {
  return seq === current;
}

export function shouldBlockDuplicateSubmit(loading: boolean): boolean {
  return loading;
}

export function explanationUnavailable(status: string | null | undefined): boolean {
  if (!status) return true;
  return status !== "OK" && status !== "INSUFFICIENT_DATA";
}

export function levelsFromSnapshot(snapshot: {
  entry_reference_price?: number | null;
  stop_loss_price?: number | null;
  take_profit_prices?: number[] | null;
}): {
  entry: number | null;
  stopLoss: number | null;
  takeProfits: number[];
} {
  return {
    entry:
      typeof snapshot.entry_reference_price === "number"
        ? snapshot.entry_reference_price
        : null,
    stopLoss:
      typeof snapshot.stop_loss_price === "number" ? snapshot.stop_loss_price : null,
    takeProfits: Array.isArray(snapshot.take_profit_prices)
      ? snapshot.take_profit_prices.filter((n) => typeof n === "number")
      : [],
  };
}

export function comparisonTone(status: string | null | undefined): string {
  switch (status) {
    case "CONSISTENT":
      return "consistent";
    case "PARTIALLY_CONSISTENT":
      return "partial";
    case "CONFLICTING":
      return "conflict";
    case "INSUFFICIENT_VISUAL_DATA":
      return "insufficient";
    default:
      return "unknown";
  }
}
