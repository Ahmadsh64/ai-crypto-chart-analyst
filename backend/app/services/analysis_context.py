"""Shared MTF + per-TF analysis context for confluence and trade plan (Phases 4.2–4.3)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from app.analysis.confluence import analyze_confluence
from app.analysis.confluence.config import DEFAULT_CONFLUENCE_CONFIG, ConfluenceConfig
from app.analysis.confluence.engine import TimeframeAnalysisBundle
from app.analysis.confluence.models import ConfluenceResult
from app.analysis.liquidity import analyze_liquidity
from app.analysis.market_structure import analyze_market_structure
from app.analysis.multi_timeframe.config import DEFAULT_MTF_CONFIG
from app.analysis.multi_timeframe.models import MultiTimeframeSnapshot
from app.analysis.multi_timeframe.orchestrator import build_snapshot, evaluate_timeframe_series
from app.analysis.ob_fvg import analyze_ob_fvg
from app.exchanges.manager import get_exchange_manager
from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe


@dataclass
class AnalysisContext:
    mtf_snapshot: MultiTimeframeSnapshot
    bundles: dict[Timeframe, TimeframeAnalysisBundle]
    candles_by_tf: dict[Timeframe, list[Candle]]
    confluence: ConfluenceResult
    as_of: datetime


async def _fetch_tf(
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    timeframe: Timeframe,
    limit: int,
) -> tuple[Timeframe, list[Candle] | Exception]:
    try:
        candles = await get_exchange_manager().fetch_ohlcv(
            exchange, symbol, timeframe, market_type, limit=limit
        )
        return timeframe, candles
    except Exception as exc:  # noqa: BLE001
        return timeframe, exc


def analyze_bundle(
    candles: list[Candle],
    *,
    exchange: ExchangeId,
    symbol: str,
    market_type: MarketType,
    timeframe: Timeframe,
    need_structure: bool,
    need_liquidity: bool,
    need_ob_fvg: bool,
) -> TimeframeAnalysisBundle:
    structure = liquidity = ob_fvg = None
    structure_error = liquidity_error = ob_fvg_error = None
    closed = [c for c in candles if c.is_closed]

    if need_structure:
        try:
            structure = analyze_market_structure(
                closed,
                exchange=exchange,
                symbol=symbol,
                market_type=market_type,
                timeframe=timeframe,
                include_unconfirmed=False,
            )
        except Exception as exc:  # noqa: BLE001
            structure_error = str(exc)

    if need_liquidity:
        try:
            swings = structure.swings if structure is not None else None
            liquidity = analyze_liquidity(
                closed,
                exchange=exchange,
                symbol=symbol,
                market_type=market_type,
                timeframe=timeframe,
                swings=swings,
                include_unconfirmed=False,
            )
        except Exception as exc:  # noqa: BLE001
            liquidity_error = str(exc)

    if need_ob_fvg:
        try:
            bos = structure.bos_events if structure is not None else None
            mss = structure.mss_events if structure is not None else None
            ob_fvg = analyze_ob_fvg(
                closed,
                exchange=exchange,
                symbol=symbol,
                market_type=market_type,
                timeframe=timeframe,
                bos_events=bos,
                mss_events=mss,
                include_unconfirmed=False,
            )
        except Exception as exc:  # noqa: BLE001
            ob_fvg_error = str(exc)

    return TimeframeAnalysisBundle(
        structure=structure,
        liquidity=liquidity,
        ob_fvg=ob_fvg,
        structure_error=structure_error,
        liquidity_error=liquidity_error,
        ob_fvg_error=ob_fvg_error,
    )


async def build_analysis_context(
    *,
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    confluence_config: ConfluenceConfig | None = None,
    as_of: datetime | None = None,
) -> AnalysisContext:
    """Fetch each MTF ladder series once, run engines, and score confluence."""
    cfg = confluence_config or DEFAULT_CONFLUENCE_CONFIG
    mtf_cfg = DEFAULT_MTF_CONFIG
    now = as_of or datetime.now(timezone.utc)

    ladder = list(mtf_cfg.timeframes)
    fetched = await asyncio.gather(
        *[
            _fetch_tf(
                exchange,
                market_type,
                symbol,
                tf,
                mtf_cfg.history_for(tf).fetch_limit,
            )
            for tf in ladder
        ]
    )

    candles_by_tf: dict[Timeframe, list[Candle]] = {}
    series = {}
    for tf, payload in fetched:
        if isinstance(payload, Exception):
            series[tf] = evaluate_timeframe_series(
                [],
                timeframe=tf,
                exchange=exchange,
                symbol=symbol,
                market_type=market_type,
                as_of=now,
                config=mtf_cfg,
                error=str(payload),
            )
            candles_by_tf[tf] = []
        else:
            candles_by_tf[tf] = payload
            series[tf] = evaluate_timeframe_series(
                payload,
                timeframe=tf,
                exchange=exchange,
                symbol=symbol,
                market_type=market_type,
                as_of=now,
                config=mtf_cfg,
            )

    mtf_snapshot = build_snapshot(
        series,
        exchange=exchange,
        symbol=symbol,
        market_type=market_type,
        as_of=now,
        config=mtf_cfg,
    )

    bundles: dict[Timeframe, TimeframeAnalysisBundle] = {
        Timeframe.H4: analyze_bundle(
            candles_by_tf.get(Timeframe.H4, []),
            exchange=exchange,
            symbol=symbol,
            market_type=market_type,
            timeframe=Timeframe.H4,
            need_structure=True,
            need_liquidity=False,
            need_ob_fvg=False,
        ),
        Timeframe.H1: analyze_bundle(
            candles_by_tf.get(Timeframe.H1, []),
            exchange=exchange,
            symbol=symbol,
            market_type=market_type,
            timeframe=Timeframe.H1,
            need_structure=True,
            need_liquidity=True,
            need_ob_fvg=False,
        ),
        Timeframe.M15: analyze_bundle(
            candles_by_tf.get(Timeframe.M15, []),
            exchange=exchange,
            symbol=symbol,
            market_type=market_type,
            timeframe=Timeframe.M15,
            need_structure=True,
            need_liquidity=True,
            need_ob_fvg=True,
        ),
        Timeframe.M5: analyze_bundle(
            candles_by_tf.get(Timeframe.M5, []),
            exchange=exchange,
            symbol=symbol,
            market_type=market_type,
            timeframe=Timeframe.M5,
            need_structure=True,
            need_liquidity=True,
            need_ob_fvg=True,
        ),
    }

    confluence = analyze_confluence(
        exchange=exchange,
        symbol=symbol,
        market_type=market_type,
        mtf_snapshot=mtf_snapshot,
        bundles=bundles,
        config=cfg,
        as_of=now,
    )
    return AnalysisContext(
        mtf_snapshot=mtf_snapshot,
        bundles=bundles,
        candles_by_tf=candles_by_tf,
        confluence=confluence,
        as_of=now,
    )


def build_analysis_context_from_candles(
    candles_by_tf: dict[Timeframe, list[Candle]],
    *,
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    confluence_config: ConfluenceConfig | None = None,
    as_of: datetime,
) -> AnalysisContext:
    """
    Build confluence context from in-memory MTF candle prefixes.

    Does not call ExchangeManager or any live APIs. Used by historical replay
    analysis (Phase 5.2.1). Caller must supply only candles available at ``as_of``.
    """
    cfg = confluence_config or DEFAULT_CONFLUENCE_CONFIG
    mtf_cfg = DEFAULT_MTF_CONFIG
    now = as_of

    series = {}
    for tf in mtf_cfg.timeframes:
        payload = candles_by_tf.get(tf, [])
        series[tf] = evaluate_timeframe_series(
            payload,
            timeframe=tf,
            exchange=exchange,
            symbol=symbol,
            market_type=market_type,
            as_of=now,
            config=mtf_cfg,
        )

    mtf_snapshot = build_snapshot(
        series,
        exchange=exchange,
        symbol=symbol,
        market_type=market_type,
        as_of=now,
        config=mtf_cfg,
    )

    bundles: dict[Timeframe, TimeframeAnalysisBundle] = {
        Timeframe.H4: analyze_bundle(
            candles_by_tf.get(Timeframe.H4, []),
            exchange=exchange,
            symbol=symbol,
            market_type=market_type,
            timeframe=Timeframe.H4,
            need_structure=True,
            need_liquidity=False,
            need_ob_fvg=False,
        ),
        Timeframe.H1: analyze_bundle(
            candles_by_tf.get(Timeframe.H1, []),
            exchange=exchange,
            symbol=symbol,
            market_type=market_type,
            timeframe=Timeframe.H1,
            need_structure=True,
            need_liquidity=True,
            need_ob_fvg=False,
        ),
        Timeframe.M15: analyze_bundle(
            candles_by_tf.get(Timeframe.M15, []),
            exchange=exchange,
            symbol=symbol,
            market_type=market_type,
            timeframe=Timeframe.M15,
            need_structure=True,
            need_liquidity=True,
            need_ob_fvg=True,
        ),
        Timeframe.M5: analyze_bundle(
            candles_by_tf.get(Timeframe.M5, []),
            exchange=exchange,
            symbol=symbol,
            market_type=market_type,
            timeframe=Timeframe.M5,
            need_structure=True,
            need_liquidity=True,
            need_ob_fvg=True,
        ),
    }

    confluence = analyze_confluence(
        exchange=exchange,
        symbol=symbol,
        market_type=market_type,
        mtf_snapshot=mtf_snapshot,
        bundles=bundles,
        config=cfg,
        as_of=now,
    )
    return AnalysisContext(
        mtf_snapshot=mtf_snapshot,
        bundles=bundles,
        candles_by_tf={tf: list(candles_by_tf.get(tf, [])) for tf in mtf_cfg.timeframes},
        confluence=confluence,
        as_of=now,
    )
