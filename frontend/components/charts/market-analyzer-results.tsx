"use client";

import { cn } from "@/utils/cn";
import { decisionTone } from "@/lib/decision-display";
import type {
  AiAnalyzeResponse,
  AnalysisSnapshot,
  DecisionResponse,
  FinalDecision,
  PriceComparisonSummary,
  ScreenshotRecognitionSummary,
  TradePlanResponse,
  VisionResult,
} from "@/types/api";
import { formatConfidence, formatDiscrepancyPct } from "@/lib/chart-recognition";

function Panel({
  title,
  children,
  badge,
}: {
  title: string;
  children: React.ReactNode;
  badge?: string;
}) {
  return (
    <div className="rounded-lg border border-terminal-border bg-terminal-panel p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">{title}</h3>
        {badge ? (
          <span className="rounded border border-terminal-border px-1.5 py-0.5 text-[10px] text-terminal-muted">
            {badge}
          </span>
        ) : null}
      </div>
      <div className="mt-2 space-y-2 text-sm text-terminal-text">{children}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3 text-xs">
      <span className="text-terminal-muted">{label}</span>
      <span className="text-right font-mono text-terminal-text">{value ?? "—"}</span>
    </div>
  );
}

function fmt(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return String(n);
}

export function MarketOverviewPanel({
  result,
  snapshot,
}: {
  result: AiAnalyzeResponse | null;
  snapshot: AnalysisSnapshot | null;
}) {
  if (!result && !snapshot) return null;
  const decision = result?.decision;
  const price = decision?.data_quality?.current_price ?? null;
  return (
    <Panel title="Market Overview" badge="Deterministic">
      <div className="grid gap-1.5 sm:grid-cols-2">
        <Row label="Exchange" value={result?.exchange ?? snapshot?.exchange} />
        <Row
          label="Market"
          value={(result?.market_type ?? snapshot?.market_type)?.replaceAll("_", " ")}
        />
        <Row label="Symbol" value={result?.symbol ?? snapshot?.symbol} />
        <Row label="Timeframe" value={result?.timeframe ?? "—"} />
        <Row label="Current price" value={fmt(price)} />
        <Row
          label="Analysis time"
          value={
            result?.decision?.analysis_timestamp ||
            snapshot?.analysis_timestamp ||
            "—"
          }
        />
        <Row label="Freshness" value={snapshot?.data_freshness ?? "—"} />
        <Row
          label="Trend / assessment"
          value={
            decision?.confluence_scores?.preliminary_assessment ??
            snapshot?.preliminary_assessment ??
            "—"
          }
        />
      </div>
    </Panel>
  );
}

export function StructuredDecisionPanel({
  decision,
  snapshot,
}: {
  decision?: DecisionResponse | null;
  snapshot?: AnalysisSnapshot | null;
}) {
  const d = (decision?.decision ?? snapshot?.decision) as FinalDecision | undefined;
  if (!d) return null;
  return (
    <Panel title="Decision" badge="Deterministic engine">
      <span
        className={cn(
          "inline-flex rounded border px-2 py-0.5 text-xs font-medium",
          decisionTone(d),
        )}
      >
        {d}
      </span>
      <p className="text-xs text-terminal-muted">
        {decision?.decision_reason ?? snapshot?.decision_reason ?? "—"}
      </p>
      <p className="text-[10px] text-terminal-muted">
        Decision comes only from the deterministic Decision Engine — never from AI text.
      </p>
    </Panel>
  );
}

export function StructuredLevelsPanel({
  decision,
  tradePlan,
  snapshot,
}: {
  decision?: DecisionResponse | null;
  tradePlan?: TradePlanResponse | null;
  snapshot?: AnalysisSnapshot | null;
}) {
  if (!decision && !tradePlan && !snapshot) return null;

  const entry = tradePlan?.entry;
  const sl = tradePlan?.stop_loss;
  const tps = tradePlan?.take_profit_targets ?? [];
  const entryRef =
    entry?.entry_reference_price ??
    snapshot?.entry_reference_price ??
    (typeof decision?.entry_zone_summary?.entry_reference_price === "number"
      ? decision.entry_zone_summary.entry_reference_price
      : null);
  const entryLow =
    entry?.entry_low ??
    snapshot?.entry_low ??
    (typeof decision?.entry_zone_summary?.entry_low === "number"
      ? decision.entry_zone_summary.entry_low
      : null);
  const entryHigh =
    entry?.entry_high ??
    snapshot?.entry_high ??
    (typeof decision?.entry_zone_summary?.entry_high === "number"
      ? decision.entry_zone_summary.entry_high
      : null);
  const stop =
    sl?.stop_loss_price ?? snapshot?.stop_loss_price ?? decision?.stop_loss_price ?? null;
  const snapTps = snapshot?.take_profit_prices ?? decision?.take_profit_prices ?? [];

  const hasZone =
    entryLow != null &&
    entryHigh != null &&
    entryLow !== entryHigh;

  return (
    <Panel title="Planned levels" badge="Analytical — not fills">
      <div className="space-y-3">
        <div>
          <p className="mb-1 text-[10px] uppercase tracking-wide text-terminal-muted">
            Entry zone
          </p>
          {hasZone ? (
            <>
              <Row label="Lower" value={fmt(entryLow)} />
              <Row label="Upper" value={fmt(entryHigh)} />
              <Row label="Reference" value={fmt(entryRef)} />
            </>
          ) : entryRef != null ? (
            <Row label="Reference entry" value={fmt(entryRef)} />
          ) : (
            <p className="text-xs text-terminal-muted">No entry level in this plan.</p>
          )}
          <Row
            label="Entry status"
            value={
              decision?.entry_confirmation?.status ??
              (entry?.price_inside_zone ? "inside_zone" : tradePlan?.plan_status) ??
              "—"
            }
          />
        </div>

        <div>
          <p className="mb-1 text-[10px] uppercase tracking-wide text-terminal-muted">
            Stop loss
          </p>
          {stop != null ? (
            <>
              <Row label="SL price" value={fmt(stop)} />
              {sl ? (
                <>
                  <Row label="Risk distance" value={fmt(sl.stop_loss_distance)} />
                  <p className="text-[11px] text-terminal-muted">
                    {sl.invalidation_explanation || "—"}
                  </p>
                </>
              ) : null}
            </>
          ) : (
            <p className="text-xs text-terminal-muted">No stop loss stored.</p>
          )}
        </div>

        <div>
          <p className="mb-1 text-[10px] uppercase tracking-wide text-terminal-muted">
            Take profit
          </p>
          {tps.length > 0
            ? tps.map((tp) => (
                <div key={tp.index} className="mb-1">
                  <Row
                    label={tp.label || `TP${tp.index}`}
                    value={`${fmt(tp.price)} · R:R ${fmt(tp.risk_reward_ratio)}`}
                  />
                </div>
              ))
            : snapTps.length > 0
              ? snapTps.map((price, i) => (
                  <Row key={`tp-${i}`} label={`TP${i + 1}`} value={fmt(price)} />
                ))
              : (
                <p className="text-xs text-terminal-muted">No take-profit targets stored.</p>
              )}
          <Row
            label="Primary R:R"
            value={fmt(tradePlan?.risk?.primary_rr ?? snapshot?.primary_rr ?? decision?.primary_rr)}
          />
        </div>

        <div>
          <p className="mb-1 text-[10px] uppercase tracking-wide text-terminal-muted">
            Exit zone
          </p>
          {tps.length > 0 || snapTps.length > 0 ? (
            <p className="text-xs text-terminal-muted">
              Planned exit levels are the Take Profit targets above. This platform does not
              record actual exchange fills.
            </p>
          ) : (
            <p className="text-xs text-terminal-muted">
              No planned exit zone available for this decision.
            </p>
          )}
        </div>
      </div>
    </Panel>
  );
}

export function SmcEvidencePanel({
  decision,
  snapshot,
}: {
  decision?: DecisionResponse | null;
  snapshot?: AnalysisSnapshot | null;
}) {
  const evidence = decision?.supporting_evidence ?? snapshot?.supporting_evidence ?? [];
  const blocking = decision?.blocking_conditions ?? snapshot?.blocking_conditions ?? [];
  const conflicts = decision?.conflict_ids ?? snapshot?.conflicts ?? [];
  if (!evidence.length && !blocking.length && !conflicts.length) return null;
  return (
    <Panel title="SMC / ICT evidence" badge="Engine sourced">
      {evidence.length ? (
        <ul className="max-h-40 space-y-1 overflow-y-auto text-xs">
          {evidence.map((item, i) => (
            <li key={`e-${i}`} className="border-b border-terminal-border/40 py-1">
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-terminal-muted">No supporting evidence listed.</p>
      )}
      {blocking.length ? (
        <div>
          <p className="mb-1 text-[10px] uppercase text-terminal-muted">Blocking</p>
          <ul className="space-y-1 text-xs text-amber-200">
            {blocking.map((item, i) => (
              <li key={`b-${i}`}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <p className="text-[10px] text-terminal-muted">
        Structure / liquidity / OB-FVG details remain on the live chart overlays. AI Vision
        cannot invent SMC events without engine evidence.
      </p>
    </Panel>
  );
}

export function ScreenshotRecognitionResultsPanel({
  recognition,
  vision,
}: {
  recognition?: ScreenshotRecognitionSummary | null;
  vision?: VisionResult | null;
}) {
  if (!recognition && !vision) return null;
  return (
    <Panel title="Screenshot recognition / OCR" badge="Visual estimate">
      <div className="grid gap-1.5 sm:grid-cols-2">
        <Row
          label="Identified symbol"
          value={recognition?.detected_symbol ?? vision?.detected_symbol ?? "unavailable"}
        />
        <Row
          label="Symbol confidence"
          value={formatConfidence(
            recognition?.symbol_confidence ?? vision?.symbol_confidence,
          )}
        />
        <Row
          label="Screenshot timeframe"
          value={
            recognition?.detected_timeframe ?? vision?.detected_timeframe ?? "unavailable"
          }
        />
        <Row
          label="Timeframe confidence"
          value={formatConfidence(
            recognition?.timeframe_confidence ?? vision?.timeframe_confidence,
          )}
        />
        <Row
          label="Screenshot-observed price"
          value={
            recognition?.observed_last_price ??
            vision?.observed_last_price ??
            vision?.observed_price_label ??
            "unavailable"
          }
        />
        <Row
          label="Exchange / platform"
          value={
            [recognition?.detected_exchange ?? vision?.detected_exchange, recognition?.detected_platform ?? vision?.detected_platform]
              .filter(Boolean)
              .join(" · ") || "unavailable"
          }
        />
      </div>
      <p className="text-[10px] text-terminal-muted">
        {recognition?.disclaimer ??
          "Screenshot-observed fields are OCR/visual estimates only — not verified exchange data."}
      </p>
    </Panel>
  );
}

export function PriceComparisonPanel({
  comparison,
  analysisMode,
}: {
  comparison?: PriceComparisonSummary | null;
  analysisMode?: string | null;
}) {
  if (!comparison) return null;
  return (
    <Panel
      title="Screenshot vs verified price"
      badge={analysisMode === "UPLOADED_IMAGE" ? "Upload mode" : "Comparison"}
    >
      <div className="grid gap-1.5 sm:grid-cols-2">
        <Row
          label="Screenshot-observed"
          value={fmt(comparison.screenshot_observed_price)}
        />
        <Row label="Verified exchange" value={fmt(comparison.verified_last_price)} />
        <Row label="Verified timestamp" value={comparison.verified_price_timestamp ?? "—"} />
        <Row label="Verified source" value={comparison.verified_price_source ?? "—"} />
        <Row
          label="Discrepancy"
          value={formatDiscrepancyPct(comparison.discrepancy_pct)}
        />
      </div>
      <p className="text-[10px] text-terminal-muted">{comparison.note}</p>
    </Panel>
  );
}
