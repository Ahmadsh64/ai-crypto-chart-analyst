"use client";

import { getAccessToken } from "@/lib/supabase/client";

type ReplayListener = (message: Record<string, unknown>) => void;

async function wsUrl(): Promise<string> {
  const api = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
  const url = new URL(api);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/ws/replay";
  url.search = "";
  url.hash = "";
  const token = await getAccessToken();
  if (token) {
    url.searchParams.set("access_token", token);
  }
  return url.toString();
}

/** Dedicated historical replay socket — never shares /ws/market. */
export class ReplayWebsocketClient {
  private socket: WebSocket | null = null;
  private listeners = new Set<ReplayListener>();
  private sessionId: string | null = null;

  connect(sessionId?: string) {
    void this.connectAsync(sessionId);
  }

  private async connectAsync(sessionId?: string) {
    this.sessionId = sessionId ?? null;
    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
      if (sessionId) this.subscribe(sessionId);
      return;
    }
    const socket = new WebSocket(await wsUrl());
    this.socket = socket;
    socket.onmessage = (ev) => {
      try {
        const msg = JSON.parse(String(ev.data)) as Record<string, unknown>;
        for (const fn of this.listeners) fn(msg);
      } catch {
        /* ignore */
      }
    };
    socket.onopen = () => {
      if (this.sessionId) this.subscribe(this.sessionId);
    };
  }

  subscribe(sessionId: string) {
    this.sessionId = sessionId;
    this.socket?.send(JSON.stringify({ action: "subscribe", session_id: sessionId }));
  }

  disconnect() {
    this.socket?.close();
    this.socket = null;
    this.sessionId = null;
  }

  onMessage(fn: ReplayListener) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }
}

export const replayWebsocket = new ReplayWebsocketClient();
