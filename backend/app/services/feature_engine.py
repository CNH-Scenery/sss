from collections.abc import Mapping, Sequence


def _values(candles: Sequence[Mapping[str, float]], key: str) -> list[float]:
    return [float(candle[key]) for candle in candles]


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _moving_average(values: Sequence[float], period: int) -> float:
    window = list(values[-min(period, len(values)) :])
    return _mean(window)


def _rsi(closes: Sequence[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0

    avg_gain = 0.0
    avg_loss = 0.0
    for i in range(1, period + 1):
        change = closes[i] - closes[i - 1]
        if change > 0:
            avg_gain += change
        else:
            avg_loss -= change

    avg_gain /= period
    avg_loss /= period

    for i in range(period + 1, len(closes)):
        change = closes[i] - closes[i - 1]
        gain = change if change > 0 else 0.0
        loss = -change if change < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    rs = avg_gain / (avg_loss or 1e-9)
    return 100 - 100 / (1 + rs)


def _ema_series(values: Sequence[float], period: int) -> list[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    ema = float(values[0])
    output = [ema]
    for value in values[1:]:
        ema = float(value) * multiplier + ema * (1 - multiplier)
        output.append(ema)
    return output


def _percent_change(current: float, previous: float | None) -> float:
    if previous in (None, 0):
        return 0.0
    return (current - previous) / previous * 100


def calculate_features(candles: Sequence[Mapping[str, float]]) -> dict[str, float | str]:
    if not candles:
        raise ValueError("at least one candle is required")

    closes = _values(candles, "c")
    volumes = _values(candles, "v")
    highs = _values(candles, "h")
    lows = _values(candles, "l")
    last = closes[-1]

    ma5 = _moving_average(closes, 5)
    ma7 = _moving_average(closes, 7)
    ma20 = _moving_average(closes, 20)
    ma25 = _moving_average(closes, 25)
    ma30 = _moving_average(closes, 30)
    ma60 = _moving_average(closes, 60)
    ma99 = _moving_average(closes, 99)
    ma120 = _moving_average(closes, 120)

    if ma7 > ma25 > ma99:
        ma_align = "정배열"
    elif ma7 < ma25 < ma99:
        ma_align = "역배열"
    else:
        ma_align = "혼조"

    ema12 = _ema_series(closes, 12)
    ema26 = _ema_series(closes, 26)
    macd_series = [fast - slow for fast, slow in zip(ema12, ema26)]
    macd_signal_series = _ema_series(macd_series, 9)
    macd = macd_series[-1] if macd_series else 0.0
    macd_signal = macd_signal_series[-1] if macd_signal_series else 0.0

    bollinger_window = closes[-min(20, len(closes)) :]
    bollinger_mean = _mean(bollinger_window)
    variance = _mean([(value - bollinger_mean) ** 2 for value in bollinger_window])
    stddev = variance**0.5
    upper = bollinger_mean + 2 * stddev
    lower = bollinger_mean - 2 * stddev
    band_width = upper - lower
    bb_pct = (last - lower) / (band_width or 1)
    bb_width = band_width / bollinger_mean if bollinger_mean else 0.0

    true_ranges = []
    for i in range(1, len(candles)):
        true_ranges.append(
            max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
        )
    atr = _mean(true_ranges) if true_ranges else highs[-1] - lows[-1]

    recent_volume = volumes[-min(20, len(volumes)) :]
    vol_ratio = volumes[-1] / (_mean(recent_volume) or 1)
    high20 = max(highs[-min(20, len(highs)) :])
    low20 = min(lows[-min(20, len(lows)) :])

    return {
        "close": last,
        "ret_1": _percent_change(last, closes[-2] if len(closes) >= 2 else None),
        "ret_5": _percent_change(last, closes[-6] if len(closes) >= 6 else None),
        "ma5": ma5,
        "ma7": ma7,
        "ma20": ma20,
        "ma25": ma25,
        "ma30": ma30,
        "ma60": ma60,
        "ma99": ma99,
        "ma120": ma120,
        "ma_align": ma_align,
        "rsi14": _rsi(closes, 14),
        "macd": macd,
        "macd_signal": macd_signal,
        "bb_pct": bb_pct,
        "bb_width": bb_width,
        "atr": atr,
        "atr_pct": atr / last * 100 if last else 0.0,
        "vol_ratio": vol_ratio,
        "dist_from_high20": (last - high20) / high20 * 100 if high20 else 0.0,
        "dist_from_low20": (last - low20) / low20 * 100 if low20 else 0.0,
    }
