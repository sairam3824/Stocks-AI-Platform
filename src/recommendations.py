from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from .skills import SkillProfile


@dataclass
class Recommendation:
    symbol: str
    expected_return_pct: float
    signal: str
    score: float
    last_close: float
    forecast_end: float
    volatility_pct: float
    sentiment_score: float
    sentiment_label: str
    model_name: str
    confidence_pct: float
    reasoning: str


def _compute_volatility(close: pd.Series, window: int = 60) -> float:
    returns = close.pct_change().dropna()
    if returns.empty:
        return 0.0
    recent = returns.tail(window)
    return float(recent.std(ddof=1) * 100)


def _compute_momentum(close: pd.Series, short_window: int = 20, long_window: int = 60) -> float:
    if close.empty:
        return 0.0
    short = close.tail(min(short_window, len(close))).mean()
    long = close.tail(min(long_window, len(close))).mean()
    if not long:
        return 0.0
    return float((short / long - 1.0) * 100.0)


def _scaled_tanh(value: float, scale: float) -> float:
    scale = max(1e-6, abs(scale))
    return math.tanh(value / scale)


def compute_recommendation(
    history: pd.DataFrame,
    forecast: pd.DataFrame,
    profile: SkillProfile,
    sentiment_score: float | None = None,
    sentiment_weight: float = 0.0,
    sentiment_label: str | None = None,
    model_name: str = "Unknown",
) -> Recommendation:
    if history.empty or forecast.empty:
        raise ValueError("History and forecast must be non-empty")

    last_close = float(history["close"].iloc[-1])
    forecast_end = float(forecast["forecast"].iloc[-1])
    if last_close == 0:
        expected_return_pct = 0.0
    else:
        expected_return_pct = (forecast_end / last_close - 1.0) * 100

    if expected_return_pct >= profile.min_return_pct:
        signal = "Upside"
    elif expected_return_pct <= -profile.max_drop_pct:
        signal = "Downside"
    else:
        signal = "Neutral"

    volatility_pct = _compute_volatility(history["close"].astype(float))
    momentum_pct = _compute_momentum(history["close"].astype(float))

    upper_end = float(forecast["upper"].iloc[-1])
    lower_end = float(forecast["lower"].iloc[-1])
    width = max(0.0, upper_end - lower_end)
    width_pct = (width / max(abs(forecast_end), 1.0)) * 100.0
    confidence_pct = max(0.0, min(100.0, 100.0 - min(90.0, (volatility_pct * 2.0) + (width_pct * 1.5))))

    if sentiment_score is None:
        sentiment_score = 0.0
    if sentiment_label is None:
        if sentiment_score >= 0.2:
            sentiment_label = "Positive"
        elif sentiment_score <= -0.2:
            sentiment_label = "Negative"
        else:
            sentiment_label = "Neutral"

    return_component = 2.2 * _scaled_tanh(expected_return_pct, 6.0)
    momentum_component = 0.8 * _scaled_tanh(momentum_pct, 4.0)
    confidence_component = 0.6 * ((confidence_pct - 50.0) / 50.0)
    downside_risk_pct = (max(0.0, last_close - lower_end) / max(last_close, 1e-6)) * 100.0
    risk_penalty = 0.7 * min(1.5, downside_risk_pct / 8.0)
    volatility_penalty = 0.3 * min(1.2, volatility_pct / 8.0)
    sentiment_component = sentiment_weight * sentiment_score

    score = (
        return_component
        + momentum_component
        + confidence_component
        + sentiment_component
        - risk_penalty
        - volatility_penalty
    )

    if signal == "Upside":
        direction = "Projected close is above the current close and clears your min return threshold."
    elif signal == "Downside":
        direction = "Projected close is below the current close and breaches your max drop threshold."
    else:
        direction = "Projected move stays within your configured thresholds."

    reasoning = (
        f"{direction} Model={model_name}, "
        f"Momentum={momentum_pct:.2f}%, Volatility={volatility_pct:.2f}%, "
        f"Sentiment={sentiment_label} ({sentiment_score:.2f})."
    )

    return Recommendation(
        symbol=profile.symbol,
        expected_return_pct=expected_return_pct,
        signal=signal,
        score=score,
        last_close=last_close,
        forecast_end=forecast_end,
        volatility_pct=volatility_pct,
        sentiment_score=sentiment_score,
        sentiment_label=sentiment_label,
        model_name=model_name,
        confidence_pct=confidence_pct,
        reasoning=reasoning,
    )
