"""Explainable ranking using existing scores only (Phase 5.5)."""

from __future__ import annotations

from app.scanner.models import MarketOpportunity, OpportunityStatus

_STATUS_RANK = {
    OpportunityStatus.READY: 0,
    OpportunityStatus.APPROACHING_ENTRY: 1,
    OpportunityStatus.WAITING: 2,
    OpportunityStatus.DATA_UNAVAILABLE: 3,
    OpportunityStatus.EXPIRED: 4,
    OpportunityStatus.INVALIDATED: 5,
}


def compute_rank(opportunity: MarketOpportunity) -> tuple[float, str]:
    """
    Higher rank_score = better for sort-desc.

    Order factors (existing data only):
    1) Actionable READY first
    2) Confluence score
    3) Freshness (analysis present)
    4) Liquidity (quote volume)
    5) Closer to entry
    """
    status_bonus = (6 - _STATUS_RANK.get(opportunity.status, 5)) * 1000.0
    confluence = float(opportunity.confluence_score or 0.0)
    freshness = 50.0 if opportunity.analysis_timestamp else 0.0
    liquidity = 0.0
    if opportunity.quote_volume_24h is not None and opportunity.quote_volume_24h > 0:
        # Log-ish compression without inventing scores
        liquidity = min(100.0, (opportunity.quote_volume_24h / 1_000_000.0) * 5.0)
    distance = opportunity.entry_distance_pct
    proximity = 0.0
    if distance is not None:
        proximity = max(0.0, 100.0 - min(distance * 10.0, 100.0))

    score = status_bonus + confluence * 2.0 + freshness + liquidity + proximity
    parts = [
        f"status={opportunity.status.value}",
        f"confluence={confluence:.1f}",
        f"freshness={freshness:.0f}",
        f"liquidity_factor={liquidity:.1f}",
        f"entry_proximity={proximity:.1f}",
    ]
    explanation = (
        "Ranked by READY priority, then existing confluence, freshness, "
        f"liquidity suitability, and entry distance. ({'; '.join(parts)}). "
        "Higher score does not guarantee profitability."
    )
    return score, explanation


def sort_opportunities(items: list[MarketOpportunity]) -> list[MarketOpportunity]:
    ranked: list[MarketOpportunity] = []
    for item in items:
        score, explanation = compute_rank(item)
        ranked.append(
            item.model_copy(
                update={"rank_score": score, "rank_explanation": explanation},
            )
        )
    ranked.sort(
        key=lambda o: (
            _STATUS_RANK.get(o.status, 99),
            -(o.confluence_score or 0.0),
            o.entry_distance_pct if o.entry_distance_pct is not None else 1e9,
            -(o.quote_volume_24h or 0.0),
            o.symbol,
        ),
    )
    return ranked
