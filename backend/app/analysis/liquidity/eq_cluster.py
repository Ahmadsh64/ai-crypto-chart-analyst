"""EQH / EQL clustering with diameter constraint (Phase 3.3.1)."""

from __future__ import annotations

import hashlib
from datetime import datetime

from app.analysis.liquidity.config import LiquidityConfig
from app.analysis.liquidity.models import EqualExtremeCluster, SwingContribution
from app.analysis.liquidity.tolerance import diameter_tolerance, median_price
from app.analysis.market_structure.models import SwingKind, SwingPoint
from app.analysis.market_structure.timestamps import ensure_utc
from app.exchanges.types import ExchangeId, MarketType, Timeframe


def _member(swing: SwingPoint) -> SwingContribution:
    return SwingContribution(
        swing_key=swing.event_key,
        price=float(swing.price),
        candle_timestamp=ensure_utc(swing.candle_timestamp, field="candle_timestamp"),
        confirmation_timestamp=ensure_utc(
            swing.confirmation_timestamp, field="confirmation_timestamp"
        ),
    )


def _stable_cluster_key(
    *,
    kind: str,
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    timeframe: Timeframe,
    seed_keys: list[str],
) -> str:
    """
    Deterministic id from the two earliest seed members (by confirmation, then key).

    When the cluster grows, the key stays stable so updates do not duplicate clusters.
    """
    seeds = sorted(seed_keys)[:2]
    digest = hashlib.sha1("|".join(seeds).encode("utf-8")).hexdigest()[:16]
    return (
        f"{kind}:{exchange.value}:{market_type.value}:{symbol.upper()}:"
        f"{timeframe.value}:{digest}"
    )


def _atr_at(
    ts: datetime,
    atr_by_index: list[float | None],
    index_by_confirm_ts: dict[datetime, int],
) -> float | None:
    idx = index_by_confirm_ts.get(ts)
    if idx is None or not (0 <= idx < len(atr_by_index)):
        return None
    return atr_by_index[idx]


def _can_add(
    members: list[SwingPoint],
    candidate: SwingPoint,
    *,
    atr_by_index: list[float | None],
    index_by_confirm_ts: dict[datetime, int],
    cfg: LiquidityConfig,
) -> tuple[bool, float, bool]:
    """Return (fits, tolerance_used, atr_available) if candidate keeps diameter ≤ T."""
    prices = [float(s.price) for s in members] + [float(candidate.price)]
    latest = max(
        ensure_utc(s.confirmation_timestamp, field="confirmation_timestamp")
        for s in [*members, candidate]
    )
    atr_val = _atr_at(latest, atr_by_index, index_by_confirm_ts)
    tol, atr_ok = diameter_tolerance(prices, atr_val, cfg)
    diam = max(prices) - min(prices)
    return diam <= tol + 1e-12, tol, atr_ok


def cluster_equal_extremes(
    swings: list[SwingPoint],
    *,
    kind: SwingKind,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    timeframe: Timeframe,
    atr_by_index: list[float | None],
    index_by_confirm_ts: dict[datetime, int],
    cfg: LiquidityConfig,
    as_of: datetime | None = None,
) -> list[EqualExtremeCluster]:
    """
    Build EQH or EQL clusters from confirmed swings available at `as_of`.

    Diameter rule (liq-v1.1.0-balanced):
        max(member_prices) - min(member_prices) <= T

    Strategy — chronological greedy assignment (deterministic):
    1. Consider only confirmed swings with confirmation_timestamp <= as_of.
    2. Sort by (confirmation_timestamp ASC, event_key ASC).
    3. Assign each swing to at most one cluster:
       - Eligible clusters are those where adding the swing keeps diameter ≤ T
         (T from ATR at the latest confirmation among resulting members, else fallback %).
       - Tie-break when multiple eligible clusters:
         a. smallest resulting diameter
         b. earliest first-member confirmation_timestamp
         c. lexicographically smallest first-member event_key
       - If none eligible → start a new singleton group.
    4. Emit groups with member_count >= eq_cluster_min_swings.
    5. Never merge two existing clusters (avoids silent diameter violations).
    """
    symbol_u = symbol.upper()
    pool: list[SwingPoint] = []
    for s in swings:
        if not s.confirmed or s.kind != kind:
            continue
        conf = ensure_utc(s.confirmation_timestamp, field="confirmation_timestamp")
        if as_of is not None and conf > ensure_utc(as_of, field="as_of"):
            continue
        pool.append(s)

    if len(pool) < cfg.eq_cluster_min_swings:
        return []

    pool.sort(
        key=lambda s: (
            ensure_utc(s.confirmation_timestamp, field="confirmation_timestamp"),
            s.event_key,
        )
    )

    # Each group is a list of SwingPoint; swing appears in at most one group.
    groups: list[list[SwingPoint]] = []

    for swing in pool:
        eligible: list[tuple[float, datetime, str, int, float, bool]] = []
        for gi, members in enumerate(groups):
            fits, tol, atr_ok = _can_add(
                members,
                swing,
                atr_by_index=atr_by_index,
                index_by_confirm_ts=index_by_confirm_ts,
                cfg=cfg,
            )
            if not fits:
                continue
            prices = [float(m.price) for m in members] + [float(swing.price)]
            diam = max(prices) - min(prices)
            first = members[0]
            first_conf = ensure_utc(
                first.confirmation_timestamp, field="confirmation_timestamp"
            )
            eligible.append((diam, first_conf, first.event_key, gi, tol, atr_ok))

        if eligible:
            eligible.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
            _, _, _, gi, _, _ = eligible[0]
            groups[gi].append(swing)
        else:
            groups.append([swing])

    kind_label = "eqh" if kind == SwingKind.HIGH else "eql"
    out: list[EqualExtremeCluster] = []

    for members_swings in groups:
        if len(members_swings) < cfg.eq_cluster_min_swings:
            continue
        members_swings = sorted(
            members_swings,
            key=lambda s: (
                ensure_utc(s.confirmation_timestamp, field="confirmation_timestamp"),
                s.event_key,
            ),
        )
        members = [_member(s) for s in members_swings]
        prices = [m.price for m in members]
        level = median_price(prices)
        min_p = min(prices)
        max_p = max(prices)
        price_range = max_p - min_p
        first_detection = members[cfg.eq_cluster_min_swings - 1].confirmation_timestamp
        latest = max(m.confirmation_timestamp for m in members)
        seed_keys = [m.swing_key for m in members[: cfg.eq_cluster_min_swings]]
        event_key = _stable_cluster_key(
            kind=kind_label,
            exchange=exchange,
            market_type=market_type,
            symbol=symbol_u,
            timeframe=timeframe,
            seed_keys=seed_keys,
        )
        atr_val = _atr_at(latest, atr_by_index, index_by_confirm_ts)
        tol_used, atr_any = diameter_tolerance(prices, atr_val, cfg)

        out.append(
            EqualExtremeCluster(
                event_key=event_key,
                exchange=exchange,
                symbol=symbol_u,
                market_type=market_type,
                timeframe=timeframe,
                kind=kind_label,
                level=level,
                representative_level=level,
                min_price=min_p,
                max_price=max_p,
                price_range=price_range,
                members=members,
                member_count=len(members),
                first_detection_timestamp=first_detection,
                latest_confirmation_timestamp=latest,
                config_version=cfg.config_version,
                tolerance_used=tol_used,
                atr_available=atr_any,
            )
        )

    out.sort(key=lambda c: (c.first_detection_timestamp, c.event_key))
    return out
