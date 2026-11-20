# Technical Indicators Engine (Phase 3.1)

Deterministic Python indicators under `backend/app/analysis/indicators/`.  
AI / LLMs are **never** used to invent indicator values.

## Principles

- Chronological UTC candles only
- Closed candles by default (`include_forming=false`)
- No look-ahead: each index uses only past + current bar
- Missing / warming values are `null` — never fabricated
- Rounding only at API presentation (`round_latest_for_api`)

## Module layout

```
backend/app/analysis/indicators/
  models.py            # ids, warmup, params, result models
  moving_averages.py   # SMA, EMA
  momentum.py          # RSI, MACD, Stoch RSI
  volatility.py        # ATR, Bollinger
  volume.py            # Volume SMA, OBV, Relative Volume
  calculator.py        # Orchestrator over normalized Candle[]
```

Realtime recalculation (shared exchange WS, no extra connections):

`backend/app/market_data/indicator_runtime.py`

## Supported indicators

| Id | Parameters | Warm-up (closed candles) | Notes |
|----|------------|--------------------------|-------|
| `ema_9` … `ema_200` | period, close | period | SMA seed then EMA |
| `sma_20` / `sma_50` / `sma_200` | period, close | period | |
| `rsi_14` | Wilder 14 | 15 | Flat → 50; all gains → 100 |
| `macd` | 12 / 26 / 9 | 35 | fields: macd, signal, histogram |
| `stoch_rsi` | 14 / 14 / 3 / 3 | 17 | fields: k, d |
| `atr_14` | Wilder 14 | 15 | |
| `bollinger` | 20, 2σ | 20 | fields: middle, upper, lower (ddof=0) |
| `volume_sma_20` | 20 | 20 | |
| `obv` | — | 2 | starts at 0 |
| `relative_volume` | vol / SMA20 | 20 | |

## REST

`GET /api/v1/indicators`

Query: `exchange`, `market_type`, `symbol`, `timeframe`, optional `indicators`, `include_forming`, `include_series`, `limit`.

`GET /api/v1/indicators/catalog` — ids, params, warm-up metadata.

## WebSocket

Same `/ws/market` hub:

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

Server emits `indicator_update` when candle updates change values (hash-deduped). Forming vs closed distinguished via `include_forming` / `is_forming`.

## Limitations

- Forming-candle values are unstable by design; closed-only is recommended for signals
- EMA200 needs ≥200 closed candles; short histories return `warming_up` / null
- Stoch RSI / MACD warm-ups are conservative vs some charting platforms
- Overlay series are REST-fetched; live panel values update over WS
