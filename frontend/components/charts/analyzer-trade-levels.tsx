"use client";

import type { AnalyzerTradeLevelsModel, DisplayLevel } from "@/lib/analyzer-dashboard-display";
import { formatPrice } from "@/utils/format";
import { cn } from "@/utils/cn";

interface AnalyzerTradeLevelsProps {
  model: AnalyzerTradeLevelsModel;
  loading?: boolean;
}

function LevelRow({
  level,
  tone,
}: {
  level: DisplayLevel;
  tone: "live" | "entry" | "sl" | "tp" | "muted";
}) {
  const valueClass =
    !level.available
      ? "text-terminal-muted"
      : tone === "live"
        ? "text-terminal-accent"
        : tone === "entry"
          ? "text-sky-300"
          : tone === "sl"
            ? "text-terminal-short"
            : tone === "tp"
              ? "text-terminal-long"
              : "text-terminal-text";

  return (
    <div
      className="flex items-start justify-between gap-3 border-b border-terminal-border/50 py-2 last:border-0"
      data-testid={`level-${level.label.replace(/\s+/g, "-").toLowerCase()}`}
    >
      <div className="min-w-0">
        <p className="text-[11px] font-medium uppercase tracking-wide text-terminal-muted">
          {level.label}
        </p>
        {level.detail ? (
          <p className="mt-0.5 truncate text-[10px] text-terminal-muted">{level.detail}</p>
        ) : null}
      </div>
      <p className={cn("shrink-0 font-mono text-sm font-semibold tabular-nums", valueClass)}>
        {level.available ? formatPrice(level.price) : "Unavailable"}
      </p>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-md border border-terminal-border/70 bg-terminal-surface/40 p-3">
      <p className="mb-1 text-[10px] uppercase tracking-[0.14em] text-terminal-muted">{title}</p>
      {children}
    </div>
  );
}

export function AnalyzerTradeLevels({ model, loading }: AnalyzerTradeLevelsProps) {
  return (
    <section
      className="rounded-lg border border-terminal-border bg-terminal-panel p-4"
      data-testid="trade-levels"
      aria-label="Trade levels"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="text-[11px] uppercase tracking-[0.16em] text-terminal-muted">
          Trade levels
        </p>
        <span className="rounded border border-terminal-border px-1.5 py-0.5 text-[10px] text-terminal-muted">
          Planned · not fills
        </span>
      </div>

      {loading ? (
        <p className="text-sm text-terminal-muted">Loading trade plan…</p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          <Section title="Market information">
            <LevelRow
              level={{
                label: "Current live price",
                price: model.livePrice,
                available: model.livePrice != null,
                detail: "Verified exchange data",
              }}
              tone="live"
            />
          </Section>

          <Section title="Entry information">
            <LevelRow level={model.entry} tone="entry" />
            {model.entryZone ? (
              <div className="flex justify-between gap-3 py-1 text-xs">
                <span className="text-terminal-muted">Zone</span>
                <span className="font-mono text-sky-300">
                  {formatPrice(model.entryZone.low)} – {formatPrice(model.entryZone.high)}
                </span>
              </div>
            ) : null}
            <div className="flex justify-between gap-3 py-1 text-xs">
              <span className="text-terminal-muted">Entry status</span>
              <span className="font-mono text-terminal-text">
                {model.entryStatus ?? "—"}
              </span>
            </div>
          </Section>

          <Section title="Risk management">
            <LevelRow level={model.stopLoss} tone="sl" />
            <LevelRow level={model.invalidation} tone="sl" />
          </Section>

          <Section title="Take profit">
            <LevelRow level={model.takeProfits[0]} tone="tp" />
            <LevelRow level={model.takeProfits[1]} tone="tp" />
            <LevelRow level={model.takeProfits[2]} tone="tp" />
            <div className="flex justify-between gap-3 py-1 text-xs">
              <span className="text-terminal-muted">Primary R:R</span>
              <span className="font-mono text-terminal-text">
                {model.primaryRr != null ? model.primaryRr.toFixed(2) : "Unavailable"}
              </span>
            </div>
          </Section>
        </div>
      )}

      <p className="mt-3 text-[10px] text-terminal-muted">{model.plannedNotExecutedNote}</p>
      {!model.showTradeLevels && model.decision ? (
        <p className="mt-1 text-[10px] text-amber-200/90">
          Decision is {model.decision} — levels intentionally withheld (no invented prices).
        </p>
      ) : null}
    </section>
  );
}
