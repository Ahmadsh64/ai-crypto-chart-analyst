"use client";

import { format } from "date-fns";
import { useLiveMarketStore } from "@/stores/live-market-store";
import { cn } from "@/utils/cn";

const LABELS: Record<string, string> = {
  connected: "Connected",
  connecting: "Connecting",
  reconnecting: "Reconnecting",
  disconnected: "Disconnected",
  stale: "Stale Data",
};

export function StreamStatusBadge({ exchange }: { exchange?: string }) {
  const status = useLiveMarketStore((s) => s.connectionStatus);
  const lastMessageAt = useLiveMarketStore((s) => s.lastMessageAt);

  return (
    <div className="flex items-center gap-2 text-xs text-terminal-muted">
      <span
        className={cn(
          "inline-block h-2 w-2 rounded-full",
          status === "connected" && "bg-terminal-long",
          status === "connecting" && "bg-amber-400",
          status === "reconnecting" && "bg-amber-400",
          status === "stale" && "bg-amber-500",
          status === "disconnected" && "bg-terminal-short",
        )}
      />
      <span>
        {exchange ? `${exchange} · ` : ""}
        {LABELS[status] ?? status}
        {lastMessageAt ? ` · ${format(lastMessageAt, "HH:mm:ss")}` : ""}
      </span>
    </div>
  );
}
