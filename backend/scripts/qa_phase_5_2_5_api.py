"""LABELED FIXTURE / API QA — Phase 5.2.5 robustness (not live profitability).

Exercises replay REST controls against a mocked historical loader.
Seek has no REST endpoint — validated via session.seek in unit tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.exchanges.types import Candle, ExchangeId, MarketType, Timeframe
from app.main import app
from app.replay.manager import reset_replay_manager

UTC = timezone.utc
START = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
EX = ExchangeId.BINANCE
SYM = "BTC/USDT"
MT = MarketType.SPOT


def _c(open_ts: datetime, o: float, h: float, l: float, cl: float, tf: Timeframe) -> Candle:
    sec = {Timeframe.M5: 300, Timeframe.M15: 900, Timeframe.H1: 3600, Timeframe.H4: 14400}[tf]
    return Candle(
        timestamp=open_ts,
        open=o,
        high=h,
        low=l,
        close=cl,
        volume=10.0,
        exchange=EX,
        symbol=SYM,
        market_type=MT,
        is_closed=True,
        close_time=open_ts + timedelta(seconds=sec) - timedelta(milliseconds=1),
    )


def synth(n: int = 48) -> dict[Timeframe, list[Candle]]:
    m5 = []
    price = 100.0
    for i in range(n):
        ts = START + timedelta(minutes=5 * i)
        o, cl = price, price + (0.3 if i % 2 == 0 else -0.25)
        m5.append(_c(ts, o, max(o, cl) + 0.2, min(o, cl) - 0.2, cl, Timeframe.M5))
        price = cl

    def agg(tf: Timeframe) -> list[Candle]:
        step = {Timeframe.M15: 900, Timeframe.H1: 3600, Timeframe.H4: 14400}[tf]
        buckets: dict[datetime, list[Candle]] = {}
        for c in m5:
            key = datetime.fromtimestamp((int(c.timestamp.timestamp()) // step) * step, tz=UTC)
            buckets.setdefault(key, []).append(c)
        out = []
        for open_ts in sorted(buckets):
            parts = buckets[open_ts]
            out.append(
                _c(
                    open_ts,
                    parts[0].open,
                    max(p.high for p in parts),
                    min(p.low for p in parts),
                    parts[-1].close,
                    tf,
                )
            )
        return out

    return {
        Timeframe.M5: m5,
        Timeframe.M15: agg(Timeframe.M15),
        Timeframe.H1: agg(Timeframe.H1),
        Timeframe.H4: agg(Timeframe.H4),
    }


def main() -> None:
    reset_replay_manager()
    series = synth(48)

    async def fake_load(**kwargs):
        return series, [], []

    client = TestClient(app)
    results: dict[str, object] = {}
    with patch("app.replay.session.load_replay_series", new=AsyncMock(side_effect=fake_load)):
        r = client.post(
            "/api/v1/replay/sessions",
            json={
                "exchange": "binance",
                "symbol": "BTC/USDT",
                "market_type": "spot",
                "start_time": START.isoformat(),
                "end_time": (START + timedelta(hours=4)).isoformat(),
                "speed": "max",
            },
        )
        results["create"] = r.status_code
        assert r.status_code == 200, r.text
        body = r.json()
        sid = body["session"]["session_id"]
        results["session_id"] = sid
        results["event_count"] = body["snapshot"]["event_count"]

        r = client.get(f"/api/v1/replay/sessions/{sid}")
        results["get"] = r.status_code

        r = client.post(f"/api/v1/replay/sessions/{sid}/step")
        results["step"] = r.status_code
        assert r.json()["snapshot"]["event_index"] == 1

        r = client.post(f"/api/v1/replay/sessions/{sid}/analysis/enable")
        results["analysis_enable"] = r.status_code

        r = client.post(f"/api/v1/replay/sessions/{sid}/simulation/enable")
        results["simulation_enable"] = r.status_code

        r = client.post(f"/api/v1/replay/sessions/{sid}/costs/enable")
        results["costs_enable"] = r.status_code

        r = client.post(f"/api/v1/replay/sessions/{sid}/analytics/enable")
        results["analytics_enable"] = r.status_code

        for key, path in (
            ("summary", f"/api/v1/replay/sessions/{sid}/analytics/summary"),
            ("equity", f"/api/v1/replay/sessions/{sid}/analytics/equity"),
            ("drawdown", f"/api/v1/replay/sessions/{sid}/analytics/drawdown"),
            ("trades", f"/api/v1/replay/sessions/{sid}/analytics/trades"),
        ):
            rr = client.get(path)
            results[key] = rr.status_code

        r = client.post(f"/api/v1/replay/sessions/{sid}/reset")
        results["reset"] = r.status_code
        assert r.json()["snapshot"]["event_index"] == 0

        r = client.post(f"/api/v1/replay/sessions/{sid}/seek", json={"event_index": 5})
        results["seek_rest"] = r.status_code  # expected 404/405 — no REST seek

        r = client.post(f"/api/v1/replay/sessions/{sid}/step")
        results["after_step_index"] = r.json()["snapshot"]["event_index"]
        results["data_quality"] = r.json()["snapshot"].get("data_quality")

    reset_replay_manager()
    print("PHASE_5_2_5_API_QA")
    for k, v in results.items():
        print(f"  {k}: {v}")
    assert results["create"] == 200
    assert results["get"] == 200
    assert results["step"] == 200
    assert results["analysis_enable"] == 200
    assert results["simulation_enable"] == 200
    assert results["costs_enable"] == 200
    assert results["analytics_enable"] == 200
    assert results["summary"] == 200
    assert results["equity"] == 200
    assert results["drawdown"] == 200
    assert results["trades"] == 200
    assert results["reset"] == 200
    assert results["seek_rest"] in {404, 405, 422}
    print("PASS")


if __name__ == "__main__":
    main()
