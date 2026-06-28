import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


KST = timezone(timedelta(hours=9))


class UpbitClient:
    def __init__(
        self,
        base_url: str = "https://api.upbit.com",
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout, transport=transport)

    async def __aenter__(self) -> "UpbitClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        delay = 0.25
        for attempt in range(3):
            response = await self._client.get(path, params=params)
            if response.status_code != 429:
                response.raise_for_status()
                return response.json()
            if attempt == 2:
                response.raise_for_status()
            await asyncio.sleep(delay)
            delay *= 2
        raise RuntimeError("unreachable retry state")

    async def get_markets(self) -> list[dict[str, str]]:
        raw_markets = await self._get_json("/v1/market/all", params={"isDetails": "false"})
        return [
            {
                "code": item["market"],
                "korean_name": item["korean_name"],
                "english_name": item["english_name"],
            }
            for item in raw_markets
            if item.get("market", "").startswith("KRW-")
        ]

    async def get_candles(
        self,
        market: str,
        timeframe: str,
        count: int = 200,
        to: datetime | None = None,
    ) -> list[dict[str, Any]]:
        safe_count = max(1, min(int(count), 200))
        path = self._candle_path(timeframe)
        params: dict[str, Any] = {"market": market, "count": safe_count}
        if to is not None:
            params["to"] = to.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        raw_candles = await self._get_json(path, params=params)
        candles = [self._normalize_candle(item) for item in raw_candles]
        return sorted(candles, key=lambda candle: candle["ts"])

    def _candle_path(self, timeframe: str) -> str:
        if timeframe.isdigit():
            return f"/v1/candles/minutes/{timeframe}"
        if timeframe in {"days", "weeks", "months"}:
            return f"/v1/candles/{timeframe}"
        raise ValueError(f"unsupported timeframe: {timeframe}")

    def _normalize_candle(self, item: dict[str, Any]) -> dict[str, Any]:
        ts = _parse_kst_timestamp(item["candle_date_time_kst"]).isoformat()
        return {
            "ts": ts,
            "o": float(item["opening_price"]),
            "h": float(item["high_price"]),
            "l": float(item["low_price"]),
            "c": float(item["trade_price"]),
            "v": float(item["candle_acc_trade_volume"]),
            "raw": item,
        }


def _parse_kst_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)
