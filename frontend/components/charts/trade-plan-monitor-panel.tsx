"use client";

import { cn } from "@/utils/cn";
import type {
  EntryDistanceModel,
  LevelTouchModel,
  MarketFreshness,
  MonitorAlert,
  PlanLevelKind,
  SlMonitorModel,
  TpProgressModel,
  TpProximityModel,
  TradePlanMonitorModel,
} from "@/lib/trade-plan-monitor";

function fmt(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function fmtSigned(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toLocaleString(undefined, { maximumFractionDigits: digits })}`;
}

function freshnessTone(f: MarketFreshness): string {
  switch (f) {
    case "LIVE":
      return "border-terminal-long/50 text-terminal-long";
    case "DELAYED":
      return "border-amber-400/50 text-amber-200";
    case "STALE":
    case "DISCONNECTED":
      return "border-terminal-short/50 text-terminal-short";
    case "RECONNECTING":
      return "border-amber-400/40 text-amber-200";
    default:
      return "border-terminal-border text-terminal-muted";
  }
}

function progressTone(p: TpProgressModel): string {
  if (p.progressPct == null) return "bg-terminal-border";
  if (p.progressPct < 0) return "bg-terminal-short/70";
  if (p.beyondTarget || p.progressPct >= 100) return "bg-terminal-long";
  return "bg-emerald-400/80";
}

function progressWidth(p: TpProgressModel): string {
  if (p.progressPct == null) return "0%";
  // Visual bar only — numeric label shows uncapped value.
  const visual = Math.max(0, Math.min(100, p.progressPct));
  return `${visual}%`;
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <div className="text-[10px] uppercase tracking-[0.14em] text-terminal-muted">{title}</div>
      {children}
    </div>
  );
}

function SelectableRow({
  active,
  onClick,
  children,
  className,
}: {
  active?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full items-center justify-between gap-2 rounded border px-2 py-1.5 text-left text-[11px] transition",
        active
          ? "border-terminal-accent/60 bg-terminal-accent/10 text-terminal-text"
          : "border-terminal-border/60 bg-terminal-bg/30 text-terminal-text hover:border-terminal-accent/40",
        className,
      )}
    >
      {children}
    </button>
  );
}

function EntryBlock({
  model,
  selected,
  onSelect,
}: {
  model: EntryDistanceModel;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <SelectableRow active={selected} onClick={onSelect}>
      <div className="min-w-0 space-y-0.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">
            {model.plannedLabel ? "PLANNED ENTRY" : "ENTRY"}
          </span>
          <span className="rounded border border-terminal-border/70 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-terminal-muted">
            {model.status}
          </span>
        </div>
        <div className="font-mono text-terminal-muted">
          Px {fmt(model.currentPrice, 4)} · Entry {fmt(model.entryPrice, 4)}
        </div>
      </div>
      <div className="shrink-0 text-right font-mono">
        <div>{fmtSigned(model.absoluteDistance, 4)}</div>
        <div className="text-terminal-muted">{fmtSigned(model.percentDistance, 2)}%</div>
      </div>
    </SelectableRow>
  );
}

function TpProgressBlock({
  items,
  selectedKind,
  onSelect,
}: {
  items: TpProgressModel[];
  selectedKind: PlanLevelKind | null;
  onSelect: (kind: PlanLevelKind) => void;
}) {
  if (!items.length) {
    return <p className="text-[11px] text-terminal-muted">No TP levels from plan.</p>;
  }
  return (
    <div className="space-y-1.5">
      {items.map((tp) => {
        const kind = `tp${tp.index}` as PlanLevelKind;
        return (
          <SelectableRow
            key={tp.index}
            active={selectedKind === kind}
            onClick={() => onSelect(kind)}
          >
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">{tp.label}</span>
                <span className="text-[9px] uppercase tracking-wide text-terminal-muted">
                  {tp.progressLabel}
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded bg-terminal-border/80">
                <div
                  className={cn("h-full transition-[width]", progressTone(tp))}
                  style={{ width: progressWidth(tp) }}
                />
              </div>
              <div className="font-mono text-terminal-muted">
                {tp.progressPct == null ? "—" : `${fmtSigned(tp.progressPct, 1)}%`} · target{" "}
                {fmt(tp.targetPrice, 4)}
              </div>
            </div>
          </SelectableRow>
        );
      })}
    </div>
  );
}

function SlBlock({
  model,
  selected,
  onSelect,
}: {
  model: SlMonitorModel;
  selected: boolean;
  onSelect: () => void;
}) {
  const warn =
    model.status === "PRICE BEYOND SL LEVEL" ||
    model.status === "PRICE AT SL LEVEL" ||
    model.status === "VERY NEAR SL" ||
    model.status === "NEAR SL";
  return (
    <div className="space-y-1">
      <SelectableRow
        active={selected}
        onClick={onSelect}
        className={warn ? "border-terminal-short/50" : undefined}
      >
        <div className="min-w-0 space-y-0.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">STOP LOSS</span>
            <span
              className={cn(
                "rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-wide",
                warn
                  ? "border-terminal-short/50 text-terminal-short"
                  : "border-terminal-border/70 text-terminal-muted",
              )}
            >
              {model.status}
            </span>
          </div>
          <div className="font-mono text-terminal-muted">
            SL {fmt(model.stopLossPrice, 4)} · Px {fmt(model.currentPrice, 4)}
          </div>
        </div>
        <div className="shrink-0 text-right font-mono">
          <div>{fmt(model.absoluteDistance, 4)}</div>
          <div className="text-terminal-muted">{fmt(model.percentDistance, 2)}%</div>
        </div>
      </SelectableRow>
      {model.warningText ? (
        <p className="rounded border border-terminal-short/40 bg-terminal-short/10 px-2 py-1 text-[10px] text-terminal-short">
          {model.warningText}
        </p>
      ) : null}
    </div>
  );
}

function TpProximityBlock({
  items,
  selectedKind,
  onSelect,
}: {
  items: TpProximityModel[];
  selectedKind: PlanLevelKind | null;
  onSelect: (kind: PlanLevelKind) => void;
}) {
  if (!items.length) return null;
  return (
    <div className="space-y-1">
      {items.map((tp) => {
        const kind = `tp${tp.index}` as PlanLevelKind;
        return (
          <SelectableRow
            key={tp.index}
            active={selectedKind === kind}
            onClick={() => onSelect(kind)}
          >
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{tp.label}</span>
                <span className="rounded border border-terminal-border/70 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-terminal-muted">
                  {tp.status}
                </span>
              </div>
              <div className="font-mono text-terminal-muted">
                {fmt(tp.targetPrice, 4)} · dist {fmt(tp.absoluteDistance, 4)} (
                {fmt(tp.percentDistance, 2)}%)
              </div>
            </div>
          </SelectableRow>
        );
      })}
    </div>
  );
}

function TouchesBlock({ touches }: { touches: LevelTouchModel[] }) {
  const shown = touches.filter((t) => t.status !== "NO TOUCH");
  if (!shown.length) {
    return <p className="text-[11px] text-terminal-muted">No price-level touches in available candles.</p>;
  }
  return (
    <ul className="space-y-1 text-[11px]">
      {shown.map((t) => (
        <li
          key={`${t.levelKind}-${t.candleTimestamp ?? "na"}-${t.status}`}
          className="rounded border border-terminal-border/50 px-2 py-1 font-mono text-terminal-muted"
        >
          <span className="uppercase text-terminal-text">{t.levelKind}</span> · {t.status}
          {t.candleTimestamp ? ` · ${t.candleTimestamp}` : ""}
        </li>
      ))}
    </ul>
  );
}

function AlertsBlock({ alerts }: { alerts: MonitorAlert[] }) {
  if (!alerts.length) {
    return <p className="text-[11px] text-terminal-muted">No active proximity alerts.</p>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {alerts.map((a) => (
        <span
          key={a.id}
          className={cn(
            "rounded border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide",
            a.type === "SL WARNING"
              ? "border-terminal-short/50 bg-terminal-short/10 text-terminal-short"
              : "border-amber-400/40 bg-amber-400/10 text-amber-200",
          )}
        >
          {a.message}
        </span>
      ))}
    </div>
  );
}

export function TradePlanMonitorPanel({
  monitor,
  selectedLevel,
  onSelectLevel,
  selectedLineLabel,
}: {
  monitor: TradePlanMonitorModel;
  selectedLevel: PlanLevelKind | null;
  onSelectLevel: (kind: PlanLevelKind | null) => void;
  selectedLineLabel?: string | null;
}) {
  return (
    <div className="space-y-3 rounded-md border border-terminal-border/70 bg-terminal-bg/40 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-[11px] uppercase tracking-[0.14em] text-terminal-muted">
          Trade plan monitor
        </div>
        <span
          className={cn(
            "rounded border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide",
            freshnessTone(monitor.freshness),
          )}
        >
          {monitor.freshness}
        </span>
      </div>

      <div className="font-mono text-sm text-terminal-text">
        Current {fmt(monitor.currentPrice, 4)}
        {monitor.side ? (
          <span className="ml-2 text-[10px] uppercase text-terminal-muted">
            {monitor.side} · {monitor.decision ?? "—"}
          </span>
        ) : null}
      </div>

      {selectedLineLabel ? (
        <p className="rounded border border-terminal-accent/30 bg-terminal-accent/5 px-2 py-1 text-[10px] text-terminal-accent">
          Chart focus: {selectedLineLabel}
        </p>
      ) : null}

      {!monitor.active ? (
        <p className="text-[11px] text-terminal-muted">
          Monitor idle — no active planned levels for the current decision.
        </p>
      ) : (
        <>
          <Section title="Distance to entry">
            <EntryBlock
              model={monitor.entryDistance}
              selected={selectedLevel === "entry"}
              onSelect={() =>
                onSelectLevel(selectedLevel === "entry" ? null : "entry")
              }
            />
          </Section>

          <Section title="TP price progress">
            <TpProgressBlock
              items={monitor.tpProgress}
              selectedKind={selectedLevel}
              onSelect={(kind) => onSelectLevel(selectedLevel === kind ? null : kind)}
            />
          </Section>

          <Section title="Stop loss monitor">
            <SlBlock
              model={monitor.stopLoss}
              selected={selectedLevel === "sl"}
              onSelect={() => onSelectLevel(selectedLevel === "sl" ? null : "sl")}
            />
          </Section>

          <Section title="Target proximity">
            <TpProximityBlock
              items={monitor.tpProximity}
              selectedKind={selectedLevel}
              onSelect={(kind) => onSelectLevel(selectedLevel === kind ? null : kind)}
            />
          </Section>

          <Section title="Price-level touch">
            <TouchesBlock touches={monitor.touches} />
          </Section>

          <Section title="Visual alerts">
            <AlertsBlock alerts={monitor.alerts} />
          </Section>
        </>
      )}

      <p className="text-[10px] text-terminal-muted">{monitor.disclaimer}</p>
    </div>
  );
}
