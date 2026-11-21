"""Candidate universe discovery with staged liquidity filters (Phase 5.5 Step 2).

Ranking method
--------------
1. Discover active USDT pairs via exchange list_markets (Spot and Futures separate).
2. Bulk-fetch 24h tickers when available (Binance all-ticker, Bybit category tickers).
3. Rank by verified quote/turnover volume (USDT) descending.
4. Exclude pairs below min_quote_volume_24h when volume is known.
5. Cap at max_pairs_per_market per (exchange, market_type).

Limitations
-----------
- Volume units may still be ambiguous if an exchange omits quote/turnover fields;
  ranking then falls back to base volume or treats volume as missing.
- Missing volume: pair is eligible for ranking only if ticker exists with last price;
  pairs with no ticker data are excluded (not hardcoded majors).
- Bulk ticker failure for one market does not block other markets/exchanges.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.exchanges.manager import get_exchange_manager
from app.exchanges.types import ExchangeId, MarketType, TradingPair
from app.market_data.markets_cache import get_markets_cache
from app.scanner.config import ScannerConfig

RANKING_METHOD = (
    "quote_or_turnover_24h_desc_with_min_volume_filter_cap_per_market"
)


@dataclass(frozen=True)
class ScanCandidate:
    exchange: ExchangeId
    market_type: MarketType
    symbol: str
    base: str
    quote_volume_24h: float | None = None


@dataclass
class ExclusionRecord:
    exchange: str
    market_type: str
    symbol: str | None
    reason: str


@dataclass
class UniverseBucketStats:
    exchange: str
    market_type: str
    discovered: int = 0
    eligible: int = 0
    selected: int = 0
    excluded: int = 0


@dataclass
class UniverseDiscoveryResult:
    candidates: list[ScanCandidate] = field(default_factory=list)
    discovered_pairs: int = 0
    eligible_pairs: int = 0
    selected_pairs: int = 0
    excluded: list[ExclusionRecord] = field(default_factory=list)
    per_market: list[UniverseBucketStats] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    ranking_method: str = RANKING_METHOD


def _compatible_markets(exchange: ExchangeId, configured: list[MarketType]) -> list[MarketType]:
    manager = get_exchange_manager()
    info = next((e for e in manager.list_exchanges() if e.id == exchange), None)
    supported = set(info.market_types) if info else set()
    return [m for m in configured if m in supported]


def _append_exclusion(
    excluded: list[ExclusionRecord],
    *,
    exchange: ExchangeId,
    market_type: MarketType,
    symbol: str | None,
    reason: str,
    limit: int = 100,
) -> None:
    if len(excluded) >= limit:
        return
    excluded.append(
        ExclusionRecord(
            exchange=exchange.value,
            market_type=market_type.value,
            symbol=symbol,
            reason=reason,
        )
    )


async def discover_universe(config: ScannerConfig) -> UniverseDiscoveryResult:
    """
    Staged discovery:
      list_markets → active USDT filter → bulk volume rank → cap 25/market.
    Isolates per-exchange and per-market-type failures.
    """
    cache = get_markets_cache()
    manager = get_exchange_manager()
    result = UniverseDiscoveryResult()

    for exchange in config.default_exchanges:
        for market_type in _compatible_markets(exchange, config.default_market_types):
            bucket = UniverseBucketStats(
                exchange=exchange.value,
                market_type=market_type.value,
            )
            try:
                pairs = cache.get(exchange, market_type)
                if pairs is None:
                    pairs = await manager.list_markets(exchange, market_type)
                    active = [p for p in pairs if p.active]
                    cache.set(exchange, market_type, active)
                    pairs = active
                else:
                    pairs = [p for p in pairs if p.active]
            except Exception as exc:  # noqa: BLE001
                msg = f"{exchange.value}:{market_type.value}: list_markets failed: {exc}"
                result.errors.append(msg)
                _append_exclusion(
                    result.excluded,
                    exchange=exchange,
                    market_type=market_type,
                    symbol=None,
                    reason=f"market_discovery_failed:{exc}",
                )
                result.per_market.append(bucket)
                continue

            bucket.discovered = len(pairs)
            result.discovered_pairs += bucket.discovered

            usdt_pairs = [p for p in pairs if (p.quote or "").upper() == "USDT"]
            inactive_or_non_usdt = bucket.discovered - len(usdt_pairs)
            if inactive_or_non_usdt > 0:
                # list_markets already filters non-USDT on adapters; count residual.
                _append_exclusion(
                    result.excluded,
                    exchange=exchange,
                    market_type=market_type,
                    symbol=None,
                    reason=f"filtered_non_usdt_or_inactive_count={inactive_or_non_usdt}",
                )

            if not usdt_pairs:
                result.per_market.append(bucket)
                continue

            selected, eligible_count, exclusions = await _select_by_volume(
                exchange=exchange,
                market_type=market_type,
                pairs=usdt_pairs,
                config=config,
            )
            bucket.eligible = eligible_count
            bucket.selected = len(selected)
            bucket.excluded = max(0, len(usdt_pairs) - bucket.selected)
            result.eligible_pairs += eligible_count
            result.selected_pairs += bucket.selected
            result.candidates.extend(selected)
            result.excluded.extend(exclusions)
            result.per_market.append(bucket)

    return result


async def discover_candidates(config: ScannerConfig) -> list[ScanCandidate]:
    """Backward-compatible helper — returns selected candidates only."""
    return (await discover_universe(config)).candidates


async def _select_by_volume(
    *,
    exchange: ExchangeId,
    market_type: MarketType,
    pairs: list[TradingPair],
    config: ScannerConfig,
) -> tuple[list[ScanCandidate], int, list[ExclusionRecord]]:
    """
    Rank by bulk 24h quote/turnover volume. No hardcoded major-coin list.
    Returns (selected, eligible_count, exclusions).
    """
    manager = get_exchange_manager()
    exclusions: list[ExclusionRecord] = []
    volume_by_symbol: dict[str, float | None] = {}
    ticker_ok = False

    if config.ticker_prefetch:
        try:
            tickers = await manager.fetch_tickers_24h(exchange, market_type)
            for t in tickers:
                volume_by_symbol[t.symbol.upper()] = t.volume_24h
            ticker_ok = True
        except Exception as exc:  # noqa: BLE001
            _append_exclusion(
                exclusions,
                exchange=exchange,
                market_type=market_type,
                symbol=None,
                reason=f"bulk_ticker_failed:{exc}",
            )

    scored: list[tuple[float, ScanCandidate]] = []
    eligible = 0

    for pair in pairs:
        sym = pair.symbol.upper()
        if not pair.base and "/" not in pair.symbol:
            _append_exclusion(
                exclusions,
                exchange=exchange,
                market_type=market_type,
                symbol=pair.symbol,
                reason="invalid_symbol",
            )
            continue

        volume: float | None = volume_by_symbol.get(sym) if ticker_ok else None

        if ticker_ok and sym not in volume_by_symbol:
            _append_exclusion(
                exclusions,
                exchange=exchange,
                market_type=market_type,
                symbol=pair.symbol,
                reason="missing_ticker",
            )
            continue

        if volume is not None and volume < config.min_quote_volume_24h:
            _append_exclusion(
                exclusions,
                exchange=exchange,
                market_type=market_type,
                symbol=pair.symbol,
                reason=f"below_min_volume:{volume}",
            )
            continue

        # Missing volume after successful bulk fetch: exclude (unreliable rank).
        # If bulk fetch failed entirely, allow pairs without volume but rank at 0
        # so the market is still covered (capped), with volume=None documented.
        if ticker_ok and volume is None:
            _append_exclusion(
                exclusions,
                exchange=exchange,
                market_type=market_type,
                symbol=pair.symbol,
                reason="missing_volume",
            )
            continue

        eligible += 1
        scored.append(
            (
                float(volume or 0.0),
                ScanCandidate(
                    exchange=exchange,
                    market_type=market_type,
                    symbol=pair.symbol,
                    base=pair.base or pair.symbol.split("/")[0],
                    quote_volume_24h=volume,
                ),
            )
        )

    scored.sort(key=lambda x: x[0], reverse=True)
    seen: set[str] = set()
    selected: list[ScanCandidate] = []
    for _, cand in scored:
        key = cand.symbol.upper()
        if key in seen:
            continue
        seen.add(key)
        if len(selected) >= config.max_pairs_per_market:
            _append_exclusion(
                exclusions,
                exchange=exchange,
                market_type=market_type,
                symbol=cand.symbol,
                reason="over_cap",
            )
            continue
        selected.append(cand)

    return selected, eligible, exclusions
