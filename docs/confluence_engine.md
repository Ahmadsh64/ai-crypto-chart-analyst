# Deterministic Confluence & Scoring Engine (Phase 4.2)

Configuration version: **`confluence-v1.0.0-balanced`**

Consumes Phase 4.1 MTF orchestration plus Phase 3.2–3.4 engines. **No LONG/SHORT/WAIT/NO TRADE**, entries, stops, targets, or AI decisions.

---

## Evidence categories

| Category ID | Timeframes | Weight | Purpose |
|-------------|------------|-------:|---------|
| `htf_context` | 4H | 25 | Higher timeframe directional context |
| `market_structure` | 1H | 25 | Medium-term structure |
| `liquidity` | 1H, 15M | 20 | Liquidity pools & confirmed sweeps |
| `ob_fvg` | 15M | 20 | Active / partially active zones |
| `ltf_confirmation` | 5M | 10 | Lower-TF support / conflict |
| **Total** | | **100** | |

Weights are configurable and validated to sum to 100.

---

## Evidence mapping (actual engine fields)

### Structure (3.2)

| Source | Direction | Strength | Notes |
|--------|-----------|---------:|-------|
| `snapshot.bias` bullish/bearish | bias | 0.55 | Ignored if `undefined` |
| Latest confirmed `MSSEvent` | `direction` | 1.00 | Confirmed closed-candle event |
| Latest `StructureBreak` BOS | `direction` | 0.85 | |
| Latest `CHoCHEvent` | `direction` | 0.75 | |
| Recent confirmed swing labels HH/HL | bullish | 0.40 | Last up to 4 classified swings |
| Recent LH/LL | bearish | 0.40 | |

Unconfirmed swings are **excluded**. Wick-only dual breaks (`AmbiguousDualBreak`) are excluded.

### Liquidity (3.3.1)

| Source | Direction | Strength | Notes |
|--------|-----------|---------:|-------|
| Confirmed `LiquiditySweep` | `reaction_hint` | 0.85 | BSL→bearish, SSL→bullish |
| Active BSL/SSL/EQH/EQL level | contextual | 0.15 | Not a sweep; weak context only |
| Ambiguous cross | — | — | Excluded (`reaction_hint` null) |
| Broken (not swept) | — | — | Excluded |

### OB / FVG (3.4)

| Source | Status | Strength |
|--------|--------|---------:|
| OB | `active` | 0.70 |
| OB | `partially_mitigated` | 0.45 |
| OB | `mitigated` / `invalidated` | excluded |
| FVG | `active` | 0.60 |
| FVG | `partially_filled` | 0.35 |
| FVG | `filled` / `invalidated` | excluded |

Forming / provisional FVG (`confirmed=false`) excluded.

### Indicators (3.1)

**Not used** for directional confluence in v1.0.0 — no documented directional interpretation exists.

---

## Normalization

Each `EvidenceItem` includes: `evidence_id`, `evidence_type`, `category`, `timeframe`, `direction`, `strength` ∈ [0,1], `confidence` ∈ [0,1], `source_event_key`, `source_timestamp`, `is_confirmed`, `is_active`, `explanation`, `metadata`.

`confidence` defaults: confirmed closed-candle events = `1.0`; weak contextual levels = `0.5`.

---

## Deduplication

Dedup key:

```
{category}:{timeframe}:{source_event_key}
```

Same underlying `event_key` cannot contribute twice (REST + WS, repeated snapshots). Distinct events that share a price level are **not** collapsed.

---

## Scoring formula

For each side ∈ {bullish, bearish} and each category:

1. Collect deduped evidence with matching `direction`.
2. Sort by `strength × confidence` descending.
3. Apply geometric decay:  
   `effective = Σ strength_i × confidence_i × decay^i` with `decay = 0.5`.
4. Saturate: `unit = min(1.0, effective / saturation)` with `saturation = 2.0`.
5. `category_contribution = unit × category_weight`.

```
side_score = min(100, Σ category_contribution)
```

A category never exceeds its configured weight. Correlated stacked evidence saturates via decay + saturation.

---

## Preliminary assessment thresholds

Labels only:

- `bullish_confluence`
- `bearish_confluence`
- `mixed`
- `insufficient_evidence`
- `data_unavailable`

Rules (`confluence-v1.0.0-balanced`):

| Condition | Result |
|-----------|--------|
| Overall MTF unavailable or required TFs (4H+1H) not ready | `data_unavailable` / `insufficient_evidence` |
| Critical HTF conflict (4H vs 1H opposite structure) | `mixed` |
| Leading score ≥ 70 and lead−trail ≥ 15, HTF not opposing | directional confluence |
| Leading score ≥ 55 and lead−trail ≥ 10, HTF not opposing | directional confluence (moderate) |
| Otherwise with some evidence | `mixed` |
| No confirmed directional evidence | `insufficient_evidence` |

Lower TF cannot erase a higher-TF conflict.

---

## Conflict rules

| Type | Severity | Trigger |
|------|----------|---------|
| `htf_structure_conflict` | `critical` | 4H bias/MSS/BOS vs 1H opposite |
| `structure_setup_conflict` | `high` | 1H structure vs 15M OB/FVG net side |
| `setup_entry_conflict` | `medium` | 15M vs 5M net sides |
| `liquidity_dual` | `medium` | Recent confirmed bullish and bearish sweeps |
| `ob_fvg_dual` | `medium` | Active bullish and bearish zones both material |
| `stale_timeframe` | `high` | Required TF stale |
| `missing_timeframe` | `high`/`critical` | Required TF missing |

Conflicts are preserved; not auto-resolved by score.

---

## Data quality

From Phase 4.1: `is_ready`, `is_stale`, `data_quality`, `unavailable_timeframes`. Missing evidence ≠ neutral confirmation. Distinguishes excluded (invalidated / unconfirmed / duplicate) vs unavailable.

---

## API / WebSocket

- `GET /api/v1/confluence?exchange&symbol&market_type`
- WS: `subscribe_confluence` → `confluence_update` (recalc on confirmed candle changes for ladder TFs)

---

## Known limitations

- No final trade decision (Phase 4.3+).
- Indicators unused for direction in this version.
- Soft saturation parameters are configurable but opinionated.
- Does not invent HTF bias when structure bias is `undefined`.
