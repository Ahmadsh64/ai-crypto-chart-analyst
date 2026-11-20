"use client";

import { useConfluence } from "@/hooks/use-market-data";
import { useLiveConfluenceSubscription } from "@/hooks/use-market-socket";
import { confluenceKey, useLiveMarketStore } from "@/stores/live-market-store";
import {
  assessmentLabel,
  assessmentTone,
  categoryLabel,
} from "@/lib/confluence-display";
import { cn } from "@/utils/cn";
import type { ExchangeId, MarketType } from "@/types/api";

interface ConfluencePanelProps {
  exchange: ExchangeId;
  marketType: MarketType;
  symbol: string;
}

export function ConfluencePanel({ exchange, marketType, symbol }: ConfluencePanelProps) {
  useLiveConfluenceSubscription(exchange, marketType, symbol, true);
  const query = useConfluence({ exchange, marketType, symbol });
  const live = useLiveMarketStore(
    (s) => s.confluence[confluenceKey(exchange, marketType, symbol)],
  );

  const bullish = live?.bullishScore ?? query.data?.bullish_score;
  const bearish = live?.bearishScore ?? query.data?.bearish_score;
  const categories = live?.categoryScores ?? query.data?.category_scores ?? [];
  const evidence = live?.evidence ?? query.data?.evidence ?? [];
  const conflicts = live?.conflicts ?? query.data?.conflicts ?? [];
  const assessment =
    live?.preliminaryAssessment ?? query.data?.preliminary_assessment;
  const strength = live?.assessmentStrength ?? query.data?.assessment_strength ?? "none";
  const quality = live?.dataQuality ?? query.data?.data_quality;
  const summary = live?.summary ?? query.data?.summary;
  const version = live?.configurationVersion ?? query.data?.configuration_version;
  const source = live ? "live" : query.isLoading ? "loading" : "rest";

  return (
    <div className="space-y-3 rounded-lg border border-terminal-border bg-terminal-panel p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
            Confluence
          </h3>
          <p className="mt-1 text-[11px] text-terminal-muted">
            {source === "loading"
              ? "Loading…"
              : source === "live"
                ? "Live · confirmed candles"
                : "REST seed"}
            {version ? ` · ${version}` : ""}
          </p>
        </div>
        <span
          className={cn(
            "rounded border px-2 py-0.5 text-[10px] uppercase tracking-wide",
            assessmentTone(assessment),
          )}
        >
          {assessmentLabel(assessment)}
          {strength !== "none" ? ` · ${strength}` : ""}
        </span>
      </div>

      {query.isError ? (
        <p className="text-[11px] text-terminal-short">
          {(query.error as Error).message || "Confluence error"}
        </p>
      ) : null}

      <div className="grid grid-cols-2 gap-2">
        <ScoreCard label="Bullish score" value={bullish} tone="bull" />
        <ScoreCard label="Bearish score" value={bearish} tone="bear" />
      </div>

      <p className="text-[10px] text-terminal-muted">
        Scores are weighted evidence contributions (0–100), not win probabilities.
      </p>

      <div className="space-y-1.5">
        <p className="text-[10px] uppercase tracking-wide text-terminal-muted">
          Category contributions
        </p>
        {categories.map((c) => (
          <div key={c.category} className="space-y-0.5">
            <div className="flex justify-between text-[10px] text-terminal-muted">
              <span>{categoryLabel(c.category)}</span>
              <span className="font-mono">
                B {c.bullish_contribution.toFixed(1)} / S {c.bearish_contribution.toFixed(1)} · w
                {c.weight}
              </span>
            </div>
            <div className="flex h-1.5 overflow-hidden rounded bg-terminal-surface">
              <div
                className="bg-terminal-long/70"
                style={{ width: `${Math.min(100, (c.bullish_contribution / c.weight) * 50)}%` }}
              />
              <div
                className="bg-terminal-short/70"
                style={{ width: `${Math.min(100, (c.bearish_contribution / c.weight) * 50)}%` }}
              />
            </div>
          </div>
        ))}
        {!categories.length ? (
          <p className="text-[11px] text-terminal-muted">No category scores yet.</p>
        ) : null}
      </div>

      <div className="space-y-1 border-t border-terminal-border/60 pt-2">
        <p className="text-[10px] uppercase tracking-wide text-terminal-muted">Evidence</p>
        <ul className="max-h-40 space-y-1 overflow-y-auto text-[11px]">
          {evidence.slice(0, 12).map((e) => (
            <li key={e.evidence_id} className="text-terminal-text">
              <span className="font-mono text-terminal-muted">
                {e.timeframe} · {e.direction}
              </span>{" "}
              {e.explanation}
            </li>
          ))}
          {!evidence.length ? (
            <li className="text-terminal-muted">No confirmed evidence.</li>
          ) : null}
        </ul>
      </div>

      <div className="space-y-1 border-t border-terminal-border/60 pt-2">
        <p className="text-[10px] uppercase tracking-wide text-terminal-muted">Conflicts</p>
        {conflicts.length ? (
          <ul className="space-y-1 text-[11px]">
            {conflicts.map((c, i) => (
              <li key={`${c.conflict_type}-${i}`} className="text-amber-300/90">
                <span className="uppercase text-[10px] text-terminal-muted">
                  {c.severity}
                </span>{" "}
                {c.description}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[11px] text-terminal-muted">No conflicts detected.</p>
        )}
      </div>

      {quality ? (
        <div className="border-t border-terminal-border/60 pt-2 text-[10px] text-terminal-muted">
          <p>
            Data quality: <span className="font-mono text-terminal-text">{quality.overall}</span>
            {quality.is_analysis_complete ? " · complete" : " · incomplete"}
          </p>
          {quality.limitations?.length ? (
            <p className="mt-1 line-clamp-2">{quality.limitations.join(" · ")}</p>
          ) : null}
        </div>
      ) : null}

      {summary ? (
        <p className="border-t border-terminal-border/60 pt-2 text-[11px] leading-relaxed text-terminal-text">
          {summary}
        </p>
      ) : null}
    </div>
  );
}

function ScoreCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | undefined;
  tone: "bull" | "bear";
}) {
  return (
    <div className="rounded border border-terminal-border/70 bg-terminal-surface/40 px-2 py-2">
      <p className="text-[10px] uppercase tracking-wide text-terminal-muted">{label}</p>
      <p
        className={cn(
          "mt-1 font-mono text-xl font-semibold",
          tone === "bull" ? "text-terminal-long" : "text-terminal-short",
        )}
      >
        {value != null ? value.toFixed(1) : "—"}
      </p>
    </div>
  );
}
