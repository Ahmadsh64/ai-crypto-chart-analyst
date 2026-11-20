"use client";

import { CandlestickChart } from "lucide-react";

interface ChartPlaceholderProps {
  title: string;
  subtitle: string;
}

/**
 * Phase 1 visual stand-in for TradingView Lightweight Charts.
 * Real OHLCV rendering arrives in Phase 2 with exchange adapters.
 */
export function ChartPlaceholder({ title, subtitle }: ChartPlaceholderProps) {
  return (
    <div className="flex h-64 flex-col rounded-lg border border-terminal-border bg-terminal-panel">
      <div className="flex items-center justify-between border-b border-terminal-border px-4 py-3">
        <div>
          <h3 className="text-sm font-medium text-terminal-text">{title}</h3>
          <p className="text-xs text-terminal-muted">{subtitle}</p>
        </div>
        <span className="rounded border border-terminal-border px-2 py-0.5 text-[10px] uppercase tracking-wider text-terminal-muted">
          Phase 2 live data
        </span>
      </div>
      <div className="relative flex flex-1 items-center justify-center overflow-hidden">
        <div
          aria-hidden
          className="absolute inset-0 opacity-40"
          style={{
            backgroundImage:
              "linear-gradient(rgba(34,197,94,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(34,197,94,0.06) 1px, transparent 1px)",
            backgroundSize: "32px 24px",
          }}
        />
        <svg
          className="absolute inset-x-6 bottom-8 top-8 w-[calc(100%-3rem)] opacity-70"
          viewBox="0 0 400 120"
          preserveAspectRatio="none"
          aria-hidden
        >
          <polyline
            fill="none"
            stroke="#22c55e"
            strokeWidth="1.5"
            points="0,80 40,72 80,90 120,60 160,68 200,40 240,55 280,30 320,45 360,22 400,35"
          />
          <polyline
            fill="none"
            stroke="#64748b"
            strokeWidth="1"
            strokeDasharray="4 4"
            points="0,70 400,70"
          />
        </svg>
        <div className="relative z-10 flex flex-col items-center gap-2 text-center">
          <CandlestickChart className="h-8 w-8 text-terminal-muted" strokeWidth={1.25} />
          <p className="max-w-xs text-xs text-terminal-muted">
            Interactive candlesticks connect once Binance / Bybit OHLCV adapters are live.
          </p>
        </div>
      </div>
    </div>
  );
}
