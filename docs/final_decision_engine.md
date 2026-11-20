# Final Trading Decision Engine (Phase 4.4)

Configuration version: **`decision-v1.0.0-balanced`**

Combines Phase 4.1–4.3 outputs into one explainable analytical decision:

`LONG` | `SHORT` | `WAIT` | `NO TRADE`

**Analysis only — no orders are executed.** Analytical conditions do not guarantee execution or profit.

---

## Decision labels

| Decision | Meaning |
|----------|---------|
| `LONG` | Valid bullish plan + strong confluence + price in entry zone + confirmed 5M entry |
| `SHORT` | Same for bearish (Futures/linear only as executable analytical short) |
| `WAIT` | Valid directional setup/plan, but entry confirmation or price-in-zone missing |
| `NO TRADE` | Invalid, insufficient, contradictory, expired, Spot-restricted short, or unsafe |

---

## Priority order

1. Expired setup → `NO TRADE` (`expired`)
2. Invalidated setup / SL breach → `NO TRADE` (`invalidated`)
3. Invalid eligibility (data/conflict/weak confluence/invalid plan/RR) → `NO TRADE`
4. Ambiguous dual-direction validity → `NO TRADE`
5. Spot bearish with full confirmation → `NO TRADE` (not `SHORT`)
6. Valid setup without 5M confirmation → `WAIT`
7. Valid setup, price outside entry zone → `WAIT`
8. Otherwise → `LONG` / `SHORT`

Failed LONG/SHORT conditions become `WAIT` only when the setup remains fundamentally valid.

---

## Entry confirmation (5M)

Closed-candle evidence only (`include_unconfirmed=False` path):

- Confirmed MSS matching plan direction
- Confirmed BOS matching plan direction
- Confirmed liquidity sweep with correct `reaction_hint` (SSL→bullish, BSL→bearish)

Within `max_confirmation_age_candles` (default **6**). Deduped by `event_key`. Forming candles never confirm.

Price must also be **inside** the planned entry zone for LONG/SHORT (`require_price_inside_entry_zone=true`).

---

## Lifecycle

| State | When |
|-------|------|
| `setup_detected` | Weak/partial detection path |
| `awaiting_confirmation` | Valid setup, waiting for 5M / price-in-zone |
| `entry_confirmed` | LONG or SHORT issued |
| `invalidated` | Conflicts, SL breach, Spot short block, bad plan |
| `expired` | Age > `max_setup_age_hours` (12h) or > `max_setup_age_candles` (16×15M) |

---

## Spot vs Futures

| | Spot | Futures / linear |
|--|------|------------------|
| LONG | Allowed when conditions pass | Allowed |
| SHORT | **Never** emitted; confirmed bearish → `NO TRADE` with Spot explanation | Allowed |
| Leverage | N/A | Not recommended |

---

## API / WebSocket

- `GET /api/v1/decision?exchange&symbol&market_type&account_balance&risk_percent`
- `subscribe_decision` → `decision_update` on confirmed MTF-ladder closes only

Reuses shared `build_analysis_context` (single fetch) → confluence + trade plan + decision.

---

## Known limitations

- No order execution or fill claims
- No leverage automation
- No AI decisioning
- Soft confirmation age / expiration parameters are opinionated but versioned
- Spot shorts remain analytical via Trade Plan panel, not Final Decision `SHORT`
