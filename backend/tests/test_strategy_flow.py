from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.api.surveys import get_candle_fetcher
from app.db import Base, create_engine_from_url, get_db
from app.main import app
from app.models.context_log import ContextLog
from app.models.strategy_version import StrategyVersion
from app.services.strategy_service import StrategyService


KST = timezone(timedelta(hours=9))


def make_candles(count: int = 200):
    start = datetime(2026, 6, 1, 9, 0, tzinfo=KST)
    candles = []
    price = 100.0
    for i in range(count):
        close = price - 0.3 if i % 2 else price + 0.2
        candles.append(
            {
                "ts": (start + timedelta(minutes=15 * i)).isoformat(),
                "o": price,
                "h": max(price, close) + 1.0,
                "l": min(price, close) - 1.0,
                "c": close,
                "v": 200.0 + i * 3,
                "raw": {"i": i},
            }
        )
        price = close
    return candles


def make_client(tmp_path):
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'strategy_flow.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_db():
        with SessionLocal() as db:
            yield db

    async def fake_fetcher(market: str, timeframe: str, count: int):
        return make_candles(count)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_candle_fetcher] = lambda: fake_fetcher
    return TestClient(app), SessionLocal


def seed_responses(client: TestClient):
    surveys = client.post("/api/surveys/generate", json={"market": "KRW-BTC", "timeframe": "15", "n": 2}).json()[
        "surveys"
    ]
    client.post("/api/responses", json={"survey_id": surveys[0]["id"], "action": "BUY", "reasoning": "buy dip"})
    client.post("/api/responses", json={"survey_id": surveys[1]["id"], "action": "HOLD", "reasoning": "wait"})


def test_codify_creates_fallback_strategy_version_and_consistency(tmp_path):
    client, SessionLocal = make_client(tmp_path)
    seed_responses(client)

    response = client.post("/api/strategy/codify", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert body["source"] == "fallback"
    assert "def decide(features: dict, position: dict) -> dict:" in body["code"]
    assert body["consistency"]["total"] == 2
    assert body["consistency"]["match"] + len(body["consistency"]["mismatches"]) == 2

    read_response = client.get("/api/strategy/1")
    consistency_response = client.get("/api/strategy/1/consistency")

    assert read_response.status_code == 200
    assert read_response.json()["version"] == 1
    assert consistency_response.status_code == 200
    assert consistency_response.json()["total"] == 2

    with SessionLocal() as db:
        versions = db.execute(select(StrategyVersion)).scalars().all()

    assert len(versions) == 1
    assert versions[0].source == "fallback"

    app.dependency_overrides.clear()


def test_refine_logs_correction_and_creates_next_strategy_version(tmp_path):
    client, SessionLocal = make_client(tmp_path)
    seed_responses(client)
    client.post("/api/strategy/codify", json={})

    response = client.post("/api/strategy/refine", json={"correction_text": "손절을 더 빠르게 잡아줘."})

    assert response.status_code == 200
    assert response.json()["version"] == 2

    with SessionLocal() as db:
        versions = db.execute(select(StrategyVersion).order_by(StrategyVersion.version)).scalars().all()
        logs = db.execute(select(ContextLog).where(ContextLog.type == "correction")).scalars().all()

    assert [version.version for version in versions] == [1, 2]
    assert len(logs) == 1

    app.dependency_overrides.clear()


class FakeLLM:
    def __init__(self, code: str | None):
        self.code = code
        self.prompts: list[str] = []

    async def generate_strategy(self, prompt: str) -> str | None:
        self.prompts.append(prompt)
        return self.code


class SequenceLLM:
    def __init__(self, codes: list[str | None]):
        self.codes = codes
        self.prompts: list[str] = []

    async def generate_strategy(self, prompt: str) -> str | None:
        self.prompts.append(prompt)
        return self.codes.pop(0)


def test_strategy_service_saves_valid_llm_code_as_llm_source(tmp_path):
    client, SessionLocal = make_client(tmp_path)
    seed_responses(client)
    code = (
        "def decide(features: dict, position: dict) -> dict:\n"
        "    return {\"action\": \"HOLD\", \"reason\": \"valid llm\"}"
    )

    with SessionLocal() as db:
        result = run_async(StrategyService(db, llm_client=FakeLLM(code)).codify())

    assert result["source"] == "llm"
    assert result["code"] == code

    app.dependency_overrides.clear()


def test_strategy_service_falls_back_when_llm_code_fails_result_validation(tmp_path):
    client, SessionLocal = make_client(tmp_path)
    seed_responses(client)
    invalid_code = "def decide(features: dict, position: dict) -> dict:\n    return {\"action\": \"HOLD\"}"

    with SessionLocal() as db:
        result = run_async(StrategyService(db, llm_client=FakeLLM(invalid_code)).codify())

    assert result["source"] == "fallback"
    assert "warning" in result
    assert "reason" in result["code"]

    app.dependency_overrides.clear()


def test_strategy_service_retries_llm_once_with_validation_feedback(tmp_path):
    client, SessionLocal = make_client(tmp_path)
    seed_responses(client)
    invalid_code = (
        "def decide(features: dict, position: dict) -> dict:\n"
        "    try:\n"
        "        return {\"action\": \"HOLD\", \"reason\": \"bad\"}\n"
        "    except Exception:\n"
        "        return {\"action\": \"HOLD\", \"reason\": \"bad\"}"
    )
    valid_code = (
        "def decide(features: dict, position: dict) -> dict:\n"
        "    return {\"action\": \"HOLD\", \"reason\": \"valid retry\"}"
    )
    llm = SequenceLLM([invalid_code, valid_code])

    with SessionLocal() as db:
        result = run_async(StrategyService(db, llm_client=llm).codify())

    assert result["source"] == "llm"
    assert result["code"] == valid_code
    assert len(llm.prompts) == 2
    assert "Previous code failed validation" in llm.prompts[1]

    app.dependency_overrides.clear()


def test_strategy_prompt_lists_sandbox_supported_python_only(tmp_path):
    _, SessionLocal = make_client(tmp_path)

    with SessionLocal() as db:
        prompt = StrategyService(db)._build_prompt()

    assert "do not use isinstance" in prompt
    assert "use float(features.get" in prompt
    assert "do not use import, try/except" in prompt

    app.dependency_overrides.clear()


def run_async(awaitable):
    import asyncio

    return asyncio.run(awaitable)
