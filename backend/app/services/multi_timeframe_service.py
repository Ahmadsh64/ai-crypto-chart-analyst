"""REST service for Multi-Timeframe orchestration (Phase 4.1)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.analysis.multi_timeframe.config import DEFAULT_MTF_CONFIG, MultiTimeframeConfig
from app.analysis.multi_timeframe.models import TimeframeSeriesSummary
from app.analysis.multi_timeframe.orchestrator import build_snapshot, evaluate_timeframe_series
from app.api.schemas.multi_timeframe import MultiTimeframeResponse
from app.exchanges.exceptions import ExchangeError
from app.exchanges.manager import get_exchange_manager
from app.exchanges.types import ExchangeId, MarketType, Timeframe


async def _fetch_one(
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    timeframe: Timeframe,
    limit: int,
) -> tuple[Timeframe, list | Exception]:
    try:
        candles = await get_exchange_manager().fetch_ohlcv(
            exchange,
            symbol,
            timeframe,
            market_type,
            limit=limit,
        )
        return timeframe, candles
    except Exception as exc:  # noqa: BLE001 — per-TF isolation
        return timeframe, exc


async def compute_multi_timeframe_response(
    *,
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    config: MultiTimeframeConfig | None = None,
    as_of: datetime | None = None,
) -> MultiTimeframeResponse:
    cfg = config or DEFAULT_MTF_CONFIG
    now = as_of or datetime.now(timezone.utc)

    tasks = [
        _fetch_one(
            exchange,
            market_type,
            symbol,
            tf,
            cfg.history_for(tf).fetch_limit,
        )
        for tf in cfg.timeframes
    ]
    results = await asyncio.gather(*tasks)

    series: dict[Timeframe, TimeframeSeriesSummary] = {}
    for timeframe, payload in results:
        if isinstance(payload, Exception):
            detail = str(payload) or payload.__class__.__name__
            if isinstance(payload, ExchangeError):
                detail = str(payload)
            series[timeframe] = evaluate_timeframe_series(
                [],
                timeframe=timeframe,
                exchange=exchange,
                symbol=symbol,
                market_type=market_type,
                as_of=now,
                config=cfg,
                error=detail,
            )
        else:
            series[timeframe] = evaluate_timeframe_series(
                payload,
                timeframe=timeframe,
                exchange=exchange,
                symbol=symbol,
                market_type=market_type,
                as_of=now,
                config=cfg,
            )

    snapshot = build_snapshot(
        series,
        exchange=exchange,
        symbol=symbol,
        market_type=market_type,
        as_of=now,
        config=cfg,
    )

    return MultiTimeframeResponse(
        exchange=exchange,
        symbol=symbol,
        market_type=market_type,
        calculated_at=snapshot.calculated_at,
        data_source=f"{exchange.value}:{market_type.value}",
        config=cfg.snapshot(),
        snapshot=snapshot,
        timeframes=snapshot.timeframes,
        sync=snapshot.sync,
        metadata={
            **snapshot.metadata,
            "partial_failures": [
                {
                    "timeframe": s.timeframe.value,
                    "data_quality": s.data_quality,
                    "detail": s.status_detail,
                }
                for s in snapshot.timeframes
                if not s.is_ready
            ],
        },
    )
