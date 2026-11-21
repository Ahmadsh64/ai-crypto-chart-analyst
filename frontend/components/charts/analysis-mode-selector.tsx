"use client";

import { ImageUp, Radio } from "lucide-react";
import {
  ANALYSIS_MODE_LABELS,
  type AnalysisMode,
} from "@/lib/analysis-mode";
import { cn } from "@/utils/cn";

interface AnalysisModeSelectorProps {
  mode: AnalysisMode;
  onChange: (mode: AnalysisMode) => void;
  disabled?: boolean;
}

export function AnalysisModeSelector({
  mode,
  onChange,
  disabled,
}: AnalysisModeSelectorProps) {
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2" role="tablist" aria-label="Analysis mode">
      {(
        [
          { id: "LIVE_MARKET" as const, icon: Radio },
          { id: "UPLOADED_IMAGE" as const, icon: ImageUp },
        ] as const
      ).map(({ id, icon: Icon }) => {
        const active = mode === id;
        return (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={active}
            disabled={disabled}
            onClick={() => onChange(id)}
            className={cn(
              "flex items-center gap-2 rounded-md border px-3 py-2.5 text-left text-sm transition",
              active
                ? "border-terminal-accent bg-terminal-accent/10 text-terminal-text"
                : "border-terminal-border bg-terminal-surface text-terminal-muted hover:border-terminal-accent/40 hover:text-terminal-text",
              disabled && "cursor-not-allowed opacity-50",
            )}
          >
            <Icon className="h-4 w-4 shrink-0" />
            <span className="font-medium">{ANALYSIS_MODE_LABELS[id]}</span>
          </button>
        );
      })}
    </div>
  );
}
