"use client";

import { cn } from "@/utils/cn";
import type {
  AnalysisExplanation,
  AnalysisSnapshot,
  VisionComparisonSummary,
  VisionResult,
} from "@/types/api";

function Section({
  title,
  children,
  defaultOpen = true,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details
      open={defaultOpen}
      className="rounded-md border border-terminal-border/60 bg-terminal-bg/30 p-2"
    >
      <summary className="cursor-pointer text-[10px] uppercase tracking-[0.14em] text-terminal-muted">
        {title}
      </summary>
      <div className="mt-2 space-y-1 text-xs text-terminal-text">{children}</div>
    </details>
  );
}

function List({ items }: { items: string[] }) {
  if (!items.length) return <p className="text-terminal-muted">—</p>;
  return (
    <ul className="max-h-36 space-y-1 overflow-y-auto">
      {items.map((item, i) => (
        <li key={`${i}-${item.slice(0, 24)}`} className="border-b border-terminal-border/30 py-1">
          {item || "—"}
        </li>
      ))}
    </ul>
  );
}

export function DeterministicSnapshotPanel({ snapshot }: { snapshot: AnalysisSnapshot }) {
  return (
    <div className="space-y-2 rounded-lg border border-terminal-border bg-terminal-panel p-3">
      <h3 className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
        Deterministic analysis
      </h3>
      <p className="font-mono text-sm text-terminal-text">
        {snapshot.decision} · {snapshot.symbol}
      </p>
      <p className="text-[11px] text-terminal-muted">{snapshot.decision_reason}</p>
      <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
        <div>Entry {snapshot.entry_reference_price ?? "—"}</div>
        <div>SL {snapshot.stop_loss_price ?? "—"}</div>
        <div className="col-span-2">
          TPs {(snapshot.take_profit_prices || []).join(" · ") || "—"}
        </div>
        <div>RR {snapshot.primary_rr ?? "—"}</div>
        <div>Freshness {snapshot.data_freshness}</div>
      </div>
      <p className="text-[10px] text-terminal-muted">
        Entry/SL/TP always from deterministic engines — never from AI text.
      </p>
    </div>
  );
}

export function AiExplanationPanel({
  explanation,
}: {
  explanation: AnalysisExplanation | null | undefined;
}) {
  if (!explanation) {
    return (
      <div className="rounded-lg border border-terminal-border bg-terminal-panel p-3 text-sm text-terminal-muted">
        No AI explanation yet.
      </div>
    );
  }

  const unavailable = explanation.status !== "OK" && explanation.status !== "INSUFFICIENT_DATA";

  return (
    <div className="space-y-2 rounded-lg border border-terminal-border bg-terminal-panel p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
          AI explanation
        </h3>
        <span
          className={cn(
            "rounded border px-2 py-0.5 text-[10px] uppercase tracking-wide",
            unavailable
              ? "border-amber-400/50 text-amber-200"
              : "border-terminal-long/40 text-terminal-long",
          )}
        >
          {explanation.status}
        </span>
      </div>
      {explanation.message ? (
        <p className="text-[11px] text-amber-200">{explanation.message}</p>
      ) : null}
      <Section title="AI summary">
        <p>{explanation.summary || "—"}</p>
      </Section>
      <Section title="Decision explanation">
        <p>{explanation.decision_explanation || "—"}</p>
      </Section>
      <Section title="Bullish evidence" defaultOpen={false}>
        <List items={explanation.bullish_evidence} />
      </Section>
      <Section title="Bearish evidence" defaultOpen={false}>
        <List items={explanation.bearish_evidence} />
      </Section>
      <Section title="Conflicting factors" defaultOpen={false}>
        <List items={explanation.conflicting_factors} />
      </Section>
      <Section title="Entry explanation" defaultOpen={false}>
        <p>{explanation.entry_explanation || "—"}</p>
      </Section>
      <Section title="Stop loss explanation" defaultOpen={false}>
        <p>{explanation.stop_loss_explanation || "—"}</p>
      </Section>
      <Section title="Take profit explanations" defaultOpen={false}>
        <List items={explanation.take_profit_explanations} />
      </Section>
      <Section title="Missing confirmations" defaultOpen={false}>
        <List items={explanation.missing_confirmations} />
      </Section>
      <Section title="Data limitations" defaultOpen={false}>
        <List items={explanation.data_limitations} />
      </Section>
      {explanation.validation_warnings?.length ? (
        <Section title="Validation warnings" defaultOpen={false}>
          <List items={explanation.validation_warnings} />
        </Section>
      ) : null}
      <p className="text-[10px] text-terminal-muted">{explanation.disclaimer}</p>
    </div>
  );
}

export function VisionObservationsPanel({ vision }: { vision: VisionResult | null }) {
  if (!vision) {
    return (
      <div className="rounded-lg border border-terminal-border bg-terminal-panel p-3 text-sm text-terminal-muted">
        No vision analysis yet. Use Live Market Analyze (auto-capture) or Upload Chart Image mode.
      </div>
    );
  }
  return (
    <div className="space-y-2 rounded-lg border border-terminal-border bg-terminal-panel p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
          Vision observations
        </h3>
        <span className="rounded border border-terminal-border px-2 py-0.5 text-[10px] uppercase">
          {vision.status}
        </span>
      </div>
      <p className="text-[10px] uppercase tracking-wide text-amber-200/90">
        SCREENSHOT OBSERVATION — not live market data
      </p>
      {vision.message ? <p className="text-[11px] text-amber-200">{vision.message}</p> : null}
      <div className="grid grid-cols-2 gap-2 text-[11px] text-terminal-muted">
        <div>Detected TF {vision.detected_timeframe ?? "—"}</div>
        <div>Detected symbol {vision.detected_symbol ?? "—"}</div>
        <div>Chart type {vision.detected_chart_type ?? "—"}</div>
        <div>
          Image{" "}
          {vision.image_metadata
            ? `${vision.image_metadata.width}×${vision.image_metadata.height}`
            : "—"}
        </div>
      </div>
      <Section title="Observations">
        {vision.observations.length ? (
          <ul className="space-y-1">
            {vision.observations.map((o) => (
              <li key={o.observation_id} className="border-b border-terminal-border/30 py-1">
                <span className="font-mono text-[10px] text-terminal-muted">{o.category}</span>{" "}
                <span className="text-[10px] text-terminal-muted">
                  ({(o.confidence * 100).toFixed(0)}%)
                </span>
                <div>{o.description}</div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-terminal-muted">No observations.</p>
        )}
      </Section>
      <Section title="Limitations" defaultOpen={false}>
        <List items={vision.limitations} />
      </Section>
      <Section title="Unreadable fields" defaultOpen={false}>
        <List items={vision.unreadable_fields} />
      </Section>
    </div>
  );
}

export function VisionComparisonPanel({
  comparison,
}: {
  comparison: VisionComparisonSummary | null | undefined;
}) {
  if (!comparison) {
    return (
      <div className="rounded-lg border border-terminal-border bg-terminal-panel p-3 text-sm text-terminal-muted">
        Run Analyze + Vision to compare screenshot observations with live analysis.
      </div>
    );
  }
  return (
    <div className="space-y-2 rounded-lg border border-terminal-border bg-terminal-panel p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
          Vision vs live comparison
        </h3>
        <span className="rounded border border-terminal-border px-2 py-0.5 text-[10px] uppercase">
          {comparison.status}
        </span>
      </div>
      <p className="text-[10px] text-terminal-muted">
        Visual disagreement does not change the deterministic decision.
      </p>
      <Section title="Notes">
        <List items={comparison.notes} />
      </Section>
      <Section title="Disagreements">
        <List items={comparison.disagreements} />
      </Section>
    </div>
  );
}
