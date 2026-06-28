import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.context_log import ContextLog
from app.models.response import SurveyResponse
from app.models.strategy_version import StrategyVersion
from app.models.survey import Survey
from app.services.llm_client import LLMClient
from app.services.sandbox_runner import StrategyExecutionError, StrategyValidationError, run_strategy, validate_strategy_code


class StrategyService:
    def __init__(self, db: Session, llm_client: LLMClient | None = None):
        self.db = db
        self.llm_client = llm_client or LLMClient()

    async def codify(self) -> dict[str, Any]:
        prompt = self._build_prompt()
        code = None
        source = "fallback"
        candidate_prompt = prompt
        for attempt in range(2):
            candidate = await self.llm_client.generate_strategy(candidate_prompt)
            ok, error = self._validate_strategy_candidate(candidate)
            if ok:
                code = candidate
                source = "llm"
                break
            if attempt == 0:
                candidate_prompt = self._build_retry_prompt(prompt, error)
        if source == "fallback":
            code = build_fallback_strategy(self._correction_texts())
        strategy = self._save_strategy(code=code, source=source, prompt=prompt)
        payload = self._strategy_payload(strategy)
        payload["consistency"] = self._calculate_consistency(strategy)
        if source == "fallback":
            payload["warning"] = "LLM unavailable; fallback strategy generated."
        return payload

    async def refine(self, correction_text: str) -> dict[str, Any]:
        self.db.add(
            ContextLog(
                user_id=1,
                type="correction",
                content_json=json.dumps({"correction_text": correction_text}, ensure_ascii=False),
            )
        )
        self.db.flush()
        return await self.codify()

    def get_strategy(self, version: int) -> dict[str, Any] | None:
        strategy = self._get_strategy_model(version)
        return self._strategy_payload(strategy) if strategy else None

    def get_consistency(self, version: int) -> dict[str, Any] | None:
        strategy = self._get_strategy_model(version)
        return self._calculate_consistency(strategy) if strategy else None

    def _save_strategy(self, code: str, source: str, prompt: str) -> StrategyVersion:
        validate_strategy_code(code)
        version = self._next_version()
        strategy = StrategyVersion(
            user_id=1,
            version=version,
            code_text=code,
            prompt_used=prompt,
            source=source,
            validation_json=json.dumps({"ok": True}, ensure_ascii=False),
        )
        self.db.add(strategy)
        self.db.commit()
        self.db.refresh(strategy)
        return strategy

    def _validate_strategy_candidate(self, code: str | None) -> tuple[bool, str]:
        if not code:
            return False, "LLM returned no code"
        try:
            validate_strategy_code(code)
            run_strategy(
                code,
                {"rsi14": 50, "vol_ratio": 1, "ma_align": "혼조"},
                {"holding": False, "entry_price": None, "pnl_pct": 0},
            )
        except (StrategyExecutionError, StrategyValidationError) as exc:
            return False, f"{type(exc).__name__}: {exc}"
        return True, ""

    def _next_version(self) -> int:
        current = self.db.execute(select(func.max(StrategyVersion.version)).where(StrategyVersion.user_id == 1)).scalar()
        return int(current or 0) + 1

    def _get_strategy_model(self, version: int) -> StrategyVersion | None:
        return self.db.execute(
            select(StrategyVersion).where(StrategyVersion.user_id == 1, StrategyVersion.version == version)
        ).scalar_one_or_none()

    def _strategy_payload(self, strategy: StrategyVersion) -> dict[str, Any]:
        created_at = strategy.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return {
            "version": strategy.version,
            "source": strategy.source,
            "code": strategy.code_text,
            "created_at": created_at.isoformat(),
        }

    def _calculate_consistency(self, strategy: StrategyVersion) -> dict[str, Any]:
        responses = self.db.execute(
            select(SurveyResponse).where(SurveyResponse.user_id == 1).order_by(SurveyResponse.survey_id)
        ).scalars()
        total = 0
        matches = 0
        mismatches = []
        for response in responses:
            survey = self.db.get(Survey, response.survey_id)
            if survey is None:
                continue
            total += 1
            features = json.loads(survey.features_json)
            result = run_strategy(
                strategy.code_text,
                features,
                {"holding": False, "entry_price": None, "pnl_pct": 0},
            )
            if result["action"] == response.action:
                matches += 1
            else:
                mismatches.append({"survey": response.survey_id, "user": response.action, "strategy": result["action"]})
        return {
            "pct": round(matches / total * 100) if total else 0,
            "total": total,
            "match": matches,
            "mismatches": mismatches,
        }

    def _build_prompt(self) -> str:
        rows = []
        responses = self.db.execute(
            select(SurveyResponse).where(SurveyResponse.user_id == 1).order_by(SurveyResponse.survey_id)
        ).scalars()
        for response in responses:
            survey = self.db.get(Survey, response.survey_id)
            if survey is None:
                continue
            rows.append(
                {
                    "survey_id": response.survey_id,
                    "action": response.action,
                    "reasoning": response.reasoning_text,
                    "features": json.loads(survey.features_json),
                }
            )
        return json.dumps(
            {
                "task": "Create Python decide(features, position) returning BUY, SELL, or HOLD.",
                "responses": rows,
                "corrections": self._correction_texts(),
                "rules": [
                    "return only Python code, no markdown",
                    "define exactly def decide(features: dict, position: dict) -> dict",
                    "return a dict with action and reason on every path",
                    "action must be BUY, SELL, or HOLD",
                    "do not use import, try/except, while, class, lambda, with, raise, open, eval, exec, getattr",
                    "do not use isinstance or type checks; inputs are already normalized dictionaries",
                    "use float(features.get('rsi14', 50) or 50) and bool(position.get('holding', False)) defaults",
                ],
            },
            ensure_ascii=False,
        )

    def _build_retry_prompt(self, original_prompt: str, validation_error: str) -> str:
        return (
            original_prompt
            + "\n\nPrevious code failed validation: "
            + validation_error
            + "\nReturn corrected code only. Do not use try/except, imports, classes, while loops, file access, "
            "network access, eval, exec, isinstance, type checks, or markdown. Use float(features.get('rsi14', 50) or 50) "
            "style defaults. Every return must include both action and reason."
        )

    def _correction_texts(self) -> list[str]:
        logs = self.db.execute(
            select(ContextLog).where(ContextLog.user_id == 1, ContextLog.type == "correction").order_by(ContextLog.id)
        ).scalars()
        corrections = []
        for log in logs:
            content = json.loads(log.content_json)
            if "correction_text" in content:
                corrections.append(str(content["correction_text"]))
        return corrections


def build_fallback_strategy(corrections: list[str] | None = None) -> str:
    rsi_buy = 42
    vol_buy = 1.05
    rsi_sell = 60
    pnl_take = 10
    pnl_stop = -6
    for correction in corrections or []:
        lowered = correction.lower()
        if "손절" in correction or "stop" in lowered or "리스크" in correction:
            pnl_stop = min(-2, pnl_stop + 1)
        if "거래량" in correction or "volume" in lowered or "엄격" in correction:
            vol_buy = round(vol_buy + 0.2, 2)
        if "익절" in correction or "목표" in correction or "수익" in correction:
            pnl_take += 1.5
        if "rsi" in lowered or "과매도" in correction or "공격" in correction:
            rsi_buy = min(45, rsi_buy + 2)

    return f'''def decide(features: dict, position: dict) -> dict:
    rsi = float(features.get("rsi14", 50))
    vol = float(features.get("vol_ratio", 1))
    align = features.get("ma_align", "혼조")
    holding = bool(position.get("holding", False))
    pnl = float(position.get("pnl_pct", 0))

    if (not holding) and rsi < {rsi_buy} and vol > {vol_buy}:
        return {{"action": "BUY", "reason": f"RSI {{rsi:.0f}} 과매도 + 거래량 {{vol:.1f}}x"}}

    if holding and (rsi > {rsi_sell} or pnl > {pnl_take} or pnl < {pnl_stop}):
        return {{"action": "SELL", "reason": "과열 또는 목표/손절 도달"}}

    return {{"action": "HOLD", "reason": "조건 불충족 - 관망"}}
'''
