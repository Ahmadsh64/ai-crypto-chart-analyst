"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronsUpDown, Loader2 } from "lucide-react";
import type { TradingPair } from "@/types/api";
import { cn } from "@/utils/cn";
import { filterTradingPairs, PAGE_SIZE } from "@/lib/market-symbol-search";

interface SymbolSearchSelectProps {
  pairs: TradingPair[];
  value: string;
  onChange: (symbol: string) => void;
  loading?: boolean;
  error?: string | null;
  disabled?: boolean;
}

export function SymbolSearchSelect({
  pairs,
  value,
  onChange,
  loading = false,
  error = null,
  disabled = false,
}: SymbolSearchSelectProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(query.trim()), 200);
    return () => window.clearTimeout(id);
  }, [query]);

  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [debounced, pairs]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const filtered = useMemo(
    () => filterTradingPairs(pairs, debounced),
    [pairs, debounced],
  );
  const visible = filtered.slice(0, visibleCount);
  const selected = pairs.find((p) => p.symbol === value) ?? null;

  const onScroll = () => {
    const el = listRef.current;
    if (!el) return;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 24) {
      setVisibleCount((n) => Math.min(n + PAGE_SIZE, filtered.length));
    }
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex h-10 w-full items-center justify-between rounded-md border border-terminal-border bg-terminal-surface px-3 text-left text-sm text-terminal-text outline-none focus:border-terminal-accent",
          disabled && "opacity-50",
        )}
        aria-expanded={open}
        aria-haspopup="listbox"
      >
        <span className="truncate">
          {selected ? selected.symbol : value || "Select symbol"}
          {selected ? (
            <span className="ml-2 text-[11px] text-terminal-muted">
              {selected.base}/{selected.quote}
            </span>
          ) : null}
        </span>
        {loading ? (
          <Loader2 className="h-4 w-4 shrink-0 animate-spin text-terminal-muted" />
        ) : (
          <ChevronsUpDown className="h-4 w-4 shrink-0 text-terminal-muted" />
        )}
      </button>

      {open ? (
        <div className="absolute z-30 mt-1 w-full overflow-hidden rounded-md border border-terminal-border bg-terminal-panel shadow-lg">
          <div className="border-b border-terminal-border p-2">
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search BTC, USDT, BTCUSDT…"
              className="h-9 w-full rounded-md border border-terminal-border bg-terminal-bg px-3 text-sm text-terminal-text outline-none focus:border-terminal-accent"
            />
          </div>
          <div
            ref={listRef}
            onScroll={onScroll}
            role="listbox"
            className="max-h-64 overflow-y-auto"
          >
            {visible.length === 0 ? (
              <p className="px-3 py-4 text-sm text-terminal-muted">
                {loading ? "Loading markets…" : "No matching active pairs."}
              </p>
            ) : (
              visible.map((pair) => {
                const active = pair.symbol === value;
                return (
                  <button
                    key={`${pair.exchange}:${pair.market_type}:${pair.native_symbol}`}
                    type="button"
                    role="option"
                    aria-selected={active}
                    onClick={() => {
                      onChange(pair.symbol);
                      setOpen(false);
                      setQuery("");
                    }}
                    className={cn(
                      "flex w-full flex-col gap-0.5 px-3 py-2 text-left text-sm hover:bg-terminal-surface",
                      active && "bg-terminal-accent/10",
                    )}
                  >
                    <span className="font-medium text-terminal-text">{pair.symbol}</span>
                    <span className="text-[11px] text-terminal-muted">
                      {pair.exchange} · {pair.market_type.replaceAll("_", " ")} ·{" "}
                      {pair.native_symbol}
                      {pair.active === false ? " · inactive" : " · active"}
                    </span>
                  </button>
                );
              })
            )}
          </div>
          <div className="border-t border-terminal-border px-3 py-1.5 text-[10px] text-terminal-muted">
            Showing {visible.length} of {filtered.length}
            {filtered.length !== pairs.length ? ` (filtered from ${pairs.length})` : ""}
          </div>
        </div>
      ) : null}

      {error ? <p className="mt-1 text-[11px] text-terminal-short">{error}</p> : null}
    </div>
  );
}
