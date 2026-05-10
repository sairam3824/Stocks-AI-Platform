from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np
import pandas as pd

try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
except ImportError:  # pragma: no cover - handled by fallback
    ExponentialSmoothing = None

try:
    from statsmodels.tsa.arima.model import ARIMA
except ImportError:  # pragma: no cover - handled by fallback
    ARIMA = None

try:
    import torch
    import torch.nn as nn
except ImportError:  # pragma: no cover - optional dependency
    torch = None
    nn = None

try:
    from pytorch_forecasting import TimeSeriesDataSet, TemporalFusionTransformer
    from pytorch_forecasting.metrics import QuantileLoss
    import pytorch_lightning as pl
except ImportError:  # pragma: no cover - optional dependency
    TimeSeriesDataSet = None
    TemporalFusionTransformer = None
    QuantileLoss = None
    pl = None


@dataclass
class ForecastResult:
    history: pd.DataFrame
    forecast: pd.DataFrame
    model_name: str


def _fallback_linear_forecast(close: pd.Series, horizon: int) -> Tuple[np.ndarray, float]:
    y = close.values.astype(float)
    if len(y) < 2:
        forecast = np.repeat(y[-1] if len(y) else 0.0, horizon)
        return forecast, 0.0

    x = np.arange(len(y))
    slope, intercept = np.polyfit(x, y, 1)
    x_future = np.arange(len(y), len(y) + horizon)
    forecast = slope * x_future + intercept
    residuals = y - (slope * x + intercept)
    resid_std = float(np.std(residuals, ddof=1)) if len(y) > 2 else 0.0
    return forecast, resid_std


def _fit_ets(close: pd.Series, horizon: int) -> Tuple[np.ndarray, float, float]:
    if ExponentialSmoothing is None or len(close) < 10:
        raise ValueError("ETS not available or insufficient history")
    model = ExponentialSmoothing(
        close,
        trend="add",
        damped_trend=True,
        seasonal=None,
        initialization_method="estimated",
    )
    fit = model.fit(optimized=True, use_brute=True)
    forecast_values = fit.forecast(horizon).values
    residuals = close - fit.fittedvalues
    resid_std = float(residuals.std(ddof=1)) if len(residuals) > 2 else 0.0
    aic = float(getattr(fit, "aic", np.inf))
    return forecast_values, resid_std, aic


def _fit_arima(close: pd.Series, horizon: int) -> Tuple[np.ndarray, float, float]:
    if ARIMA is None or len(close) < 30:
        raise ValueError("ARIMA not available or insufficient history")
    model = ARIMA(close, order=(1, 1, 1))
    fit = model.fit()
    forecast_values = fit.forecast(steps=horizon).values
    residuals = fit.resid
    resid_std = float(np.std(residuals, ddof=1)) if len(residuals) > 2 else 0.0
    aic = float(getattr(fit, "aic", np.inf))
    return forecast_values, resid_std, aic


def _mape(actual: np.ndarray, forecast: np.ndarray) -> float:
    actual = np.array(actual, dtype=float)
    forecast = np.array(forecast, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = np.abs((actual - forecast) / actual)
        pct = np.where(np.isfinite(pct), pct, np.nan)
    value = np.nanmean(pct)
    if np.isnan(value):
        return float(np.mean(np.abs(actual - forecast)))
    return float(value)


def _select_best_stat_model(close: pd.Series) -> str | None:
    if len(close) < 40:
        return None
    val_len = min(10, max(3, len(close) // 6))
    train = close.iloc[:-val_len]
    actual = close.iloc[-val_len:]
    candidates: list[tuple[str, float]] = []

    try:
        preds, _, _ = _fit_ets(train, val_len)
        candidates.append(("ETS", _mape(actual.values, preds)))
    except Exception:
        pass

    try:
        preds, _, _ = _fit_arima(train, val_len)
        candidates.append(("ARIMA(1,1,1)", _mape(actual.values, preds)))
    except Exception:
        pass

    try:
        preds, _ = _fallback_linear_forecast(train, val_len)
        candidates.append(("Linear", _mape(actual.values, preds)))
    except Exception:
        pass

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[1])
    return candidates[0][0]


def _lstm_forecast(close: pd.Series, horizon: int, seq_len: int = 20, epochs: int = 20) -> Tuple[np.ndarray, float]:
    if torch is None:
        raise ValueError("PyTorch not available")
    values = close.values.astype(np.float32)
    if len(values) <= seq_len + 1:
        raise ValueError("Not enough data for LSTM")

    mean = values.mean()
    std = values.std() if values.std() > 0 else 1.0
    norm = (values - mean) / std

    X = []
    y = []
    for i in range(len(norm) - seq_len):
        X.append(norm[i : i + seq_len])
        y.append(norm[i + seq_len])
    X = np.array(X)
    y = np.array(y)

    X_tensor = torch.tensor(X).unsqueeze(-1)
    y_tensor = torch.tensor(y).unsqueeze(-1)

    class LSTMModel(nn.Module):
        def __init__(self, hidden_size=32):
            super().__init__()
            self.lstm = nn.LSTM(input_size=1, hidden_size=hidden_size, batch_first=True)
            self.fc = nn.Linear(hidden_size, 1)

        def forward(self, x):
            out, _ = self.lstm(x)
            out = out[:, -1, :]
            return self.fc(out)

    model = LSTMModel()
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)

    model.train()
    for _ in range(epochs):
        optimizer.zero_grad()
        output = model(X_tensor)
        loss = criterion(output, y_tensor)
        loss.backward()
        optimizer.step()

    model.eval()
    last_seq = torch.tensor(norm[-seq_len:]).unsqueeze(0).unsqueeze(-1)
    preds = []
    for _ in range(horizon):
        with torch.no_grad():
            next_val = model(last_seq).item()
        preds.append(next_val)
        next_seq = torch.cat([last_seq[:, 1:, :], torch.tensor([[[next_val]]])], dim=1)
        last_seq = next_seq

    preds = np.array(preds) * std + mean
    fitted = model(X_tensor).detach().numpy().flatten() * std + mean
    residuals = values[seq_len:] - fitted
    resid_std = float(np.std(residuals, ddof=1)) if len(residuals) > 2 else 0.0
    return preds, resid_std


def _tft_forecast(close: pd.Series, horizon: int) -> Tuple[np.ndarray, float]:
    if TimeSeriesDataSet is None or TemporalFusionTransformer is None or pl is None:
        raise ValueError("TFT dependencies not installed")

    values = close.values.astype(np.float32)
    if len(values) < 60:
        raise ValueError("Not enough data for TFT")

    df = pd.DataFrame(
        {
            "time_idx": np.arange(len(values)),
            "value": values,
            "group": "series",
        }
    )

    max_encoder_length = min(60, len(values) - horizon)
    max_prediction_length = horizon
    training_cutoff = len(values) - horizon

    training = TimeSeriesDataSet(
        df[lambda x: x.time_idx <= training_cutoff],
        time_idx="time_idx",
        target="value",
        group_ids=["group"],
        max_encoder_length=max_encoder_length,
        max_prediction_length=max_prediction_length,
        time_varying_unknown_reals=["value"],
    )

    train_loader = training.to_dataloader(train=True, batch_size=32, num_workers=0)

    tft = TemporalFusionTransformer.from_dataset(
        training,
        learning_rate=0.03,
        hidden_size=16,
        attention_head_size=1,
        dropout=0.1,
        hidden_continuous_size=8,
        output_size=1,
        loss=QuantileLoss(),
    )

    trainer = pl.Trainer(max_epochs=5, enable_checkpointing=False, logger=False)
    trainer.fit(tft, train_loader)

    raw_predictions = tft.predict(training, mode="raw", return_x=False)
    preds = raw_predictions[:, 0].detach().cpu().numpy()[-horizon:]

    residuals = values[-len(preds) :] - preds
    resid_std = float(np.std(residuals, ddof=1)) if len(residuals) > 2 else 0.0
    return preds, resid_std


def forecast_close(
    history: pd.DataFrame,
    horizon: int = 5,
    freq: str = "B",
    model_preference: str = "auto",
) -> ForecastResult:
    if history.empty:
        raise ValueError("History cannot be empty")

    df = history.copy()
    df = df.sort_values("date")
    close = df["close"].astype(float)

    forecast_values = None
    resid_std = 0.0
    model_name = "Linear"

    if model_preference == "tft":
        try:
            forecast_values, resid_std = _tft_forecast(close, horizon)
            model_name = "TFT"
        except Exception:
            forecast_values = None

    if model_preference == "lstm" and forecast_values is None:
        try:
            forecast_values, resid_std = _lstm_forecast(close, horizon)
            model_name = "LSTM"
        except Exception:
            forecast_values = None

    selected_model = None
    if model_preference in ("auto", "best"):
        selected_model = _select_best_stat_model(close)

    if selected_model == "ETS":
        try:
            forecast_values, resid_std, _ = _fit_ets(close, horizon)
            model_name = "ETS"
        except Exception:
            forecast_values = None
    elif selected_model == "ARIMA(1,1,1)":
        try:
            forecast_values, resid_std, _ = _fit_arima(close, horizon)
            model_name = "ARIMA(1,1,1)"
        except Exception:
            forecast_values = None
    elif selected_model == "Linear":
        forecast_values, resid_std = _fallback_linear_forecast(close, horizon)
        model_name = "Linear"

    if forecast_values is None:
        candidates = []
        try:
            ets_values, ets_std, ets_aic = _fit_ets(close, horizon)
            candidates.append(("ETS", ets_values, ets_std, ets_aic))
        except Exception:
            pass

        try:
            arima_values, arima_std, arima_aic = _fit_arima(close, horizon)
            candidates.append(("ARIMA(1,1,1)", arima_values, arima_std, arima_aic))
        except Exception:
            pass

        if candidates and model_preference in ("auto", "stat", "best"):
            candidates.sort(key=lambda item: item[3])
            model_name, forecast_values, resid_std, _ = candidates[0]
        else:
            forecast_values, resid_std = _fallback_linear_forecast(close, horizon)

    last_date = pd.Timestamp(df["date"].iloc[-1])
    future_dates = pd.date_range(start=last_date + pd.tseries.frequencies.to_offset(freq), periods=horizon, freq=freq)

    z = 1.96
    lower = forecast_values - z * resid_std
    upper = forecast_values + z * resid_std

    forecast_df = pd.DataFrame(
        {
            "date": future_dates,
            "forecast": forecast_values,
            "lower": lower,
            "upper": upper,
        }
    )

    return ForecastResult(history=df.reset_index(drop=True), forecast=forecast_df, model_name=model_name)
