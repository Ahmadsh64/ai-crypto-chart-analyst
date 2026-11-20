# Deterministic Trade Plan Engine (Phase 4.3)

Configuration version: **`trade-plan-v1.0.0-balanced`**

Builds a **hypothetical**, risk-aware analytical trade plan from Phase 4.2 strong confluence plus Phase 3.2–3.4 technical levels.

**Analysis only — no orders are executed.** Prices are analytical levels, not guaranteed fills.

This phase does **not** emit LONG / SHORT / WAIT / NO TRADE as final trading decisions.

---

## Eligibility policy

A plan is generated only when **all** of the following hold:

| Rule | Default (`trade-plan-v1.0.0-balanced`) |
|------|----------------------------------------|
| Preliminary assessment | `bullish_confluence` or `bearish_confluence` |
| Assessment strength | `strong` (moderate is blocked) |
| Directional score | ≥ **70** |
| Score margin vs opposite | ≥ **15** |
| Critical HTF conflicts | **blocked** |
| Required TFs ready & fresh | **4H, 1H, 15M** |
| Confirmed directional evidence | required |
| Valid current price | required |

Failing eligibility returns `plan_status=blocked` with explicit `blocking_reasons`.

Statuses: `eligible` | `blocked` | `invalid`.

---

## Entry methodology

Prefer **15M** setup zones matching plan direction:

1. Active Order Blocks (`zone_low`–`zone_high`)
2. Active Fair Value Gaps
3. Partially mitigated / partially filled zones (optional)
4. Structure retest around confirmed unbroken swing
5. **Market-condition** reference only when price is already inside a valid zone (explicit config flag)

Rules:

- Invalidated / fully mitigated / filled zones excluded
- Unconfirmed / provisional zones excluded
- Zone mid must be within `max_entry_distance_atr` (default **3.0**) of price unless price is inside the zone
- Never fabricates entry prices

Fields: `entry_low`, `entry_high`, `entry_reference_price`, `entry_type`, `entry_source`, `source_event_key`, `entry_explanation`.

---

## Stop Loss methodology

Technical invalidation + ATR buffer (`atr_buffer_mult=0.25` on 15M Wilder ATR-14):

- **Bullish:** below entry — prefer zone low − buffer, else confirmed swing low − buffer
- **Bearish:** above entry — prefer zone high + buffer, else confirmed swing high + buffer

Rejects:

- Zero / negative risk distance
- SL on the wrong side of entry
- Distance outside `[min_stop_distance_atr, max_stop_distance_atr]` = `[0.15, 4.0]` when ATR is available
- SL deep inside the entry zone without zone-edge justification

---

## Take Profit methodology

Up to **TP1 / TP2 / TP3** from real levels only:

- Active BSL (bullish plans) / SSL (bearish plans) on 1H & 15M
- Confirmed opposing swing highs/lows
- Opposing active/partial OB/FVG boundaries

Rules:

- Correct side of entry; ordered progressively
- Near-duplicates collapsed (`near_duplicate_pct=0.1%`)
- **Do not invent** farther prices to force RR
- Primary target must meet `minimum_primary_target_rr = 2.0` or the plan is rejected

---

## Risk / reward

LONG: `risk = entry_ref − SL`, `reward = TP − entry_ref`, `RR = reward / risk`  
SHORT: mirrored.

Internal math uses unrounded floats; display may round.

---

## Position sizing (hypothetical)

```
risk_amount = account_balance * (risk_percent / 100)
position_size = risk_amount / ( |entry_ref − SL| * contract_multiplier )
```

Defaults: balance **10000**, risk **1%**, multiplier **1** (linear base-asset model).

- No real exchange balances
- No leverage recommendation
- Fees / funding / slippage not modeled
- Missing contract metadata → `sizing_available=false`

---

## Spot vs Futures

| Market | Behavior |
|--------|----------|
| Spot bullish | Hypothetical long inventory sizing |
| Spot bearish | Allowed as **hypothetical downside scenario** with explicit warning that Spot shorts are not standard Spot trades |
| Futures / linear | Hypothetical long or short; no leverage advice |

---

## Validation

Dedicated layer checks eligibility, entry integrity, SL side, TP order/side, RR floor, sizing, and Spot short warnings. Any blocking error → not `eligible`.

---

## API

`GET /api/v1/trade-plan?exchange&symbol&market_type&account_balance&risk_percent`

Returns structured response even when blocked.

## WebSocket

Reuses `/ws/market`:

- `subscribe_trade_plan` / `unsubscribe_trade_plan`
- `trade_plan_update` on **confirmed** MTF-ladder candle closes only
- Forming candles never promote a plan
- Payload includes `configuration_version` and `analysis_timestamp`

---

## Data quality

Consumes Phase 4.1 readiness/staleness. Missing ATR, missing price, or incomplete required TFs appear in `data_quality.limitations` / blockers. Missing evidence ≠ neutral confirmation.

---

## Known limitations

- No final LONG/SHORT/WAIT/NO TRADE decision engine (later phase)
- No automated execution or exchange order APIs
- Indicators unused except ATR for buffers / distance gates
- Soft ATR / distance / RR parameters are opinionated but versioned
- Contract multipliers beyond `1.0` require future instrument metadata
