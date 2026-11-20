"use client";

import type { ExchangeId, MarketType, Timeframe } from "@/types/api";

export type WsConnectionStatus =
  | "disconnected"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "stale";

export type MarketWsMessageType =
  | "ticker_update"
  | "trade_update"
  | "candle_update"
  | "indicator_update"
  | "structure_update"
  | "liquidity_update"
  | "ob_fvg_update"
  | "multi_timeframe_update"
  | "confluence_update"
  | "trade_plan_update"
  | "decision_update"
  | "connection_status"
  | "subscription_error"
  | "subscribed"
  | "unsubscribed";

export interface MarketWsMessage {
  type: MarketWsMessageType;
  exchange?: ExchangeId | null;
  symbol?: string | null;
  market_type?: MarketType | null;
  timeframe?: Timeframe | null;
  exchange_ts?: string | null;
  processed_at: string;
  status?: string | null;
  detail?: string | null;
  data?: Record<string, unknown> | null;
}

export interface SubscribeRequest {
  exchange: ExchangeId;
  symbol: string;
  marketType: MarketType;
  timeframe?: Timeframe;
  tickerOnly?: boolean;
}

export interface IndicatorSubscribeRequest {
  exchange: ExchangeId;
  symbol: string;
  marketType: MarketType;
  timeframe: Timeframe;
  indicators?: string[];
}

export interface StructureSubscribeRequest {
  exchange: ExchangeId;
  symbol: string;
  marketType: MarketType;
  timeframe: Timeframe;
}

export interface LiquiditySubscribeRequest {
  exchange: ExchangeId;
  symbol: string;
  marketType: MarketType;
  timeframe: Timeframe;
}

export interface ObFvgSubscribeRequest {
  exchange: ExchangeId;
  symbol: string;
  marketType: MarketType;
  timeframe: Timeframe;
}

export interface MultiTimeframeSubscribeRequest {
  exchange: ExchangeId;
  symbol: string;
  marketType: MarketType;
}

export interface ConfluenceSubscribeRequest {
  exchange: ExchangeId;
  symbol: string;
  marketType: MarketType;
}

export interface TradePlanSubscribeRequest {
  exchange: ExchangeId;
  symbol: string;
  marketType: MarketType;
  accountBalance?: number;
  riskPercent?: number;
}

export interface DecisionSubscribeRequest {
  exchange: ExchangeId;
  symbol: string;
  marketType: MarketType;
  accountBalance?: number;
  riskPercent?: number;
}

type MessageListener = (message: MarketWsMessage) => void;
type StatusListener = (status: WsConnectionStatus) => void;

function wsUrl(): string {
  const api = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
  const url = new URL(api);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/ws/market";
  url.search = "";
  url.hash = "";
  return url.toString();
}

function subKey(req: SubscribeRequest): string {
  const tf = req.tickerOnly ? "-" : (req.timeframe ?? "1h");
  return `${req.exchange}:${req.marketType}:${req.symbol.toUpperCase()}:${tf}`;
}

class MarketWebsocketClient {
  private socket: WebSocket | null = null;
  private status: WsConnectionStatus = "disconnected";
  private listeners = new Set<MessageListener>();
  private statusListeners = new Set<StatusListener>();
  private desired = new Map<string, SubscribeRequest>();
  private desiredIndicators = new Map<string, IndicatorSubscribeRequest>();
  private desiredStructure = new Map<string, StructureSubscribeRequest>();
  private desiredLiquidity = new Map<string, LiquiditySubscribeRequest>();
  private desiredObFvg = new Map<string, ObFvgSubscribeRequest>();
  private desiredMultiTimeframe = new Map<string, MultiTimeframeSubscribeRequest>();
  private desiredConfluence = new Map<string, ConfluenceSubscribeRequest>();
  private desiredTradePlan = new Map<string, TradePlanSubscribeRequest>();
  private desiredDecision = new Map<string, DecisionSubscribeRequest>();
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private lastMessageAt: number | null = null;
  private staleTimer: ReturnType<typeof setInterval> | null = null;
  private shouldRun = false;
  private lastPayloadByKey = new Map<string, string>();

  connect() {
    this.shouldRun = true;
    if (
      this.socket &&
      (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }
    this.setStatus("connecting");
    const socket = new WebSocket(wsUrl());
    this.socket = socket;

    socket.onopen = () => {
      this.reconnectAttempt = 0;
      this.setStatus("connected");
      this.flushSubscriptions();
      this.startHeartbeat();
    };

    socket.onmessage = (event) => {
      this.lastMessageAt = Date.now();
      if (this.status === "stale") this.setStatus("connected");
      try {
        const message = JSON.parse(String(event.data)) as MarketWsMessage;
        if (!this.isDuplicate(message)) {
          this.listeners.forEach((listener) => listener(message));
        }
        if (message.type === "connection_status" && message.status) {
          if (message.status === "reconnecting") this.setStatus("reconnecting");
          if (message.status === "stale") this.setStatus("stale");
          if (message.status === "connected") this.setStatus("connected");
        }
      } catch {
        /* ignore malformed */
      }
    };

    socket.onclose = () => {
      this.clearHeartbeat();
      this.socket = null;
      if (!this.shouldRun) {
        this.setStatus("disconnected");
        return;
      }
      this.setStatus("reconnecting");
      const delay = Math.min(30_000, 1000 * 2 ** this.reconnectAttempt);
      this.reconnectAttempt += 1;
      this.reconnectTimer = setTimeout(() => this.connect(), delay);
    };

    socket.onerror = () => {
      // onclose handles reconnect
    };

    if (!this.staleTimer) {
      this.staleTimer = setInterval(() => {
        if (!this.lastMessageAt || this.status === "disconnected") return;
        if (Date.now() - this.lastMessageAt > 15_000 && this.status === "connected") {
          this.setStatus("stale");
        }
      }, 3000);
    }
  }

  disconnect() {
    this.shouldRun = false;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.clearHeartbeat();
    if (this.staleTimer) {
      clearInterval(this.staleTimer);
      this.staleTimer = null;
    }
    this.socket?.close();
    this.socket = null;
    this.setStatus("disconnected");
  }

  subscribe(req: SubscribeRequest) {
    const key = subKey(req);
    this.desired.set(key, req);
    this.connect();
    this.send({
      action: "subscribe",
      exchange: req.exchange,
      symbol: req.symbol,
      market_type: req.marketType,
      timeframe: req.timeframe ?? "1h",
      ticker_only: Boolean(req.tickerOnly),
    });
    return () => this.unsubscribe(req);
  }

  unsubscribe(req: SubscribeRequest) {
    const key = subKey(req);
    this.desired.delete(key);
    this.send({
      action: "unsubscribe",
      exchange: req.exchange,
      symbol: req.symbol,
      market_type: req.marketType,
      timeframe: req.timeframe,
    });
  }

  subscribeIndicators(req: IndicatorSubscribeRequest) {
    const key = `${req.exchange}:${req.marketType}:${req.symbol.toUpperCase()}:${req.timeframe}:ind`;
    this.desiredIndicators.set(key, req);
    this.connect();
    this.send({
      action: "subscribe_indicators",
      exchange: req.exchange,
      symbol: req.symbol,
      market_type: req.marketType,
      timeframe: req.timeframe,
      indicators: req.indicators,
    });
    return () => this.unsubscribeIndicators(req);
  }

  unsubscribeIndicators(req: IndicatorSubscribeRequest) {
    const key = `${req.exchange}:${req.marketType}:${req.symbol.toUpperCase()}:${req.timeframe}:ind`;
    this.desiredIndicators.delete(key);
    this.send({ action: "unsubscribe_indicators" });
  }

  subscribeStructure(req: StructureSubscribeRequest) {
    const key = `${req.exchange}:${req.marketType}:${req.symbol.toUpperCase()}:${req.timeframe}:struct`;
    this.desiredStructure.set(key, req);
    this.connect();
    this.send({
      action: "subscribe_structure",
      exchange: req.exchange,
      symbol: req.symbol,
      market_type: req.marketType,
      timeframe: req.timeframe,
    });
    return () => this.unsubscribeStructure(req);
  }

  unsubscribeStructure(req: StructureSubscribeRequest) {
    const key = `${req.exchange}:${req.marketType}:${req.symbol.toUpperCase()}:${req.timeframe}:struct`;
    this.desiredStructure.delete(key);
    this.send({ action: "unsubscribe_structure" });
  }

  subscribeLiquidity(req: LiquiditySubscribeRequest) {
    const key = `${req.exchange}:${req.marketType}:${req.symbol.toUpperCase()}:${req.timeframe}:liq`;
    this.desiredLiquidity.set(key, req);
    this.connect();
    this.send({
      action: "subscribe_liquidity",
      exchange: req.exchange,
      symbol: req.symbol,
      market_type: req.marketType,
      timeframe: req.timeframe,
    });
    return () => this.unsubscribeLiquidity(req);
  }

  unsubscribeLiquidity(req: LiquiditySubscribeRequest) {
    const key = `${req.exchange}:${req.marketType}:${req.symbol.toUpperCase()}:${req.timeframe}:liq`;
    this.desiredLiquidity.delete(key);
    this.send({ action: "unsubscribe_liquidity" });
  }

  subscribeObFvg(req: ObFvgSubscribeRequest) {
    const key = `${req.exchange}:${req.marketType}:${req.symbol.toUpperCase()}:${req.timeframe}:obfvg`;
    this.desiredObFvg.set(key, req);
    this.connect();
    this.send({
      action: "subscribe_ob_fvg",
      exchange: req.exchange,
      symbol: req.symbol,
      market_type: req.marketType,
      timeframe: req.timeframe,
    });
    return () => this.unsubscribeObFvg(req);
  }

  unsubscribeObFvg(req: ObFvgSubscribeRequest) {
    const key = `${req.exchange}:${req.marketType}:${req.symbol.toUpperCase()}:${req.timeframe}:obfvg`;
    this.desiredObFvg.delete(key);
    this.send({ action: "unsubscribe_ob_fvg" });
  }

  subscribeMultiTimeframe(req: MultiTimeframeSubscribeRequest) {
    const key = `${req.exchange}:${req.marketType}:${req.symbol.toUpperCase()}:mtf`;
    this.desiredMultiTimeframe.set(key, req);
    this.connect();
    this.send({
      action: "subscribe_multi_timeframe",
      exchange: req.exchange,
      symbol: req.symbol,
      market_type: req.marketType,
    });
    return () => this.unsubscribeMultiTimeframe(req);
  }

  unsubscribeMultiTimeframe(req: MultiTimeframeSubscribeRequest) {
    const key = `${req.exchange}:${req.marketType}:${req.symbol.toUpperCase()}:mtf`;
    this.desiredMultiTimeframe.delete(key);
    this.send({ action: "unsubscribe_multi_timeframe" });
  }

  subscribeConfluence(req: ConfluenceSubscribeRequest) {
    const key = `${req.exchange}:${req.marketType}:${req.symbol.toUpperCase()}:confluence`;
    this.desiredConfluence.set(key, req);
    this.connect();
    this.send({
      action: "subscribe_confluence",
      exchange: req.exchange,
      symbol: req.symbol,
      market_type: req.marketType,
    });
    return () => this.unsubscribeConfluence(req);
  }

  unsubscribeConfluence(req: ConfluenceSubscribeRequest) {
    const key = `${req.exchange}:${req.marketType}:${req.symbol.toUpperCase()}:confluence`;
    this.desiredConfluence.delete(key);
    this.send({ action: "unsubscribe_confluence" });
  }

  subscribeTradePlan(req: TradePlanSubscribeRequest) {
    const key = `${req.exchange}:${req.marketType}:${req.symbol.toUpperCase()}:trade_plan`;
    this.desiredTradePlan.set(key, req);
    this.connect();
    this.send({
      action: "subscribe_trade_plan",
      exchange: req.exchange,
      symbol: req.symbol,
      market_type: req.marketType,
      account_balance: req.accountBalance,
      risk_percent: req.riskPercent,
    });
    return () => this.unsubscribeTradePlan(req);
  }

  unsubscribeTradePlan(req: TradePlanSubscribeRequest) {
    const key = `${req.exchange}:${req.marketType}:${req.symbol.toUpperCase()}:trade_plan`;
    this.desiredTradePlan.delete(key);
    this.send({ action: "unsubscribe_trade_plan" });
  }

  subscribeDecision(req: DecisionSubscribeRequest) {
    const key = `${req.exchange}:${req.marketType}:${req.symbol.toUpperCase()}:decision`;
    this.desiredDecision.set(key, req);
    this.connect();
    this.send({
      action: "subscribe_decision",
      exchange: req.exchange,
      symbol: req.symbol,
      market_type: req.marketType,
      account_balance: req.accountBalance,
      risk_percent: req.riskPercent,
    });
    return () => this.unsubscribeDecision(req);
  }

  unsubscribeDecision(req: DecisionSubscribeRequest) {
    const key = `${req.exchange}:${req.marketType}:${req.symbol.toUpperCase()}:decision`;
    this.desiredDecision.delete(key);
    this.send({ action: "unsubscribe_decision" });
  }

  onMessage(listener: MessageListener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  onStatus(listener: StatusListener) {
    this.statusListeners.add(listener);
    listener(this.status);
    return () => this.statusListeners.delete(listener);
  }

  getStatus() {
    return this.status;
  }

  getLastMessageAt() {
    return this.lastMessageAt;
  }

  private flushSubscriptions() {
    for (const req of this.desired.values()) {
      this.send({
        action: "subscribe",
        exchange: req.exchange,
        symbol: req.symbol,
        market_type: req.marketType,
        timeframe: req.timeframe ?? "1h",
        ticker_only: Boolean(req.tickerOnly),
      });
    }
    for (const req of this.desiredIndicators.values()) {
      this.send({
        action: "subscribe_indicators",
        exchange: req.exchange,
        symbol: req.symbol,
        market_type: req.marketType,
        timeframe: req.timeframe,
        indicators: req.indicators,
      });
    }
    for (const req of this.desiredStructure.values()) {
      this.send({
        action: "subscribe_structure",
        exchange: req.exchange,
        symbol: req.symbol,
        market_type: req.marketType,
        timeframe: req.timeframe,
      });
    }
    for (const req of this.desiredLiquidity.values()) {
      this.send({
        action: "subscribe_liquidity",
        exchange: req.exchange,
        symbol: req.symbol,
        market_type: req.marketType,
        timeframe: req.timeframe,
      });
    }
    for (const req of this.desiredObFvg.values()) {
      this.send({
        action: "subscribe_ob_fvg",
        exchange: req.exchange,
        symbol: req.symbol,
        market_type: req.marketType,
        timeframe: req.timeframe,
      });
    }
    for (const req of this.desiredMultiTimeframe.values()) {
      this.send({
        action: "subscribe_multi_timeframe",
        exchange: req.exchange,
        symbol: req.symbol,
        market_type: req.marketType,
      });
    }
    for (const req of this.desiredConfluence.values()) {
      this.send({
        action: "subscribe_confluence",
        exchange: req.exchange,
        symbol: req.symbol,
        market_type: req.marketType,
      });
    }
    for (const req of this.desiredTradePlan.values()) {
      this.send({
        action: "subscribe_trade_plan",
        exchange: req.exchange,
        symbol: req.symbol,
        market_type: req.marketType,
        account_balance: req.accountBalance,
        risk_percent: req.riskPercent,
      });
    }
    for (const req of this.desiredDecision.values()) {
      this.send({
        action: "subscribe_decision",
        exchange: req.exchange,
        symbol: req.symbol,
        market_type: req.marketType,
        account_balance: req.accountBalance,
        risk_percent: req.riskPercent,
      });
    }
  }

  private send(payload: Record<string, unknown>) {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(payload));
    }
  }

  private startHeartbeat() {
    this.clearHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      this.send({ action: "ping" });
    }, 20_000);
  }

  private clearHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private setStatus(status: WsConnectionStatus) {
    this.status = status;
    this.statusListeners.forEach((listener) => listener(status));
  }

  private isDuplicate(message: MarketWsMessage): boolean {
    if (
      message.type !== "ticker_update" &&
      message.type !== "candle_update" &&
      message.type !== "trade_update" &&
      message.type !== "indicator_update" &&
      message.type !== "structure_update" &&
      message.type !== "liquidity_update" &&
      message.type !== "ob_fvg_update" &&
      message.type !== "multi_timeframe_update" &&
      message.type !== "confluence_update" &&
      message.type !== "trade_plan_update" &&
      message.type !== "decision_update"
    ) {
      return false;
    }
    const mapKey = [
      message.type,
      message.exchange,
      message.symbol,
      message.market_type,
      message.timeframe ?? "",
    ].join("|");
    const fingerprint = `${message.exchange_ts ?? ""}:${JSON.stringify(message.data ?? {})}`;
    if (this.lastPayloadByKey.get(mapKey) === fingerprint) return true;
    this.lastPayloadByKey.set(mapKey, fingerprint);
    if (this.lastPayloadByKey.size > 500) {
      const first = this.lastPayloadByKey.keys().next().value;
      if (first) this.lastPayloadByKey.delete(first);
    }
    return false;
  }
}

export const marketWebsocket = new MarketWebsocketClient();
