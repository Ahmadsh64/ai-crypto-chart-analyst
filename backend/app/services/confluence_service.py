"""REST service for confluence scoring (Phase 4.2)."""

from __future__ import annotations

from datetime import datetime

from app.analysis.confluence.config import DEFAULT_CONFLUENCE_CONFIG, ConfluenceConfig
from app.api.schemas.confluence import ConfluenceResponse
from app.exchanges.types import ExchangeId, MarketType
from app.services.analysis_context import build_analysis_context


async def compute_confluence_response(
    *,
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str,
    config: ConfluenceConfig | None = None,
    as_of: datetime | None = None,
) -> ConfluenceResponse:
    cfg = config or DEFAULT_CONFLUENCE_CONFIG
    ctx = await build_analysis_context(
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        confluence_config=cfg,
        as_of=as_of,
    )
    result = ctx.confluence

    return ConfluenceResponse(
        exchange=exchange,
        symbol=symbol,
        market_type=market_type,
        calculated_at=result.calculated_at,
        data_source=f"{exchange.value}:{market_type.value}",
        config=cfg.snapshot(),
        bullish_score=result.bullish_score,
        bearish_score=result.bearish_score,
        category_scores=result.category_scores,
        evidence=result.evidence,
        excluded_evidence=result.excluded_evidence,
        conflicts=result.conflicts,
        preliminary_assessment=result.preliminary_assessment,
        assessment_strength=result.assessment_strength,
        data_quality=result.data_quality,
        summary=result.summary,
        configuration_version=result.config_version,
        analysis_timestamp=result.calculated_at,
        mtf_snapshot=ctx.mtf_snapshot,
        metadata=result.metadata,
    )
