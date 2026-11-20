# Liquidity Definitions (Phase 3.3.1)

Deterministic SMC / ICT liquidity detection. Implemented in Python only — never by an LLM.

Configuration version: **`liq-v1.1.0-balanced`**

Depends on Phase 3.2 confirmed swings (`ms-v1.0.0-balanced`). Phase 3.2 calculation rules are **not** modified.

---

## Inputs

| Input | Rule |
|-------|------|
| Candles | Closed candles only for confirmed events |
| Swings | Confirmed Swing High / Swing Low from Market Structure |
| ATR | Wilder ATR(14) from the existing indicators module |
| Timestamps | Timezone-aware UTC |
| Isolation | Exchange × market_type × symbol × timeframe |
| Analysis window | Canonical `LIQUIDITY_ANALYSIS_CANDLE_LIMIT = 500` (REST default `limit` and WebSocket `max_candles`) |

A swing may contribute to liquidity only after its **`confirmation_timestamp`** (no look-ahead).

---

## Configuration defaults (`liq-v1.1.0-balanced`)

| Setting | Default | Notes |
|---------|---------|-------|
| `eq_cluster_min_swings` | `2` | Minimum confirmed swings to form EQH/EQL |
| `atr_period` | `14` | ATR period for tolerance / penetration |
| `atr_tolerance_mult` | `0.15` | Diameter budget `T = 0.15 × ATR` when ATR available |
| `fallback_tolerance_pct` | `0.001` | `0.1%` of mid(min,max) when ATR missing/non-finite |
| `min_penetration_atr_mult` | `0.05` | Min wick penetration beyond level = `0.05 × ATR` |
| `min_penetration_fallback_pct` | `0.0002` | `0.02%` of level price when ATR missing |
| `use_closed_candles_only` | `true` | Confirmed sweeps require closed candles |
| `analysis_candle_limit` | `500` | Shared REST / WS candle window |
| `config_version` | `liq-v1.1.0-balanced` | Embedded in every event |

---

## EQH — Equal Highs

### Diameter rule (Phase 3.3.1)

A valid cluster must satisfy:

```
max(member_prices) − min(member_prices) ≤ T
```

where `T` is computed at the **latest** confirmation among the candidate members:

- `T = atr_tolerance_mult × ATR(atr_period)` when ATR is available, else
- `T = fallback_tolerance_pct × mid(min_price, max_price)`.

Exact boundary `diameter == T` is accepted.

### Clustering algorithm (deterministic)

Chronological greedy assignment — **not** unbounded transitive union-find:

1. Confirmed Swing Highs with `confirmation_timestamp ≤` analysis time only.
2. Sort by `(confirmation_timestamp ASC, event_key ASC)`.
3. Assign each swing to **at most one** cluster:
   - Eligible = existing groups where adding the swing keeps diameter ≤ T.
   - Tie-break: (a) smallest resulting diameter, (b) earliest first-member confirmation, (c) lexicographically smallest first-member `event_key`.
   - If none eligible → start a new singleton group.
4. Never merge two existing clusters (avoids silent diameter violations).
5. Emit groups with `member_count ≥ eq_cluster_min_swings`.

### Cluster outputs

| Field | Meaning |
|-------|---------|
| `level` | Representative **median** (backward-compatible alias) |
| `representative_level` | Same median |
| `min_price` / `max_price` / `price_range` | Exact member extremes |
| `tolerance_used` | T used for the final member set |
| `member_count` | Number of contributing swings |

**First detection** = confirmation of the swing that first made size ≥ min.  
**Latest confirmation** = max member confirmation.  
**Cluster key** stable from the first two seed members’ keys (SHA1 digest).

Do **not** use arbitrary candle highs — only confirmed swing points.

### Non-detection

- Fewer than `eq_cluster_min_swings` highs within diameter T.
- Adding a swing would make diameter > T.
- Unconfirmed / forming pivots / future confirmations.

---

## EQL — Equal Lows

Same diameter rules applied to confirmed **Swing Lows**.

---

## BSL / SSL classification

| Type | Meaning | Sources |
|------|---------|---------|
| **BSL** | Liquidity above structure (stops above highs) | EQH clusters; unclustered confirmed Swing Highs |
| **SSL** | Liquidity below structure (stops below lows) | EQL clusters; unclustered confirmed Swing Lows |

---

## Sweep detection

Detection rules are unchanged from Phase 3.3 (wick beyond + reclaim close on a **closed** candle).

### Sweep field semantics (Phase 3.3.1)

| Field | Role |
|-------|------|
| `liquidity_type` | **Authoritative** pool swept (`bsl` \| `ssl`) |
| `reaction_hint` | Contextual ICT interpretation only — **not** a trade signal |
| `direction` | **DEPRECATED** side label retained for API backward compatibility |

| Event | `liquidity_type` | `reaction_hint` | Deprecated `direction` |
|-------|------------------|-----------------|------------------------|
| BSL wick above, close below | `bsl` | `bearish` | `bullish_side` |
| SSL wick below, close above | `ssl` | `bullish` | `bearish_side` |
| Ambiguous dual cross | — | `null` (no sweep emitted) | — |

`reaction_hint` must **not** alter sweep detection or generate LONG/SHORT decisions.

### Not a sweep

| Case | Result |
|------|--------|
| Wick beyond level but close also beyond | **`broken`**, not sweep |
| Wick beyond without meeting penetration | Ignored |
| Forming candle | Provisional only if `include_unconfirmed`; never confirmed |
| Level already swept/broken | No duplicate |
| Same candle crosses active BSL and SSL | Ambiguous diagnostic; no sweep |

---

## Level status transitions

| From | To | Trigger |
|------|----|---------|
| — | `active` | Level created from confirmed swing/cluster |
| `active` | `swept` | Confirmed sweep (wick beyond + reclaim close) |
| `active` | `broken` | Closed candle closes beyond level |
| `swept` / `broken` | (terminal) | No reactivation |

**`invalidated`:** reserved; never assigned in `liq-v1.1.0-balanced`.

---

## REST / WebSocket candle window

- REST `GET /api/v1/liquidity` default `limit` = **500**
- WebSocket liquidity runtime `max_candles` = **500**
- `snapshot.sweep_count` **equals** `len(sweeps)` for the returned analysis window
- Sweeps are **not** independently paginated; changing `limit` changes the candle history analyzed

---

## Historical vs incremental

Full-series analysis and closed-candle prefix recomputation must yield identical event keys, prices, and timestamps for all confirmed events.

---

## Out of scope (Phase 3.4+)

Order Blocks, FVG, ICT sessions, trade decisions, execution.
