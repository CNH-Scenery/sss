import httpx
import pytest

from app.services.upbit_client import UpbitClient


@pytest.mark.asyncio
async def test_upbit_client_normalizes_markets_and_minute_candles():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/market/all":
            return httpx.Response(
                200,
                json=[
                    {
                        "market": "KRW-BTC",
                        "korean_name": "비트코인",
                        "english_name": "Bitcoin",
                    },
                    {
                        "market": "BTC-ETH",
                        "korean_name": "이더리움",
                        "english_name": "Ethereum",
                    },
                ],
            )
        if request.url.path == "/v1/candles/minutes/15":
            assert request.url.params["market"] == "KRW-BTC"
            assert request.url.params["count"] == "2"
            return httpx.Response(
                200,
                json=[
                    {
                        "candle_date_time_kst": "2026-06-01T09:15:00",
                        "opening_price": 101.0,
                        "high_price": 103.0,
                        "low_price": 100.0,
                        "trade_price": 102.0,
                        "candle_acc_trade_volume": 12.0,
                    },
                    {
                        "candle_date_time_kst": "2026-06-01T09:00:00",
                        "opening_price": 100.0,
                        "high_price": 102.0,
                        "low_price": 99.0,
                        "trade_price": 101.0,
                        "candle_acc_trade_volume": 10.0,
                    },
                ],
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with UpbitClient(base_url="https://upbit.test", transport=transport) as client:
        markets = await client.get_markets()
        candles = await client.get_candles("KRW-BTC", "15", count=2)

    assert markets == [
        {
            "code": "KRW-BTC",
            "korean_name": "비트코인",
            "english_name": "Bitcoin",
        }
    ]
    assert candles == [
        {
            "ts": "2026-06-01T09:00:00+09:00",
            "o": 100.0,
            "h": 102.0,
            "l": 99.0,
            "c": 101.0,
            "v": 10.0,
            "raw": {
                "candle_date_time_kst": "2026-06-01T09:00:00",
                "opening_price": 100.0,
                "high_price": 102.0,
                "low_price": 99.0,
                "trade_price": 101.0,
                "candle_acc_trade_volume": 10.0,
            },
        },
        {
            "ts": "2026-06-01T09:15:00+09:00",
            "o": 101.0,
            "h": 103.0,
            "l": 100.0,
            "c": 102.0,
            "v": 12.0,
            "raw": {
                "candle_date_time_kst": "2026-06-01T09:15:00",
                "opening_price": 101.0,
                "high_price": 103.0,
                "low_price": 100.0,
                "trade_price": 102.0,
                "candle_acc_trade_volume": 12.0,
            },
        },
    ]
    assert [request.url.path for request in requests] == [
        "/v1/market/all",
        "/v1/candles/minutes/15",
    ]
