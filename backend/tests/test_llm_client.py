import httpx
import pytest

from app.config import Settings
from app.services.llm_client import LLMClient


@pytest.mark.asyncio
async def test_llm_client_calls_openai_compatible_chat_completions_and_extracts_code():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("Authorization")
        seen["json"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "```python\n"
                            "def decide(features: dict, position: dict) -> dict:\n"
                            "    return {\"action\": \"HOLD\", \"reason\": \"wait\"}\n"
                            "```"
                        }
                    }
                ]
            },
        )

    settings = Settings(
        LLM_API_KEY="test-key",
        LLM_BASE_URL="https://api.example.test/v1",
        LLM_MODEL="codex-5.5-extrahigh",
    )
    client = LLMClient(settings=settings, transport=httpx.MockTransport(handler))

    code = await client.generate_strategy("make a strategy")

    assert seen["url"] == "https://api.example.test/v1/chat/completions"
    assert seen["authorization"] == "Bearer test-key"
    assert '"model":"codex-5.5-extrahigh"' in seen["json"]
    assert code == (
        "def decide(features: dict, position: dict) -> dict:\n"
        "    return {\"action\": \"HOLD\", \"reason\": \"wait\"}"
    )


@pytest.mark.asyncio
async def test_llm_client_returns_none_without_api_key():
    settings = Settings(LLM_API_KEY="", LLM_BASE_URL="https://api.example.test/v1")
    client = LLMClient(settings=settings)

    assert await client.generate_strategy("make a strategy") is None


@pytest.mark.asyncio
async def test_llm_client_returns_none_on_http_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "unavailable"})

    settings = Settings(LLM_API_KEY="test-key", LLM_BASE_URL="https://api.example.test/v1")
    client = LLMClient(settings=settings, transport=httpx.MockTransport(handler))

    assert await client.generate_strategy("make a strategy") is None


def test_settings_default_to_deepinfra_glm_model():
    settings = Settings()

    assert settings.llm_base_url == "https://api.deepinfra.com/v1/openai"
    assert settings.llm_model == "zai-org/GLM-5"
