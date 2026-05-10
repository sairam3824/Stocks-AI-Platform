from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

import numpy as np
import pandas as pd

from .forecast import forecast_close


@dataclass
class ModelScore:
    model_name: str
    mape: float
    rmse: float


@dataclass
class BacktestResult:
    selected_model: str
    scores: List[ModelScore]


def _mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.abs((y_true - y_pred) / y_true)
        ratio = ratio[np.isfinite(ratio)]
    if ratio.size == 0:
        return 999.0
    return float(ratio.mean() * 100.0)


def _rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    if y_true.size == 0:
        return 999.0
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def evaluate_models(
    history: pd.DataFrame,
    freq: str = "B",
    candidates: Iterable[str] | None = None,
) -> BacktestResult:
    candidates = list(candidates or ("auto", "stat", "best"))
    if history.empty or len(history) < 40:
        return BacktestResult(selected_model="auto", scores=[])

    holdout = max(5, min(21, len(history) // 5))
    train = history.iloc[:-holdout]
    test = history.iloc[-holdout:]
    true = test["close"].astype(float).values
    scores: List[ModelScore] = []

    for candidate in candidates:
        try:
            result = forecast_close(train, horizon=holdout, freq=freq, model_preference=candidate)
            pred = result.forecast["forecast"].astype(float).values[:holdout]
            scores.append(
                ModelScore(
                    model_name=result.model_name,
                    mape=_mape(true, pred),
                    rmse=_rmse(true, pred),
                )
            )
        except Exception:
            continue

    if not scores:
        return BacktestResult(selected_model="auto", scores=[])
    scores.sort(key=lambda s: (s.mape, s.rmse))
    selected = scores[0].model_name
    if "ARIMA" in selected:
        pref = "stat"
    elif "ETS" in selected:
        pref = "stat"
    elif "LSTM" in selected:
        pref = "lstm"
    elif "TFT" in selected:
        pref = "tft"
    else:
        pref = "best"
    return BacktestResult(selected_model=pref, scores=scores)
