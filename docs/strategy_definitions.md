# Strategy Definitions

Exact detection rules are implemented in Phase 3+. This document records the locked definitions so AI explanations and backtests stay aligned.

Configuration version for Market Structure (Phase 3.2): **`ms-v1.0.0-balanced`**

## Market structure (Phase 3.2 — implemented)

### Configuration defaults

| Setting | Value |
|---------|-------|
| Swing left / right bars | 3 / 3 |
| Detection mode | `BALANCED` (only mode implemented) |
| Structure confirmation | Candle **CLOSE** |
| Closed candles only | Yes (forming bars ignored for confirmed signals) |
| Timestamps | UTC |
| Displacement (MSS) | Body ≥ `1.5 × ATR(14)` |
| Equal high/low tie rule | **Strict inequality** — equal neighbour disqualifies the pivot |

Every analysis response embeds `config_version` + full settings snapshot so config changes cannot silently rewrite history.

### Swing High / Swing Low

- **Swing High** at index `i`: `high[i]` is **strictly greater** than highs of the `left` bars before and `right` bars after.
- **Swing Low** at index `i`: `low[i]` is **strictly less** than lows of the `left` bars before and `right` bars after.
- A pivot is **not confirmed** until all `right` subsequent candles exist and are closed.
- `candle_timestamp` = pivot bar open time; `confirmation_timestamp` = open time of bar `i + right`.
- Equal extremes never create duplicate pivots (strict inequality).

### Classification

Relative to the previous confirmed swing of the **same kind**:

| Label | Rule |
|-------|------|
| HH | Swing High price > previous Swing High |
| LH | Swing High price ≤ previous Swing High |
| HL | Swing Low price > previous Swing Low |
| LL | Swing Low price ≤ previous Swing Low |

First swing of each kind is unclassified (`classification=null`).

### Structure bias

- Starts as **`undefined`**.
- From swings: **bullish** when latest classified SH is HH **and** latest classified SL is HL; **bearish** when LH **and** LL.
- Close-breaks also set/flip bias (see BOS / CHoCH).

### Active unbroken levels (API snapshot)

These are **break targets**, not generic S/R labels:

| Field | Meaning |
|-------|---------|
| `active_unbroken_swing_high` | Latest confirmed Swing High not yet broken by a **close** (bullish BOS/CHoCH target) |
| `active_unbroken_swing_low` | Latest confirmed Swing Low not yet broken by a **close** (bearish BOS/CHoCH target) |
| `active_bullish_level` | Legacy alias of `active_unbroken_swing_high` |
| `active_bearish_level` | Legacy alias of `active_unbroken_swing_low` |

### Same-candle ambiguous dual break

When **one closed candle**:

1. Wicks **above** the active unbroken Swing High, **and**
2. Wicks **below** the active unbroken Swing Low, **and**
3. **Closes inside** the open structure range `(SL, SH)`,

then the engine emits an **`ambiguous_dual_break`** diagnostic only:

- No bullish/bearish BOS
- No CHoCH / MSS
- Structure bias is **unchanged**
- Both crossed levels and the candle timestamp are recorded

This avoids arbitrarily choosing a direction when both sides are only wicked.

### BOS (Break of Structure)

**Valid BOS**

- Bullish: closed candle **close >** latest unbroken confirmed Swing High.
- Bearish: closed candle **close <** latest unbroken confirmed Swing Low.
- Occurs **with** the current bias, or while bias is still `undefined` (first break is always BOS, never CHoCH).

**Invalid / not BOS**

- Wick beyond the level with close still inside (wick-only).
- Repeat break of an already-broken swing level (each swing key broken once).
- Forming (unclosed) candle.
- Ambiguous dual-wick candle (see above).

Chart display: each BOS is a **time-scoped horizontal segment** from the break candle to the next superseding/opposing structure event (or to the latest candle if still active). Invalidated/superseded segments use a muted style; active segments are emphasized. No invented invalidation events — ends are derived only from subsequent BOS/CHoCH timestamps.

### CHoCH (Change of Character)

**Valid CHoCH**

- Bullish: close above relevant SH while established bias is **bearish**.
- Bearish: close below relevant SL while established bias is **bullish**.

**Not CHoCH**

- Any break while bias is `undefined` (recorded as BOS instead).
- Breaks in the same direction as the current bias (BOS continuation).

After CHoCH, bias flips to the break direction. Events include `previous_bias` and `new_bias`.

### MSS (Market Structure Shift)

**Valid MSS**

1. A valid **CHoCH** on that candle, **and**
2. Displacement: `abs(close - open) >= 1.5 × ATR(14)` at that bar.

**Not MSS**

- CHoCH without displacement.
- Missing / non-finite ATR (never invent ATR → no MSS).
- BOS-only breaks.

### Examples

**Valid bullish BOS:** Bias undefined or bullish; latest SH at 120; candle closes at 124.

**Invalid BOS:** High=130, close=118 vs SH=120 (wick-only).

**Valid bearish CHoCH:** Bias bullish after BOS; latest unbroken SL at 104; candle closes at 89 → CHoCH, bias → bearish.

**Valid MSS:** Same CHoCH candle with body ≥ 1.5×ATR(14).

**Invalid MSS:** CHoCH with body 0.8 while ATR=10 (body < 15).

---

## Liquidity (Phase 3.3.1 — implemented)

Full rules: [liquidity_definitions.md](liquidity_definitions.md) (`liq-v1.1.0-balanced`).

- **EQH / EQL:** Diameter-constrained clusters (`max−min ≤ T`); chronological greedy assignment; median representative level.
- **BSL / SSL:** EQH/EQL pools plus individual unclustered swing highs/lows.
- **Sweep:** Wick beyond an active level with reclaim close; close-through is `broken`, not a sweep.
- **`liquidity_type`:** Authoritative pool (`bsl`/`ssl`). **`reaction_hint`:** contextual ICT reaction only (bearish after BSL sweep, bullish after SSL) — not a trade signal. Deprecated `direction` retained for compatibility.
- **Ambiguous:** Same candle crossing active BSL and SSL → diagnostic only (`reaction_hint` null).
- **Window:** REST default `limit` and WS `max_candles` share `500`; `sweep_count == len(sweeps)` for that window.

## Order blocks & FVG (Phase 3.4 — `obfvg-v1.0.0-balanced`)

Canonical rules: [ob_fvg_definitions.md](ob_fvg_definitions.md).

- **Order Block:** Last opposing closed candle before a displacement-qualified confirmed BOS/MSS; zone = full source candle `[low, high]`.
- **FVG:** Three consecutive closed candles with a non-overlapping gap meeting ATR-based minimum size; lifecycle tracks fill % and invalidation.
- Confirmed events use closed candles only; provisional events are separate. No look-ahead.

## ICT sessions (timezone-aware) — later

| Session | Typical UTC window |
|---------|--------------------|
| Asia | 00:00–08:00 |
| London | 07:00–16:00 |
| New York | 12:00–21:00 |

## Decision outputs (Phase 4 — later)

`LONG` | `SHORT` | `WAIT` | `NO TRADE`

Scores are weighted and transparent. High technical scores are **not** success probabilities.
