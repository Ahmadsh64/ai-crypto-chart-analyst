"use client";

import { useCallback, useRef, useState, type DragEvent } from "react";
import { ImagePlus, Trash2, Replace } from "lucide-react";
import {
  formatFileSize,
  validateChartScreenshotFile,
} from "@/lib/ai-analysis-display";
import { cn } from "@/utils/cn";

interface ChartImageUploadProps {
  file: File | null;
  previewUrl: string | null;
  onFileChange: (file: File | null, previewUrl: string | null) => void;
  disabled?: boolean;
}

export function ChartImageUpload({
  file,
  previewUrl,
  onFileChange,
  disabled,
}: ChartImageUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const applyFile = useCallback(
    (next: File | null) => {
      if (!next) {
        setError(null);
        onFileChange(null, null);
        return;
      }
      const check = validateChartScreenshotFile(next);
      if (!check.ok) {
        setError(check.error);
        return;
      }
      setError(null);
      const url = URL.createObjectURL(next);
      onFileChange(next, url);
    },
    [onFileChange],
  );

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    if (disabled) return;
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) applyFile(dropped);
  };

  return (
    <div className="space-y-2">
      <div
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (disabled) return;
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => {
          if (!disabled) inputRef.current?.click();
        }}
        className={cn(
          "flex min-h-[140px] cursor-pointer flex-col items-center justify-center gap-2 rounded-md border border-dashed px-3 py-4 text-center transition",
          dragOver
            ? "border-terminal-accent bg-terminal-accent/10"
            : "border-terminal-border bg-terminal-surface",
          disabled && "cursor-not-allowed opacity-50",
        )}
        data-testid="chart-image-dropzone"
      >
        <ImagePlus className="h-6 w-6 text-terminal-muted" />
        <p className="text-sm text-terminal-text">
          Drop a chart screenshot, or click to browse
        </p>
        <p className="text-[11px] text-terminal-muted">
          PNG, JPEG, or WebP · max 10 MB · never stored publicly
        </p>
        <input
          ref={inputRef}
          type="file"
          accept="image/png,image/jpeg,image/jpg,image/webp"
          className="hidden"
          disabled={disabled}
          onChange={(e) => {
            const f = e.target.files?.[0] ?? null;
            applyFile(f);
            e.target.value = "";
          }}
        />
      </div>

      {error ? (
        <p className="text-[11px] text-terminal-short" data-testid="upload-error">
          {error}
        </p>
      ) : null}

      {file && previewUrl ? (
        <div className="rounded-md border border-terminal-border bg-terminal-panel p-2">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="truncate text-[11px] text-terminal-muted">
              {file.name} · {formatFileSize(file.size)}
            </p>
            <div className="flex gap-1">
              <button
                type="button"
                disabled={disabled}
                onClick={(e) => {
                  e.stopPropagation();
                  inputRef.current?.click();
                }}
                className="inline-flex items-center gap-1 rounded px-2 py-1 text-[11px] text-terminal-muted hover:bg-terminal-surface hover:text-terminal-text"
              >
                <Replace className="h-3 w-3" />
                Replace
              </button>
              <button
                type="button"
                disabled={disabled}
                onClick={(e) => {
                  e.stopPropagation();
                  applyFile(null);
                }}
                className="inline-flex items-center gap-1 rounded px-2 py-1 text-[11px] text-terminal-short hover:bg-terminal-surface"
              >
                <Trash2 className="h-3 w-3" />
                Remove
              </button>
            </div>
          </div>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={previewUrl}
            alt="Uploaded chart preview"
            className="max-h-[220px] w-full object-contain"
            data-testid="upload-preview"
          />
        </div>
      ) : null}
    </div>
  );
}
