import pandas as pd

from src.recommendations import compute_recommendation
from src.skills import SkillProfile


def test_recommendation_classification_edges() -> None:
    history = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=3, freq="D"),
            "close": [100.0, 101.0, 102.0],
        }
    )
    forecast = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-04", periods=2, freq="D"),
            "forecast": [104.0, 105.0],
            "lower": [103.0, 104.0],
            "upper": [105.0, 106.0],
        }
    )
    profile = SkillProfile(
        symbol="TEST",
        stooq_symbol=None,
        min_return_pct=2.0,
        max_drop_pct=2.0,
        notes="",
    )

    rec = compute_recommendation(history, forecast, profile)
    assert rec.signal == "Upside"


def test_recommendation_downside() -> None:
    history = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=3, freq="D"),
            "close": [100.0, 99.0, 98.0],
        }
    )
    forecast = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-04", periods=2, freq="D"),
            "forecast": [95.0, 94.0],
            "lower": [93.0, 92.0],
            "upper": [96.0, 95.0],
        }
    )
    profile = SkillProfile(
        symbol="TEST",
        stooq_symbol=None,
        min_return_pct=2.0,
        max_drop_pct=2.0,
        notes="",
    )

    rec = compute_recommendation(history, forecast, profile)
    assert rec.signal == "Downside"


def test_recommendation_score_responds_to_sentiment() -> None:
    history = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=10, freq="D"),
            "close": [100.0, 101.0, 102.0, 103.0, 102.5, 103.5, 104.0, 104.2, 105.0, 105.5],
        }
    )
    forecast = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-11", periods=2, freq="D"),
            "forecast": [106.0, 108.0],
            "lower": [104.0, 105.0],
            "upper": [109.0, 110.0],
        }
    )
    profile = SkillProfile(
        symbol="TEST",
        stooq_symbol=None,
        min_return_pct=2.0,
        max_drop_pct=2.0,
        notes="",
    )

    pos = compute_recommendation(
        history,
        forecast,
        profile,
        sentiment_score=0.8,
        sentiment_weight=0.4,
        sentiment_label="Positive",
    )
    neg = compute_recommendation(
        history,
        forecast,
        profile,
        sentiment_score=-0.8,
        sentiment_weight=0.4,
        sentiment_label="Negative",
    )
    assert pos.score > neg.score
