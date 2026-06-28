from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.api.surveys import get_candle_fetcher
from app.db import Base, create_engine_from_url, get_db
from app.main import app
from app.models.backtest_result import BacktestResult
from app.models.strategy_version import StrategyVersion


KST = timezone(timedelta(hours=9))
STRATEGY_CODE = """
def decide(features: dict, position: dict) -> dict:
    holding = bool(position.get("holding", False))
    rsi = float(features.get("rsi14", 50) or 50)
    pnl = float(position.get("pnl_pct", 0) or 0)
    if (not holding) and rsi < 45:
        return {"action": "BUY", "reason": "low rsi"}
    if holding and (rsi > 55 or pnl > 1):
        return {"action": "SELL", "reason": "exit"}
    return {"action": "HOLD", "reason": "wait"}
""".strip()


def make_candles(count: int = 180):
    start = datetime(2026, 5, 1, 9, 0, tzinfo=KST)
    candles = []
    price = 100.0
    for i in range(count):
        if i < 60:
            close = price - 0.7
        elif i < 120:
            close = price + 0.9
        else:
            close = price + (0.3 if i % 2 == 0 else -0.2)
        candles.append(
            {
                "ts": (start + timedelta(minutes=15 * i)).isoformat(),
                "o": price,
                "h": max(price, close) + 0.8,
                "l": min(price, close) - 0.8,
                "c": close,
                "v": 1000 + i * 4,
                "raw": {"i": i},
            }
        )
        price = close
    return candles


def make_client(tmp_path):
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'backtest.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_db():
        with SessionLocal() as db:
            yield db

    async def fake_fetcher(market: str, timeframe: str, count: int):
        return make_candles(max(count, 180))

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_candle_fetcher] = lambda: fake_fetcher
    return TestClient(app), SessionLocal


def seed_strategy(SessionLocal):
    with SessionLocal() as db:
        db.add(
            StrategyVersion(
                user_id=1,
                version=1,
                code_text=STRATEGY_CODE,
                prompt_used="test",
                source="fallback",
                validation_json='{"ok": true}',
            )
        )
        db.commit()


def test_backtest_returns_frontend_shape_and_persists_result(tmp_path):
    client, SessionLocal = make_client(tmp_path)
    seed_strategy(SessionLocal)

    response = client.post(
        "/api/backtest",
        json={
            "version": 1,
            "market": "KRW-BTC",
            "timeframe": "15",
            "from": "2026-05-01T00:00:00+09:00",
            "to": "2026-06-01T00:00:00+09:00",
            "fee_rate": 0.0005,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body["metrics"]) == {"totalReturn", "bhReturn", "vsBH", "winRate", "trades", "mdd"}
    assert len(body["equity"]) == len(body["bh"])
    assert len(body["candles"]) >= 120
    assert all(marker["type"] in {"BUY", "SELL"} for marker in body["markers"])
    assert body["metrics"]["trades"] == len([trade for trade in body["trades"] if trade["type"] == "SELL"])

    with SessionLocal() as db:
        results = db.execute(select(BacktestResult)).scalars().all()

    assert len(results) == 1
    assert results[0].market == "KRW-BTC"
    assert results[0].timeframe == "15"

    app.dependency_overrides.clear()


def test_backtest_rejects_missing_strategy_version(tmp_path):
    client, _ = make_client(tmp_path)

    response = client.post(
        "/api/backtest",
        json={"version": 999, "market": "KRW-BTC", "timeframe": "15", "fee_rate": 0.0005},
    )

    assert response.status_code == 404

    app.dependency_overrides.clear()
