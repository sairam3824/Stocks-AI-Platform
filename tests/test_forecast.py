import pandas as pd

from src.forecast import forecast_close


def test_forecast_fallback_short_history() -> None:
    history = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=2, freq="D"),
            "close": [100.0, 101.0],
        }
    )
    result = forecast_close(history, horizon=3, freq="D")
    assert len(result.forecast) == 3
    assert list(result.forecast.columns) == ["date", "forecast", "lower", "upper"]
