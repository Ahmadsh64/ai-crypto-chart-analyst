# Order Blocks & Fair Value Gaps (Phase 3.4)

Deterministic SMC / ICT zone detection. Implemented in Python only — never by an LLM.

Configuration version: **`obfvg-v1.0.0-balanced`**

Depends on:

- Phase 3.2 Market Structure (`ms-v1.0.0-balanced`) — confirmed BOS / MSS only
- Phase 3.1 Wilder ATR(14)

Phase 3.2 and 3.3 calculation rules are **not** modified.

---

## Inputs

| Input | Rule |
|-------|------|
| Candles | Closed candles for confirmed OB/FVG detection and lifecycle |
| Structure | Confirmed BOS and MSS events (not unconfirmed swings) |
| ATR | Wilder ATR(14) aligned to closed candles |
| Timestamps | Timezone-aware UTC |
| Isolation | Exchange × market_type × symbol × timeframe |
| Analysis window | Canonical `OB_FVG_ANALYSIS_CANDLE_LIMIT = 500` (REST default + WS) |

No look-ahead: status at time `t` uses only candles with `timestamp ≤ t`.

---

## Configuration defaults (`obfvg-v1.0.0-balanced`)

| Setting | Default | Notes |
|---------|---------|-------|
| `atr_period` | `14` | Shared with structure/liquidity |
| `ob_max_lookback` | `10` | Max closed candles searched backward from the break candle for the opposing candle |
| `ob_displacement_atr_mult` | `1.0` | Break-candle body must be ≥ `1.0 × ATR` |
| `ob_boundary_method` | `full_candle` | Zone = source candle `[low, high]` (configurable for future methods) |
| `ob_invalidate_on` | `close` | Invalidation requires a **closed** candle beyond the far boundary |
| `fvg_min_gap_atr_mult` | `0.1` | Min gap width = `0.1 × ATR` when ATR available |
| `fvg_min_gap_fallback_pct` | `0.0005` | `0.05%` of mid-gap when ATR missing |
| `use_closed_candles_only` | `true` | Confirmed events require closed candles |
| `analysis_candle_limit` | `500` | Shared REST / WS window |
| `config_version` | `obfvg-v1.0.0-balanced` | Embedded in every event |

---

## Order Block detection

### Qualifying structure events

| Side | Source events |
|------|----------------|
| Bullish OB | Confirmed **bullish BOS** or **bullish MSS** |
| Bearish OB | Confirmed **bearish BOS** or **bearish MSS** |

Plain CHoCH without MSS does **not** create an OB under this version (MSS already encodes displacement-qualified CHoCH). BOS still requires the displacement body rule below.

### Displacement rule

On the structure-break candle (BOS/MSS `candle_index`):

```
body = |close − open|
body ≥ ob_displacement_atr_mult × ATR(break_index)
```

If ATR is unavailable at that bar → no OB for that event.

### Bullish Order Block

1. Take a qualifying bullish BOS/MSS event at candle index `i`.
2. Search candles `i-1, i-2, …` up to `ob_max_lookback` bars.
3. Select the **last** (nearest to the break) **bearish** candle (`close < open`) in that window.
4. If none → no OB.
5. Source candle must have `timestamp <` break candle timestamp.
6. Zone (`full_candle`): `zone_low = source.low`, `zone_high = source.high`.
7. Detection timestamp = break candle confirmation timestamp.
8. Event key: `ob:bullish:{source_event_key}:{source_candle_ts}` — unique per (structure event, source candle).

### Bearish Order Block

Inverse: last **bullish** candle (`close > open`) before a bearish BOS/MSS, same lookback and displacement rules.

Zone: `zone_low = source.low`, `zone_high = source.high`.

### Non-detection

- No qualifying BOS/MSS
- Displacement body too small / ATR missing
- No opposing candle within lookback
- Zero-width zone (`zone_high ≤ zone_low`) — rejected
- Duplicate key already emitted

---

## Order Block lifecycle

Statuses: `active` → `partially_mitigated` → `mitigated` | `invalidated`

Evaluated on each **closed** candle at or after detection, in chronological order.

| Transition | Trigger |
|------------|---------|
| → `partially_mitigated` | Candle overlaps the zone (`high ≥ zone_low` and `low ≤ zone_high`) while status is `active` |
| → `mitigated` | Candle fully traverses the zone (`high ≥ zone_high` and `low ≤ zone_low`). **Precedence:** full traverse is `mitigated`, not `invalidated`, even if close is beyond the far side |
| → `invalidated` | While not yet mitigated: closed candle closes beyond the invalidation boundary — bullish OB: `close < zone_low`; bearish OB: `close > zone_high` (`ob_invalidate_on=close`) |

Terminal states: `mitigated`, `invalidated` — no further transitions.

Segment: `segment_start` = detection; `segment_end` = first mitigation / invalidation / series end; finite drawing only.

---

## Fair Value Gap detection

Three consecutive **closed** candles `(c1, c2, c3)` with indices `i-2, i-1, i`.

### Bullish FVG

```
c3.low > c1.high
gap = c3.low − c1.high
gap ≥ min_gap
zone_low = c1.high
zone_high = c3.low
```

### Bearish FVG

```
c3.high < c1.low
gap = c1.low − c3.high
gap ≥ min_gap
zone_low = c3.high
zone_high = c1.low
```

`min_gap = fvg_min_gap_atr_mult × ATR(i)` when ATR available, else `fvg_min_gap_fallback_pct × mid(zone_low, zone_high)`.

Reject zero/negative width. Event key: `fvg:{bullish|bearish}:{exchange}:{market}:{symbol}:{tf}:{c3_timestamp}`.

Detection timestamp = `c3.timestamp`. Store all three candle timestamps and OHLC references.

Forming (unclosed) `c3` → provisional only when `include_unconfirmed`; never confirmed.

---

## FVG lifecycle

Statuses: `active` → `partially_filled` → `filled` | `invalidated`

| Transition | Trigger |
|------------|---------|
| → `partially_filled` | Closed candle overlaps the gap while `active` |
| → `filled` | Closed candle fully traverses the gap (`high ≥ zone_high` and `low ≤ zone_low`). **Precedence over invalidation** |
| → `invalidated` | While not filled: bullish FVG `close < zone_low`; bearish FVG `close > zone_high` (far boundary relative to typical fill approach) |

Also track:

- `first_touch_timestamp`
- `max_fill_pct` ∈ [0, 100] — max fraction of gap range overlapped by any single candle (deterministic)
- `full_fill_timestamp` / `invalidation_timestamp`

---

## REST / WebSocket

- `GET /api/v1/ob-fvg` — default `limit=500`
- WS: `subscribe_ob_fvg` / `unsubscribe_ob_fvg` → `ob_fvg_update` (combined OB+FVG snapshot; kinds cover order_block and fvg updates)
- `snapshot` counts equal returned array lengths for the analysis window

---

## Out of scope

Trade decisions, execution, kill zones / sessions (later), confluence scoring (Phase 4).
