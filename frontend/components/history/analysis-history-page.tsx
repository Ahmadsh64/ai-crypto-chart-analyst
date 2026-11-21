"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { History, RefreshCw, X } from "lucide-react";
import { api } from "@/services/api";
import type {
  AnalysisHistoryDetail,
  AnalysisHistoryListItem,
  FinalDecision,
} from "@/types/api";
import { decisionTone } from "@/lib/decision-display";
import {
  HISTORY_DECISION_OPTIONS,
  HISTORY_PAGE_SIZE,
  consistencyLabel,
  consistencyTone,
  extractPlannedLevels,
  formatHistoryTimestamp,
  hasAnyPlannedLevel,
  historyErrorMessage,
  historyPageCount,
  isIncompleteConsistency,
} from "@/lib/history-display";
import { cn } from "@/utils/cn";

export function AnalysisHistoryPage() {
  const [symbol, setSymbol] = useState("");
  const [decision, setDecision] = useState<FinalDecision | "">("");
  const [appliedSymbol, setAppliedSymbol] = useState("");
  const [appliedDecision, setAppliedDecision] = useState<FinalDecision | "">("");
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<AnalysisHistoryListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AnalysisHistoryDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const listAbortRef = useRef<AbortController | null>(null);
  const detailAbortRef = useRef<AbortController | null>(null);
  const listSeqRef = useRef(0);
  const detailSeqRef = useRef(0);

  const loadList = useCallback(async () => {
    listAbortRef.current?.abort();
    const ac = new AbortController();
    listAbortRef.current = ac;
    const seq = ++listSeqRef.current;
    setLoading(true);
    setError(null);
    try {
      const res = await api.historyAnalyses(
        {
          limit: HISTORY_PAGE_SIZE,
          offset,
          symbol: appliedSymbol || undefined,
          decision: appliedDecision || undefined,
        },
        ac.signal,
      );
      if (seq !== listSeqRef.current) return;
      setItems(res.items);
      setTotal(res.total);
    } catch (err) {
      if (ac.signal.aborted) return;
      if (seq !== listSeqRef.current) return;
      setItems([]);
      setTotal(0);
      setError(historyErrorMessage(err));
    } finally {
      if (seq === listSeqRef.current) setLoading(false);
    }
  }, [offset, appliedSymbol, appliedDecision]);

  useEffect(() => {
    void loadList();
    return () => listAbortRef.current?.abort();
  }, [loadList]);

  const openDetail = useCallback(async (runId: string) => {
    setSelectedRunId(runId);
    setDetail(null);
    setDetailError(null);
    detailAbortRef.current?.abort();
    const ac = new AbortController();
    detailAbortRef.current = ac;
    const seq = ++detailSeqRef.current;
    setDetailLoading(true);
    try {
      const res = await api.historyAnalysisByRun(runId, ac.signal);
      if (seq !== detailSeqRef.current) return;
      setDetail(res);
    } catch (err) {
      if (ac.signal.aborted) return;
      if (seq !== detailSeqRef.current) return;
      setDetailError(historyErrorMessage(err));
    } finally {
      if (seq === detailSeqRef.current) setDetailLoading(false);
    }
  }, []);

  const closeDetail = () => {
    detailAbortRef.current?.abort();
    setSelectedRunId(null);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(false);
  };

  const applyFilters = (e: FormEvent) => {
    e.preventDefault();
    setOffset(0);
    setAppliedSymbol(symbol.trim().toUpperCase());
    setAppliedDecision(decision);
  };

  const clearFilters = () => {
    setSymbol("");
    setDecision("");
    setAppliedSymbol("");
    setAppliedDecision("");
    setOffset(0);
  };

  const pageSize = HISTORY_PAGE_SIZE;
  const pages = historyPageCount(total, pageSize);
  const currentPage = Math.floor(offset / pageSize) + 1;
  const canPrev = offset > 0;
  const canNext = offset + pageSize < total;

  const levels = detail ? extractPlannedLevels(detail) : null;

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 p-4 md:p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-md bg-terminal-surface text-terminal-accent">
            <History className="h-5 w-5" strokeWidth={1.75} />
          </div>
          <div>
            <h1 className="font-display text-xl font-semibold text-terminal-text">
              Analysis History
            </h1>
            <p className="mt-1 max-w-2xl text-sm text-terminal-muted">
              Read-only records from saved Analyze runs. Values are frozen at
              analysis time — not live market prices or exchange fills.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => void loadList()}
          className="inline-flex items-center gap-2 rounded-md border border-terminal-border bg-terminal-surface px-3 py-2 text-sm text-terminal-text hover:border-terminal-accent/50"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
          Refresh
        </button>
      </header>

      <form
        onSubmit={applyFilters}
        className="flex flex-wrap items-end gap-3 rounded-md border border-terminal-border bg-terminal-panel p-3"
      >
        <label className="flex min-w-[10rem] flex-col gap-1 text-[11px] uppercase tracking-wide text-terminal-muted">
          Symbol
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder="BTC/USDT"
            className="rounded-md border border-terminal-border bg-terminal-bg px-3 py-2 text-sm normal-case tracking-normal text-terminal-text outline-none focus:border-terminal-accent"
          />
        </label>
        <label className="flex min-w-[10rem] flex-col gap-1 text-[11px] uppercase tracking-wide text-terminal-muted">
          Decision
          <select
            value={decision}
            onChange={(e) => setDecision(e.target.value as FinalDecision | "")}
            className="rounded-md border border-terminal-border bg-terminal-bg px-3 py-2 text-sm normal-case tracking-normal text-terminal-text outline-none focus:border-terminal-accent"
          >
            {HISTORY_DECISION_OPTIONS.map((opt) => (
              <option key={opt || "all"} value={opt}>
                {opt || "All"}
              </option>
            ))}
          </select>
        </label>
        <button
          type="submit"
          className="rounded-md bg-terminal-accent/90 px-3 py-2 text-sm font-medium text-terminal-bg hover:bg-terminal-accent"
        >
          Apply
        </button>
        <button
          type="button"
          onClick={clearFilters}
          className="rounded-md border border-terminal-border px-3 py-2 text-sm text-terminal-muted hover:text-terminal-text"
        >
          Clear
        </button>
      </form>

      <div className="min-h-0 flex-1 overflow-hidden rounded-md border border-terminal-border bg-terminal-panel">
        {loading && items.length === 0 ? (
          <div className="flex h-48 items-center justify-center text-sm text-terminal-muted">
            Loading history…
          </div>
        ) : error ? (
          <div className="flex h-48 flex-col items-center justify-center gap-3 px-4 text-center">
            <p className="text-sm text-terminal-short">{error}</p>
            {error.includes("503") ||
            error.includes("UNAVAILABLE") ||
            error.includes("DISABLED") ||
            error.toLowerCase().includes("unavailable") ||
            error.toLowerCase().includes("disabled") ? (
              <p className="max-w-md text-xs text-terminal-muted">
                Persistence may be disabled or the database is unreachable. This
                does not mean there is no history — retry when the service is
                available.
              </p>
            ) : null}
            <button
              type="button"
              onClick={() => void loadList()}
              className="rounded-md border border-terminal-border px-3 py-1.5 text-sm text-terminal-text hover:border-terminal-accent/50"
            >
              Retry
            </button>
          </div>
        ) : items.length === 0 ? (
          <div className="flex h-48 flex-col items-center justify-center gap-2 px-4 text-center">
            <p className="text-sm text-terminal-text">No saved analyses yet.</p>
            <p className="max-w-md text-xs text-terminal-muted">
              Run Analyze on the AI Market Analyzer page with persistence enabled to
              populate history.
            </p>
          </div>
        ) : (
          <div className="h-full overflow-auto">
            <table className="w-full min-w-[720px] border-collapse text-left text-sm">
              <thead className="sticky top-0 bg-terminal-surface text-[11px] uppercase tracking-wide text-terminal-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">Symbol</th>
                  <th className="px-3 py-2 font-medium">Exchange</th>
                  <th className="px-3 py-2 font-medium">TF</th>
                  <th className="px-3 py-2 font-medium">Timestamp</th>
                  <th className="px-3 py-2 font-medium">Decision</th>
                  <th className="px-3 py-2 font-medium">Consistency</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => {
                  const active = selectedRunId === row.analysis_run_id;
                  return (
                    <tr
                      key={row.analysis_run_id}
                      onClick={() => void openDetail(row.analysis_run_id)}
                      className={cn(
                        "cursor-pointer border-t border-terminal-border/80 transition-colors",
                        active
                          ? "bg-terminal-accent/10"
                          : "hover:bg-terminal-surface/70",
                      )}
                    >
                      <td className="px-3 py-2.5 font-medium text-terminal-text">
                        {row.symbol}
                      </td>
                      <td className="px-3 py-2.5 capitalize text-terminal-muted">
                        {row.exchange} · {row.market_type.replaceAll("_", " ")}
                      </td>
                      <td className="px-3 py-2.5 text-terminal-muted">
                        {row.timeframe ?? "—"}
                      </td>
                      <td className="px-3 py-2.5 text-terminal-muted">
                        {formatHistoryTimestamp(row.analysis_timestamp)}
                      </td>
                      <td className="px-3 py-2.5">
                        <span
                          className={cn(
                            "inline-flex rounded border px-2 py-0.5 text-xs",
                            decisionTone(row.decision as FinalDecision),
                          )}
                        >
                          {row.decision}
                        </span>
                      </td>
                      <td className="px-3 py-2.5">
                        <span
                          className={cn(
                            "inline-flex rounded border px-2 py-0.5 text-xs",
                            consistencyTone(row.consistency_status),
                          )}
                        >
                          {consistencyLabel(row.consistency_status)}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {!error && total > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-terminal-muted">
          <span>
            {total} record{total === 1 ? "" : "s"} · page {currentPage} of {pages}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={!canPrev}
              onClick={() => setOffset(Math.max(0, offset - pageSize))}
              className="rounded-md border border-terminal-border px-3 py-1.5 disabled:opacity-40"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={!canNext}
              onClick={() => setOffset(offset + pageSize)}
              className="rounded-md border border-terminal-border px-3 py-1.5 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      ) : null}

      {selectedRunId ? (
        <div className="fixed inset-0 z-40 flex justify-end bg-black/50">
          <aside className="flex h-full w-full max-w-lg flex-col border-l border-terminal-border bg-terminal-panel shadow-xl">
            <div className="flex items-center justify-between border-b border-terminal-border px-4 py-3">
              <div>
                <p className="text-[11px] uppercase tracking-wide text-terminal-muted">
                  Analysis detail
                </p>
                <p className="font-mono text-xs text-terminal-text">{selectedRunId}</p>
              </div>
              <button
                type="button"
                onClick={closeDetail}
                className="rounded-md p-1.5 text-terminal-muted hover:bg-terminal-surface hover:text-terminal-text"
                aria-label="Close detail"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              {detailLoading ? (
                <p className="text-sm text-terminal-muted">Loading detail…</p>
              ) : detailError ? (
                <div className="space-y-3">
                  <p className="text-sm text-terminal-short">{detailError}</p>
                  <button
                    type="button"
                    onClick={() => void openDetail(selectedRunId)}
                    className="rounded-md border border-terminal-border px-3 py-1.5 text-sm"
                  >
                    Retry
                  </button>
                </div>
              ) : detail ? (
                <div className="space-y-5">
                  {isIncompleteConsistency(detail.consistency_status) ? (
                    <div className="rounded-md border border-amber-400/40 bg-amber-400/5 px-3 py-2 text-xs text-amber-100">
                      Record status: {consistencyLabel(detail.consistency_status)}.
                      Original stored payloads are shown without merging or
                      recomputation.
                    </div>
                  ) : null}

                  <section className="space-y-2">
                    <h2 className="text-[11px] uppercase tracking-wide text-terminal-muted">
                      Session
                    </h2>
                    <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
                      <div>
                        <dt className="text-terminal-muted">Symbol</dt>
                        <dd className="text-terminal-text">{detail.symbol}</dd>
                      </div>
                      <div>
                        <dt className="text-terminal-muted">Exchange</dt>
                        <dd className="capitalize text-terminal-text">
                          {detail.exchange} / {detail.market_type}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-terminal-muted">Timeframe</dt>
                        <dd className="text-terminal-text">{detail.timeframe ?? "—"}</dd>
                      </div>
                      <div>
                        <dt className="text-terminal-muted">Analyzed at</dt>
                        <dd className="text-terminal-text">
                          {formatHistoryTimestamp(detail.analysis_timestamp)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-terminal-muted">Decision</dt>
                        <dd>
                          <span
                            className={cn(
                              "inline-flex rounded border px-2 py-0.5 text-xs",
                              decisionTone(detail.decision as FinalDecision),
                            )}
                          >
                            {detail.decision}
                          </span>
                        </dd>
                      </div>
                      <div>
                        <dt className="text-terminal-muted">Consistency</dt>
                        <dd>
                          <span
                            className={cn(
                              "inline-flex rounded border px-2 py-0.5 text-xs",
                              consistencyTone(detail.consistency_status),
                            )}
                          >
                            {consistencyLabel(detail.consistency_status)}
                          </span>
                        </dd>
                      </div>
                    </dl>
                  </section>

                  <section className="space-y-2">
                    <h2 className="text-[11px] uppercase tracking-wide text-terminal-muted">
                      Planned levels (analytical — not fills)
                    </h2>
                    {levels && hasAnyPlannedLevel(levels) ? (
                      <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
                        {levels.entry ? (
                          <div>
                            <dt className="text-terminal-muted">Entry (ref)</dt>
                            <dd className="font-mono text-terminal-text">{levels.entry}</dd>
                          </div>
                        ) : null}
                        {levels.entryLow || levels.entryHigh ? (
                          <div>
                            <dt className="text-terminal-muted">Entry zone</dt>
                            <dd className="font-mono text-terminal-text">
                              {levels.entryLow ?? "—"} – {levels.entryHigh ?? "—"}
                            </dd>
                          </div>
                        ) : null}
                        {levels.stopLoss ? (
                          <div>
                            <dt className="text-terminal-muted">Stop loss</dt>
                            <dd className="font-mono text-terminal-text">
                              {levels.stopLoss}
                            </dd>
                          </div>
                        ) : null}
                        {levels.takeProfits.map((tp, i) => (
                          <div key={`tp-${i}`}>
                            <dt className="text-terminal-muted">TP{i + 1}</dt>
                            <dd className="font-mono text-terminal-text">{tp}</dd>
                          </div>
                        ))}
                        {levels.primaryRr ? (
                          <div>
                            <dt className="text-terminal-muted">Primary R:R</dt>
                            <dd className="font-mono text-terminal-text">
                              {levels.primaryRr}
                            </dd>
                          </div>
                        ) : null}
                      </dl>
                    ) : (
                      <p className="text-sm text-terminal-muted">
                        No planned Entry/SL/TP stored for this run.
                      </p>
                    )}
                    <p className="text-[11px] text-terminal-muted">
                      {levels?.note}
                    </p>
                    <p className="text-[11px] text-terminal-muted">
                      Actual fills are not recorded in Analysis History. This
                      surface shows planned Analyze levels only.
                    </p>
                  </section>

                  <section className="space-y-2">
                    <h2 className="text-[11px] uppercase tracking-wide text-terminal-muted">
                      Provenance
                    </h2>
                    <dl className="space-y-1 text-xs text-terminal-muted">
                      <div>
                        Decision ts:{" "}
                        {formatHistoryTimestamp(detail.decision_analysis_timestamp)}
                      </div>
                      <div>
                        Trade plan ts:{" "}
                        {formatHistoryTimestamp(detail.trade_plan_analysis_timestamp)}
                      </div>
                      <div>Decision id: {detail.decision_id ?? "—"}</div>
                      <div>Plan id: {detail.plan_id ?? "—"}</div>
                      <div className="break-all">Hash: {detail.content_hash}</div>
                    </dl>
                  </section>
                </div>
              ) : null}
            </div>
          </aside>
        </div>
      ) : null}

    </div>
  );
}
