"use client";

import { useEffect, useState } from "react";

export default function SettingsPage() {
  const [balance, setBalance] = useState(10000);
  const [riskPercent, setRiskPercent] = useState(1);
  const [minRr, setMinRr] = useState(2);
  const [timezone, setTimezone] = useState("UTC");

  useEffect(() => {
    setTimezone(Intl.DateTimeFormat().resolvedOptions().timeZone);
  }, []);

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-5 md:p-6">
      <div>
        <h1 className="font-display text-2xl font-semibold text-terminal-text">Settings</h1>
        <p className="mt-1 text-sm text-terminal-muted">
          Conservative risk defaults. Persistence arrives with PostgreSQL in Phase 6.
        </p>
      </div>

      <section className="space-y-4 rounded-lg border border-terminal-border bg-terminal-panel p-5">
        <h2 className="text-sm font-medium text-terminal-text">Risk Management</h2>

        <label className="block space-y-1.5">
          <span className="text-xs text-terminal-muted">Account balance (USD)</span>
          <input
            type="number"
            min={100}
            value={balance}
            onChange={(e) => setBalance(Number(e.target.value))}
            className="h-10 w-full rounded-md border border-terminal-border bg-terminal-surface px-3 text-sm text-terminal-text outline-none focus:border-terminal-accent"
          />
        </label>

        <label className="block space-y-1.5">
          <span className="text-xs text-terminal-muted">Risk per trade (%)</span>
          <input
            type="number"
            min={0.1}
            max={5}
            step={0.1}
            value={riskPercent}
            onChange={(e) => setRiskPercent(Number(e.target.value))}
            className="h-10 w-full rounded-md border border-terminal-border bg-terminal-surface px-3 text-sm text-terminal-text outline-none focus:border-terminal-accent"
          />
        </label>

        <label className="block space-y-1.5">
          <span className="text-xs text-terminal-muted">Minimum risk / reward</span>
          <input
            type="number"
            min={1}
            step={0.1}
            value={minRr}
            onChange={(e) => setMinRr(Number(e.target.value))}
            className="h-10 w-full rounded-md border border-terminal-border bg-terminal-surface px-3 text-sm text-terminal-text outline-none focus:border-terminal-accent"
          />
        </label>

        <p className="text-xs text-terminal-muted">
          Risk amount preview: ${((balance * riskPercent) / 100).toFixed(2)} per trade
        </p>
      </section>

      <section className="space-y-4 rounded-lg border border-terminal-border bg-terminal-panel p-5">
        <h2 className="text-sm font-medium text-terminal-text">Sessions & Timezone</h2>
        <label className="block space-y-1.5">
          <span className="text-xs text-terminal-muted">Preferred timezone (ICT sessions)</span>
          <input
            type="text"
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            className="h-10 w-full rounded-md border border-terminal-border bg-terminal-surface px-3 text-sm text-terminal-text outline-none focus:border-terminal-accent"
          />
        </label>
      </section>
    </div>
  );
}
