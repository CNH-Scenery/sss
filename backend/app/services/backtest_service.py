import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.backtest_result import BacktestResult
from app.models.strategy_version import StrategyVersion
from app.services.candle_cache import CandleCache
from app.services.feature_engine import calculate_features
from app.services.sandbox_runner import run_strategy
from app.services.upbit_client import UpbitClient


CandleFetcher = Callable[[str, str, int], Awaitable[list[dict[str, Any]]]]


class BacktestService:
    def __init__(self, db: Session, candle_fetcher: CandleFetcher | None = None):
        self.db = db
        self.candle_fetcher = candle_fetcher

    async def run(
        self,
        version: int,
        market: str,
        timeframe: str,
        from_ts: datetime | None,
        to: datetime | None,
        fee_rate: float,
    ) -> dict[str, Any]:
        strategy = self._get_strategy(version)
        if strategy is None:
            raise ValueError("strategy not found")

        candles = await self._get_candles(market, timeframe, 200)
        candles = _filter_period(candles, from_ts, to)
        if len(candles) < 30:
            raise ValueError("not enough candles for backtest")

        result = self._simulate(strategy.code_text, candles, fee_rate)
        self._save_result(strategy, market, timeframe, from_ts, to, result)
        return result

    def _get_strategy(self, version: int) -> StrategyVersion | None:
        return self.db.execute(
            select(StrategyVersion).where(StrategyVersion.user_id == 1, StrategyVersion.version == version)
        ).scalar_one_or_none()

    async def _get_candles(self, market: str, timeframe: str, count: int) -> list[dict[str, Any]]:
        if self.candle_fetcher is not None:
            return await self.candle_fetcher(market, timeframe, count)
        settings = get_settings()
        async with UpbitClient(base_url=settings.upbit_base_url) as client:
            return await CandleCache(self.db, client).get_candles(market, timeframe, count)

    def _simulate(self, code: str, candles: list[dict[str, Any]], fee_rate: float) -> dict[str, Any]:
        holding = False
        entry_price = 0.0
        entry_equity = 1.0
        equity = 1.0
        equity_curve = []
        buy_hold_curve = []
        trades = []
        markers = []
        first_price = float(candles[0]["c"])

        for i in range(20, len(candles)):
            price = float(candles[i]["c"])
            pnl_pct = (price - entry_price) / entry_price * 100 if holding else 0.0
            features = calculate_features(candles[: i + 1])
            decision = run_strategy(
                code,
                features,
                {"holding": holding, "entry_price": entry_price if holding else None, "pnl_pct": pnl_pct},
            )
            action = decision["action"]
            if action == "BUY" and not holding:
                holding = True
                entry_price = price
                equity *= 1 - fee_rate
                entry_equity = equity
                trade = {"i": i, "ts": candles[i].get("ts"), "type": "BUY", "price": price}
                trades.append(trade)
                markers.append({"i": i, "type": "BUY"})
            elif action == "SELL" and holding:
                equity *= price / entry_price * (1 - fee_rate)
                return_pct = (equity / entry_equity - 1) * 100
                trade = {
                    "i": i,
                    "ts": candles[i].get("ts"),
                    "type": "SELL",
                    "price": price,
                    "return_pct": return_pct,
                }
                trades.append(trade)
                markers.append({"i": i, "type": "SELL"})
                holding = False
                entry_price = 0.0
                entry_equity = equity

            current_equity = equity * (price / entry_price) if holding and entry_price else equity
            equity_curve.append(current_equity)
            buy_hold_curve.append(price / first_price if first_price else 1.0)

        closed_returns = [trade["return_pct"] for trade in trades if trade["type"] == "SELL"]
        total_return = (equity_curve[-1] - 1) * 100 if equity_curve else 0.0
        bh_return = (buy_hold_curve[-1] - 1) * 100 if buy_hold_curve else 0.0
        wins = len([value for value in closed_returns if value > 0])
        win_rate = wins / len(closed_returns) * 100 if closed_returns else 0.0
        mdd = _max_drawdown(equity_curve)
        metrics = {
            "totalReturn": total_return,
            "bhReturn": bh_return,
            "vsBH": total_return - bh_return,
            "winRate": win_rate,
            "trades": len(closed_returns),
            "mdd": mdd,
        }
        chart_candles = [
            {
                "ts": candle.get("ts"),
                "o": float(candle["o"]),
                "h": float(candle["h"]),
                "l": float(candle["l"]),
                "c": float(candle["c"]),
                "v": float(candle["v"]),
            }
            for candle in candles
        ]
        return {
            "metrics": metrics,
            "trades": trades,
            "equity": equity_curve,
            "eq": equity_curve,
            "bh": buy_hold_curve,
            "markers": markers,
            "candles": chart_candles,
        }

    def _save_result(
        self,
        strategy: StrategyVersion,
        market: str,
        timeframe: str,
        from_ts: datetime | None,
        to: datetime | None,
        result: dict[str, Any],
    ) -> None:
        self.db.add(
            BacktestResult(
                user_id=1,
                strategy_version_id=strategy.id,
                market=market,
                timeframe=timeframe,
                period_json=json.dumps(
                    {"from": from_ts.isoformat() if from_ts else None, "to": to.isoformat() if to else None},
                    ensure_ascii=False,
                ),
                metrics_json=json.dumps(result["metrics"], ensure_ascii=False),
                trades_json=json.dumps(result["trades"], ensure_ascii=False),
                equity_json=json.dumps({"equity": result["equity"], "bh": result["bh"]}, ensure_ascii=False),
                markers_json=json.dumps(result["markers"], ensure_ascii=False),
            )
        )
        self.db.commit()


def _filter_period(
    candles: list[dict[str, Any]],
    from_ts: datetime | None,
    to: datetime | None,
) -> list[dict[str, Any]]:
    if from_ts is None and to is None:
        return candles
    output = []
    for candle in candles:
        ts = datetime.fromisoformat(str(candle["ts"]))
        if from_ts is not None and ts < from_ts:
            continue
        if to is not None and ts > to:
            continue
        output.append(candle)
    return output


def _max_drawdown(values: list[float]) -> float:
    peak = 0.0
    mdd = 0.0
    for value in values:
        peak = max(peak, value)
        if peak:
            mdd = min(mdd, (value - peak) / peak * 100)
    return mdd
