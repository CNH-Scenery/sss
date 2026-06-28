import json
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.candle import Candle


KST = timezone(timedelta(hours=9))


class CandleCache:
    def __init__(self, db: Session, upbit_client: Any):
        self.db = db
        self.upbit_client = upbit_client

    async def get_candles(self, market: str, timeframe: str, count: int = 200) -> list[dict[str, Any]]:
        cached = self._load_cached(market, timeframe, count)
        if len(cached) >= count:
            return cached

        fetched = await self.upbit_client.get_candles(market, timeframe, count)
        self._store(market, timeframe, fetched)
        return self._load_cached(market, timeframe, count)

    def _load_cached(self, market: str, timeframe: str, count: int) -> list[dict[str, Any]]:
        rows = (
            self.db.execute(
                select(Candle)
                .where(Candle.market == market, Candle.timeframe == timeframe)
                .order_by(Candle.ts.desc())
                .limit(count)
            )
            .scalars()
            .all()
        )
        return [self._to_payload(row) for row in reversed(rows)]

    def _store(self, market: str, timeframe: str, candles: list[Mapping[str, Any]]) -> None:
        for candle in candles:
            ts = _parse_iso(candle["ts"])
            existing = self.db.execute(
                select(Candle).where(Candle.market == market, Candle.timeframe == timeframe, Candle.ts == ts)
            ).scalar_one_or_none()
            if existing is not None:
                continue
            self.db.add(
                Candle(
                    market=market,
                    timeframe=timeframe,
                    ts=ts,
                    open=float(candle["o"]),
                    high=float(candle["h"]),
                    low=float(candle["l"]),
                    close=float(candle["c"]),
                    volume=float(candle["v"]),
                    raw_json=json.dumps(candle.get("raw", {}), ensure_ascii=False),
                )
            )
        self.db.commit()

    def _to_payload(self, candle: Candle) -> dict[str, Any]:
        ts = candle.ts
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=KST)
        else:
            ts = ts.astimezone(KST)
        return {
            "ts": ts.isoformat(),
            "o": candle.open,
            "h": candle.high,
            "l": candle.low,
            "c": candle.close,
            "v": candle.volume,
            "raw": json.loads(candle.raw_json),
        }


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)
