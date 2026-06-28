import pytest
from sqlalchemy.orm import sessionmaker

from app.db import Base, create_engine_from_url
from app.services.candle_cache import CandleCache


class FakeUpbitClient:
    def __init__(self):
        self.calls = 0

    async def get_candles(self, market: str, timeframe: str, count: int):
        self.calls += 1
        return [
            {
                "ts": f"2026-06-01T09:{i:02d}:00+09:00",
                "o": 100.0 + i,
                "h": 101.0 + i,
                "l": 99.0 + i,
                "c": 100.5 + i,
                "v": 10.0 + i,
                "raw": {"i": i},
            }
            for i in range(count)
        ]


@pytest.mark.asyncio
async def test_candle_cache_reuses_stored_candles_for_same_market_timeframe_count(tmp_path):
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'cache.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    client = FakeUpbitClient()

    with SessionLocal() as db:
        cache = CandleCache(db=db, upbit_client=client)

        first = await cache.get_candles("KRW-BTC", "15", 3)
        second = await cache.get_candles("KRW-BTC", "15", 3)

    assert client.calls == 1
    assert second == first
    assert [candle["ts"] for candle in second] == [
        "2026-06-01T09:00:00+09:00",
        "2026-06-01T09:01:00+09:00",
        "2026-06-01T09:02:00+09:00",
    ]
