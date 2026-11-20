"""Drawdown calculations from equity curves (Phase 5.2.4)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.replay.analytics.metrics_calculator import available, unavailable
from app.replay.analytics.models import DrawdownPoint, DrawdownSummary, EquityCurve

ZERO = Decimal("0")


def _q(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.00000001"))


def compute_drawdown(curve: EquityCurve) -> DrawdownSummary:
    """
    Drawdown = running peak equity − current equity (≥ 0).
    Requires explicit initial_equity on the curve.
    """
    if not curve.available:
        return DrawdownSummary(
            available=False,
            unavailable_reason=curve.unavailable_reason or "equity_curve_unavailable",
        )
    if curve.initial_equity is None:
        return DrawdownSummary(
            available=False,
            unavailable_reason="initial_equity_not_configured",
        )

    if not curve.points:
        return DrawdownSummary(
            available=True,
            absolute_drawdown=ZERO,
            max_drawdown=ZERO,
            current_drawdown=ZERO,
            drawdown_pct=available(ZERO),
            max_drawdown_pct=available(ZERO),
            current_drawdown_pct=available(ZERO),
        )

    series: list[DrawdownPoint] = []
    peak = curve.initial_equity
    peak_ts: datetime | None = None
    max_dd = ZERO
    max_peak_ts: datetime | None = None
    max_trough_ts: datetime | None = None
    max_peak_equity = peak

    for p in curve.points:
        eq = p.equity
        if eq is None:
            continue
        if eq > peak:
            peak = eq
            peak_ts = p.timestamp

        dd = _q(peak - eq)
        if dd < 0:
            dd = ZERO

        dd_pct: Decimal | None
        if peak > 0:
            dd_pct = _q(dd / peak * Decimal("100"))
        else:
            dd_pct = None

        series.append(
            DrawdownPoint(
                timestamp=p.timestamp,
                equity=eq,
                peak_equity=peak,
                drawdown=dd,
                drawdown_pct=dd_pct,
            )
        )

        if dd > max_dd:
            max_dd = dd
            max_peak_ts = peak_ts
            max_trough_ts = p.timestamp
            max_peak_equity = peak

    recovery_ts = None
    if max_dd > 0 and max_trough_ts is not None:
        after = False
        for p in curve.points:
            if p.timestamp >= max_trough_ts:
                if p.timestamp == max_trough_ts:
                    after = True
                    continue
                after = True
            if not after:
                continue
            if p.equity is not None and p.equity >= max_peak_equity:
                recovery_ts = p.timestamp
                break

    last = series[-1]
    current_dd = last.drawdown

    if last.peak_equity and last.peak_equity > 0 and last.drawdown_pct is not None:
        current_pct = available(last.drawdown_pct)
        abs_pct = available(last.drawdown_pct)
    elif last.peak_equity == 0:
        current_pct = unavailable("zero_peak_equity")
        abs_pct = unavailable("zero_peak_equity")
    else:
        current_pct = available(ZERO)
        abs_pct = available(ZERO)

    if max_dd > 0:
        trough = next((s for s in series if s.timestamp == max_trough_ts), None)
        if trough and trough.drawdown_pct is not None:
            max_pct = available(trough.drawdown_pct)
        elif trough and trough.peak_equity == 0:
            max_pct = unavailable("zero_peak_equity")
        else:
            max_pct = unavailable("zero_peak_equity")
    else:
        max_pct = available(ZERO)

    return DrawdownSummary(
        available=True,
        absolute_drawdown=current_dd,
        drawdown_pct=abs_pct,
        max_drawdown=_q(max_dd),
        max_drawdown_pct=max_pct,
        peak_timestamp=max_peak_ts if max_dd > 0 else None,
        trough_timestamp=max_trough_ts if max_dd > 0 else None,
        recovery_timestamp=recovery_ts,
        current_drawdown=current_dd,
        current_drawdown_pct=current_pct,
        series=series,
    )
