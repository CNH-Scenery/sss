from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.api.surveys import get_candle_fetcher
from app.db import get_db
from app.services.backtest_service import BacktestService


router = APIRouter(prefix="/api", tags=["backtest"])
CandleFetcher = Callable[[str, str, int], Awaitable[list[dict[str, Any]]]]


class BacktestRequest(BaseModel):
    version: int
    market: str = "KRW-BTC"
    timeframe: str = "15"
    from_ts: datetime | None = None
    to: datetime | None = None
    fee_rate: float = Field(default=0.0005, ge=0, le=0.05)

    @model_validator(mode="before")
    @classmethod
    def map_from_alias(cls, data: Any) -> Any:
        if isinstance(data, dict) and "from" in data and "from_ts" not in data:
            return {**data, "from_ts": data["from"]}
        return data


@router.post("/backtest")
async def run_backtest(
    request: BacktestRequest,
    db: Session = Depends(get_db),
    candle_fetcher: CandleFetcher | None = Depends(get_candle_fetcher),
) -> dict[str, Any]:
    service = BacktestService(db=db, candle_fetcher=candle_fetcher)
    try:
        return await service.run(
            version=request.version,
            market=request.market,
            timeframe=request.timeframe,
            from_ts=request.from_ts,
            to=request.to,
            fee_rate=request.fee_rate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
