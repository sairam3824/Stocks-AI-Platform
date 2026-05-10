from src.recommendations import Recommendation
from src.trading import build_trade_candidates


def test_trade_candidates_filters_and_ranks() -> None:
    recs = [
        Recommendation(
            symbol="AAPL",
            expected_return_pct=4.0,
            signal="Upside",
            score=1.2,
            last_close=100.0,
            forecast_end=104.0,
            volatility_pct=2.0,
            sentiment_score=0.1,
            sentiment_label="Neutral",
            model_name="ETS",
            confidence_pct=72.0,
            reasoning="good",
        ),
        Recommendation(
            symbol="TSLA",
            expected_return_pct=-3.0,
            signal="Downside",
            score=0.9,
            last_close=200.0,
            forecast_end=194.0,
            volatility_pct=3.0,
            sentiment_score=-0.2,
            sentiment_label="Negative",
            model_name="ARIMA(1,1,1)",
            confidence_pct=65.0,
            reasoning="bad",
        ),
        Recommendation(
            symbol="MSFT",
            expected_return_pct=1.0,
            signal="Neutral",
            score=2.0,
            last_close=100.0,
            forecast_end=101.0,
            volatility_pct=1.0,
            sentiment_score=0.0,
            sentiment_label="Neutral",
            model_name="Linear",
            confidence_pct=90.0,
            reasoning="neutral",
        ),
    ]

    candidates = build_trade_candidates(recs, top_n=2, min_confidence_pct=60.0)
    assert len(candidates) == 2
    assert candidates[0].symbol == "AAPL"
    assert candidates[0].side == "BUY"
    assert candidates[1].symbol == "TSLA"
    assert candidates[1].side == "SELL"
