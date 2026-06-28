import re

import httpx

from app.config import Settings, get_settings


class LLMClient:
    def __init__(
        self,
        settings: Settings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 45.0,
    ):
        self.settings = settings or get_settings()
        self.transport = transport
        self.timeout = timeout

    async def generate_strategy(self, prompt: str) -> str | None:
        api_key = self.settings.effective_llm_api_key
        if not api_key:
            return None

        url = self.settings.llm_base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.settings.llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You write only safe Python code. Return exactly one function named "
                        "decide(features: dict, position: dict) -> dict. Do not use imports, "
                        "file access, network access, classes, isinstance, try/except, loops that can run forever, "
                        "or markdown prose. Use float(features.get('rsi14', 50) or 50) style defaults."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return _extract_python_code(str(content))
        except Exception:
            return None


def _extract_python_code(content: str) -> str:
    stripped = content.strip()
    fenced = re.search(r"```(?:python|py)?\s*(.*?)```", stripped, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    return stripped
