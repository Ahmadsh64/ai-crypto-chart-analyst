"""Phase 4.2 — Deterministic confluence scoring tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.analysis.confluence.config import DEFAULT_CONFLUENCE_CONFIG, ConfluenceConfig
from app.analysis.confluence.engine import TimeframeAnalysisBundle, analyze_confluence
from app.analysis.confluence.evidence import dedupe_evidence
from app.analysis.confluence.models import (
    EvidenceDirection,
    EvidenceItem,
    EvidenceType,
    PreliminaryAssessment,
)
from app.analysis.confluence.scoring import decide_preliminary_assessment, score_categories
from app.analysis.multi_timeframe.models import (
    MultiTimeframeSnapshot,
    SyncMetadata,
    TimeframeSeriesSummary,
)
from app.exchanges.types import ExchangeId, MarketType, Timeframe
from app.main import app


NOW = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)


def _ev(
    *,
    eid: str,
    category: str,
    tf: Timeframe,
    direction: EvidenceDirection,
    strength: float,
    source: str,
    excluded: bool = False,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=eid,
        evidence_type=EvidenceType.BOS,
        category=category,
        timeframe=tf,
        direction=direction,
        strength=strength,
        confidence=1.0,
        source_event_key=source,
        source_timestamp=NOW,
        explanation=f"{eid}",
        excluded=excluded,
        exclusion_reason="test" if excluded else None,
    )


def _ready_summary(tf: Timeframe) -> TimeframeSeriesSummary:
    return TimeframeSeriesSummary(
        timeframe=tf,
        purpose="htf_context",
        duration_minutes=60,
        latest_closed_candle_time=NOW,
        latest_price=100.0,
        candles_count=100,
        closed_candles_count=99,
        is_ready=True,
        is_stale=False,
        has_data_gaps=False,
        data_quality="ok",
        last_updated=NOW,
    )


def _mtf_ready() -> MultiTimeframeSnapshot:
    tfs = [_ready_summary(tf) for tf in (Timeframe.H4, Timeframe.H1, Timeframe.M15, Timeframe.M5)]
    return MultiTimeframeSnapshot(
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        calculated_at=NOW,
        config_version="mtf-v1.0.0-orchestration",
        overall_status="ready",
        ready_timeframes=[Timeframe.H4, Timeframe.H1, Timeframe.M15, Timeframe.M5],
        unavailable_timeframes=[],
        timeframes=tfs,
        sync=SyncMetadata(as_of=NOW, aligned=True),
    )


def test_config_weights_sum_to_100():
    assert abs(sum(DEFAULT_CONFLUENCE_CONFIG.category_weights.values()) - 100) < 1e-9
    assert DEFAULT_CONFLUENCE_CONFIG.config_version == "confluence-v1.0.0-balanced"


def test_duplicate_evidence_does_not_increase_score():
    a = _ev(
        eid="1",
        category="market_structure",
        tf=Timeframe.H1,
        direction=EvidenceDirection.BULLISH,
        strength=1.0,
        source="bos:same",
    )
    b = _ev(
        eid="2",
        category="market_structure",
        tf=Timeframe.H1,
        direction=EvidenceDirection.BULLISH,
        strength=1.0,
        source="bos:same",
    )
    kept, excluded = dedupe_evidence([a, b])
    assert len(kept) == 1
    assert len(excluded) == 1
    assert excluded[0].exclusion_reason == "duplicate_event_key"
    _, bull_once, _ = score_categories(kept, DEFAULT_CONFLUENCE_CONFIG)
    _, bull_dup_raw, _ = score_categories([a, b], DEFAULT_CONFLUENCE_CONFIG)
    # Without dedupe raw list would score higher or equal; after dedupe lower/equal than undeduped sum path
    assert bull_once <= bull_dup_raw


def test_category_weight_cap_and_bounds():
    items = [
        _ev(
            eid=f"b{i}",
            category="htf_context",
            tf=Timeframe.H4,
            direction=EvidenceDirection.BULLISH,
            strength=1.0,
            source=f"unique:{i}",
        )
        for i in range(10)
    ]
    scores, bull, bear = score_categories(items, DEFAULT_CONFLUENCE_CONFIG)
    htf = next(s for s in scores if s.category == "htf_context")
    assert htf.bullish_contribution <= htf.weight + 1e-9
    assert 0 <= bull <= 100
    assert bear == 0


def test_deterministic_repeated_scoring():
    items = [
        _ev(
            eid="x",
            category="market_structure",
            tf=Timeframe.H1,
            direction=EvidenceDirection.BEARISH,
            strength=0.85,
            source="bos:1",
        )
    ]
    a = score_categories(items, DEFAULT_CONFLUENCE_CONFIG)
    b = score_categories(items, DEFAULT_CONFLUENCE_CONFIG)
    assert a == b


def test_preliminary_thresholds_and_htf_conflict():
    label, strength = decide_preliminary_assessment(
        bullish_score=80,
        bearish_score=20,
        config=DEFAULT_CONFLUENCE_CONFIG,
        has_critical_htf_conflict=False,
        analysis_complete=True,
        data_unavailable=False,
        has_confirmed_evidence=True,
        htf_opposes_bullish=False,
        htf_opposes_bearish=False,
    )
    assert label == PreliminaryAssessment.BULLISH_CONFLUENCE
    assert strength == "strong"

    mixed, _ = decide_preliminary_assessment(
        bullish_score=80,
        bearish_score=20,
        config=DEFAULT_CONFLUENCE_CONFIG,
        has_critical_htf_conflict=True,
        analysis_complete=True,
        data_unavailable=False,
        has_confirmed_evidence=True,
        htf_opposes_bullish=False,
        htf_opposes_bearish=False,
    )
    assert mixed == PreliminaryAssessment.MIXED


def test_analyze_confluence_empty_bundles_insufficient():
    result = analyze_confluence(
        exchange=ExchangeId.BINANCE,
        symbol="BTC/USDT",
        market_type=MarketType.SPOT,
        mtf_snapshot=_mtf_ready(),
        bundles={},
        config=DEFAULT_CONFLUENCE_CONFIG,
        as_of=NOW,
    )
    assert result.bullish_score == 0
    assert result.bearish_score == 0
    assert result.preliminary_assessment in {
        PreliminaryAssessment.INSUFFICIENT_EVIDENCE,
        PreliminaryAssessment.DATA_UNAVAILABLE,
        PreliminaryAssessment.MIXED,
    }
    assert result.metadata["no_trade_decisions"] is True


def test_api_confluence_schema(monkeypatch):
    from app.analysis.confluence.models import CategoryScore, ConfluenceDataQuality
    from app.api.schemas.confluence import ConfluenceResponse

    async def fake_compute(**kwargs):
        mtf = _mtf_ready()
        return ConfluenceResponse(
            exchange=ExchangeId.BINANCE,
            symbol="BTC/USDT",
            market_type=MarketType.SPOT,
            calculated_at=NOW,
            data_source="binance:spot",
            config=DEFAULT_CONFLUENCE_CONFIG.snapshot(),
            bullish_score=12.5,
            bearish_score=40.0,
            category_scores=[
                CategoryScore(
                    category="market_structure",
                    weight=25,
                    bullish_contribution=0,
                    bearish_contribution=12.5,
                    bullish_unit=0,
                    bearish_unit=0.5,
                )
            ],
            evidence=[],
            excluded_evidence=[],
            conflicts=[],
            preliminary_assessment=PreliminaryAssessment.MIXED,
            assessment_strength="none",
            data_quality=ConfluenceDataQuality(
                overall="ready",
                is_analysis_complete=True,
                timeframes_used=[Timeframe.H1],
            ),
            summary="test summary",
            configuration_version="confluence-v1.0.0-balanced",
            analysis_timestamp=NOW,
            mtf_snapshot=mtf,
            metadata={"no_trade_decisions": True},
        )

    monkeypatch.setattr(
        "app.api.routes.confluence.compute_confluence_response",
        fake_compute,
    )

    client = TestClient(app)
    res = client.get(
        "/api/v1/confluence",
        params={"exchange": "binance", "market_type": "spot", "symbol": "BTC/USDT"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["configuration_version"] == "confluence-v1.0.0-balanced"
    assert "bullish_score" in body and "bearish_score" in body
    assert body["preliminary_assessment"] == "mixed"
    assert "LONG" not in res.text
    assert "SHORT" not in res.text
    assert "NO TRADE" not in res.text


def test_config_version_change_is_explicit():
    other = ConfluenceConfig(config_version="confluence-test")
    assert other.config_version != DEFAULT_CONFLUENCE_CONFIG.config_version
