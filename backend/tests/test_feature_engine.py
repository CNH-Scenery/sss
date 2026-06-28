from app.services.feature_engine import calculate_features


def make_trend_candles(count: int, start: float = 100.0, step: float = 1.0, volume: float = 100.0):
    candles = []
    price = start
    for i in range(count):
        close = price + step
        candles.append(
            {
                "o": price,
                "h": max(price, close) + 0.5,
                "l": min(price, close) - 0.5,
                "c": close,
                "v": volume + i,
            }
        )
        price = close
    return candles


def test_calculate_features_returns_frontend_and_plan_schema_fields():
    features = calculate_features(make_trend_candles(130))

    assert set(features) == {
        "close",
        "ret_1",
        "ret_5",
        "ma5",
        "ma7",
        "ma20",
        "ma25",
        "ma30",
        "ma60",
        "ma99",
        "ma120",
        "ma_align",
        "rsi14",
        "macd",
        "macd_signal",
        "bb_pct",
        "bb_width",
        "atr",
        "atr_pct",
        "vol_ratio",
        "dist_from_high20",
        "dist_from_low20",
    }


def test_calculate_features_classifies_rising_and_falling_rsi_and_ma_alignment():
    rising = calculate_features(make_trend_candles(130, step=1.0))
    falling = calculate_features(make_trend_candles(130, start=300.0, step=-1.0))

    assert rising["rsi14"] > 90
    assert rising["ma_align"] == "정배열"
    assert falling["rsi14"] < 10
    assert falling["ma_align"] == "역배열"


def test_calculate_features_uses_latest_volume_over_recent_20_average():
    candles = make_trend_candles(25, volume=100.0)
    candles[-1]["v"] = 400.0

    features = calculate_features(candles)

    recent_average = sum(candle["v"] for candle in candles[-20:]) / 20
    assert features["vol_ratio"] == 400.0 / recent_average
