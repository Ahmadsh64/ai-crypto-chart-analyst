# API Reference

Base URL: `http://127.0.0.1:8000`

## GET `/`

Service metadata and links to docs / health.

## GET `/api/v1/health`

Returns process health and component readiness (including live exchange pings).

## GET `/api/v1/exchanges`

Lists Binance / Bybit, supported market types, default symbols, and timeframes.

## GET `/api/v1/markets`

Query params:

- `exchange` — `binance` | `bybit`
- `market_type` — `spot` | `usdt_m_futures` | `linear_perpetual`
- `search` — optional filter (e.g. `BTC`)

Returns normalized USDT trading pairs plus `last_updated` and `data_source`.

## GET `/api/v1/market/candles`

Example:

`GET /api/v1/market/candles?exchange=binance&symbol=BTC/USDT&market_type=spot&timeframe=15m&limit=500`

Query params:

- `exchange`, `market_type`, `symbol` (e.g. `BTC/USDT` or `BTCUSDT`)
- `timeframe` — `1m` | `5m` | `15m` | `30m` | `1h` | `4h` | `1d`
- `limit` — 1–5000 (paginated upstream when > 1000)

Response includes:

- `exchange`, `symbol`, `market_type`, `timeframe`
- `candles` (UTC, sorted, deduped; each has `is_closed`)
- `latest_price`
- `last_updated` / `updated_at`
- `data_source` (e.g. `binance:spot`)

## GET `/api/v1/market/ticker`

Query params: `exchange`, `market_type`, `symbol`

Returns last price, 24h stats, `last_updated`, and `data_source`.

## GET `/api/v1/market-structure`

Example:

`GET /api/v1/market-structure?exchange=binance&symbol=BTC/USDT&market_type=spot&timeframe=1h`

Query params:

- `exchange`, `market_type`, `symbol`, `timeframe`
- `limit` — OHLCV fetch size (50–2000)
- `include_unconfirmed` — default `false` (candidates are never labeled confirmed)

Response includes:

- `config` + `config_version` (`ms-v1.0.0-balanced`)
- `snapshot` (bias; `active_unbroken_swing_high` / `active_unbroken_swing_low` break targets; legacy aliases `active_bullish_level` / `active_bearish_level`)
- `swings`, `bos_events` (with `segment_start` / `segment_end` / `segment_active`), `choch_events`, `mss_events`
- `ambiguous_dual_breaks` (same-candle dual-wick diagnostic; no bias flip)

Rules: [strategy_definitions.md](strategy_definitions.md)

## GET `/api/v1/indicators`

Example:

`GET /api/v1/indicators?exchange=binance&symbol=BTC/USDT&market_type=spot&timeframe=15m&indicators=ema_20,rsi_14,macd`

Query params:

- `exchange`, `market_type`, `symbol`, `timeframe`
- `indicators` — optional comma-separated ids (default: all)
- `include_forming` — default `false` (closed candles only)
- `include_series` — default `false`; set `true` for chart overlay series
- `limit` — OHLCV fetch size (50–2000; engine may raise floor for EMA200 warm-up)

Response includes latest widget values (`status`, `value` / `fields`, warm-up metadata). Values are never fabricated — unavailable bars stay `null`.

Catalog: `GET /api/v1/indicators/catalog`

Formulas, warm-up tables, and limitations: [indicators.md](indicators.md)

## GET `/api/v1/liquidity`

Deterministic liquidity analysis (Phase 3.3.1, `liq-v1.1.0-balanced`). Rules: [liquidity_definitions.md](liquidity_definitions.md).

`GET /api/v1/liquidity?exchange=binance&symbol=BTC/USDT&market_type=spot&timeframe=1h&limit=500`

Query params: `exchange`, `market_type`, `symbol`, `timeframe`, `limit` (default **500**, same canonical window as WebSocket `max_candles`), `include_unconfirmed` (provisional forming-candle sweeps only).

Response includes `eqh_clusters`, `eql_clusters`, `bsl_levels`, `ssl_levels`, `sweeps`, `provisional_sweeps`, `ambiguous_crosses`, `config`, `snapshot`.

- `snapshot.sweep_count` **equals** `len(sweeps)` for the returned candle window; sweeps are **not** independently paginated.
- EQH/EQL clusters expose `representative_level` (median; alias `level`), `min_price`, `max_price`, `price_range`, `tolerance_used`, `member_count`.
- Sweeps expose authoritative `liquidity_type`, contextual `reaction_hint` (not a trade signal), and deprecated `direction` for compatibility.

No confidence percentages.

## GET `/api/v1/ob-fvg`

Deterministic Order Blocks and Fair Value Gaps (Phase 3.4, `obfvg-v1.0.0-balanced`). Rules: [ob_fvg_definitions.md](ob_fvg_definitions.md).

`GET /api/v1/ob-fvg?exchange=binance&symbol=BTC/USDT&market_type=spot&timeframe=1h&limit=500`

Query params: `exchange`, `market_type`, `symbol`, `timeframe`, `limit` (default **500**, same canonical window as WebSocket), `include_unconfirmed` (provisional forming-window events only).

Response includes `bullish_order_blocks`, `bearish_order_blocks`, `bullish_fvgs`, `bearish_fvgs`, `provisional_order_blocks`, `provisional_fvgs`, `config`, `snapshot`.

- Snapshot counts equal returned array lengths for the analysis window.
- Order blocks link to source BOS/MSS via `source_structure_event_key`.
- All zone boundaries are exact deterministic prices (no LLM).

No confidence percentages.

## GET `/api/v1/multi-timeframe`

Multi-Timeframe data orchestration (Phase 4.1, `mtf-v1.0.0-orchestration`). Rules: [multi_timeframe_architecture.md](multi_timeframe_architecture.md).

`GET /api/v1/multi-timeframe?exchange=binance&symbol=BTC/USDT&market_type=spot`

Fetches synchronized **4h / 1h / 15m / 5m** series via existing exchange adapters. Response includes per-TF readiness, stale/gap/error quality, sync metadata, and overall status (`ready` | `partial` | `unavailable`).

No trade signals. Forming candles are never treated as confirmed.

## GET `/api/v1/confluence`

Deterministic multi-timeframe confluence (Phase 4.2, `confluence-v1.0.0-balanced`). Rules: [confluence_engine.md](confluence_engine.md).

`GET /api/v1/confluence?exchange=binance&symbol=BTC/USDT&market_type=spot`

Returns `bullish_score`, `bearish_score`, category contributions, evidence, conflicts, and `preliminary_assessment` (`bullish_confluence` | `bearish_confluence` | `mixed` | `insufficient_evidence` | `data_unavailable`).

**Not** a trade recommendation — no LONG/SHORT/WAIT/NO TRADE.

## WS `/ws/market`

Real-time market stream (not under `/api/v1`).

Client subscribe example:

```json
{
  "action": "subscribe",
  "exchange": "binance",
  "symbol": "BTC/USDT",
  "market_type": "spot",
  "timeframe": "15m"
}
```

Ticker-only:

```json
{
  "action": "subscribe",
  "exchange": "bybit",
  "symbol": "ETH/USDT",
  "market_type": "linear_perpetual",
  "ticker_only": true
}
```

Indicators (reuses the same exchange candle stream — no extra exchange connection):

```json
{
  "action": "subscribe_indicators",
  "exchange": "binance",
  "symbol": "BTC/USDT",
  "market_type": "spot",
  "timeframe": "15m",
  "indicators": ["ema_20", "rsi_14", "macd"]
}
```

Market structure (same hub; emits only on closed-candle confirmations):

```json
{
  "action": "subscribe_structure",
  "exchange": "binance",
  "symbol": "BTC/USDT",
  "market_type": "spot",
  "timeframe": "1h"
}
```

Liquidity (same hub; closed-candle confirmations):

```json
{
  "action": "subscribe_liquidity",
  "exchange": "binance",
  "symbol": "BTC/USDT",
  "market_type": "spot",
  "timeframe": "1h"
}
```

Order Blocks / FVG (same hub; closed-candle confirmations):

```json
{
  "action": "subscribe_ob_fvg",
  "exchange": "binance",
  "symbol": "BTC/USDT",
  "market_type": "spot",
  "timeframe": "1h"
}
```

Multi-Timeframe orchestration (same hub; four kline intervals, no extra exchange sockets):

```json
{
  "action": "subscribe_multi_timeframe",
  "exchange": "binance",
  "symbol": "BTC/USDT",
  "market_type": "spot"
}
```

Confluence (recomputes on confirmed ladder candle closes only):

```json
{
  "action": "subscribe_confluence",
  "exchange": "binance",
  "symbol": "BTC/USDT",
  "market_type": "spot"
}
```

Server message types: `ticker_update`, `trade_update`, `candle_update`, `indicator_update`, `structure_update`, `liquidity_update`, `ob_fvg_update`, `multi_timeframe_update`, `confluence_update`, `connection_status`, `subscription_error`, `subscribed`, `unsubscribed`.

`liquidity_update` payload kinds conceptually cover level / sweep / status changes in one snapshot-compatible message (`kind`: `snapshot` | `update`).

`ob_fvg_update` is the normalized transport for order-block and FVG changes (`kind`: `snapshot` | `update`). Fresh OB/FVG events appear under `new_events` (`bullish_order_blocks`, `bearish_order_blocks`, `bullish_fvgs`, `bearish_fvgs`) — conceptual `order_block_update` / `fvg_update` payloads without extra exchange sockets.

`multi_timeframe_update` carries the orchestration snapshot plus optional `confirmed_candle` / `forming_candle` for the updated timeframe (`kind`: `snapshot` | `update`).

Every market message includes `exchange_ts` and `processed_at`.

## Historical replay (Phase 5.1)

Base path: `/api/v1/replay`

| Method | Path | Notes |
|--------|------|-------|
| POST | `/sessions` | Create + load historical candles |
| GET | `/sessions/{id}` | Session info + snapshot |
| POST | `/sessions/{id}/start\|pause\|resume\|stop\|step\|reset` | Playback controls |
| POST | `/sessions/{id}/speed` | Body `{ "speed": "1x"\|…\|"max" }` |
| DELETE | `/sessions/{id}` | Drop session |

WebSocket: `/ws/replay` (separate from live `/ws/market`). See [PHASE_5_1_HISTORICAL_REPLAY.md](PHASE_5_1_HISTORICAL_REPLAY.md).

### Historical analysis (Phase 5.2.1)

| Method | Path |
|--------|------|
| POST | `/sessions/{id}/analysis/enable` |
| POST | `/sessions/{id}/analysis/disable` |
| GET | `/sessions/{id}/analysis` |
| GET | `/sessions/{id}/analysis/history` |
| GET | `/sessions/{id}/analysis/at/{timestamp}` |

WS events: `replay_analysis_update`, `replay_analysis_error`. See [PHASE_5_2_1_HISTORICAL_ANALYSIS.md](PHASE_5_2_1_HISTORICAL_ANALYSIS.md).

## Planned endpoints (later phases)

| Method | Path | Phase |
|--------|------|-------|
| POST | `/api/v1/analysis/screenshot` | 5 |
| GET | `/api/v1/analysis/{id}` | 6 |
| GET | `/api/v1/analysis/history` | 6 |
| GET/POST/PATCH | `/api/v1/trades` | 6 |
| GET | `/api/v1/performance` | 6 |
| POST/GET | `/api/v1/backtesting/...` | 5.2+ / 6 |
