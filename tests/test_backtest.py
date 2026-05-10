import pandas as pd

from src.backtest import evaluate_models


def test_backtest_returns_selection_for_sufficient_history() -> None:
    history = pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=120, freq="B"),
            "close": [100 + i * 0.2 for i in range(120)],
        }
    )
    result = evaluate_models(history, freq="B")
    assert result.selected_model in {"auto", "stat", "best", "lstm", "tft"}
