from src.news import NewsItem
from src.sentiment import SentimentResult, analyze_sentiment, analyze_sentiment_lexicon


def _items(*titles: str) -> list[NewsItem]:
    return [NewsItem(title=title, summary="", link="", published="") for title in titles]


def test_lexicon_sentiment_detects_positive_and_negative() -> None:
    positive = analyze_sentiment_lexicon(_items("AAPL beats earnings and raises guidance"))
    negative = analyze_sentiment_lexicon(_items("AAPL faces lawsuit after weak outlook downgrade"))
    assert positive is not None and positive.label == "Positive" and positive.score > 0
    assert negative is not None and negative.label == "Negative" and negative.score < 0


def test_auto_sentiment_blends_ollama_with_lexicon(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.sentiment.analyze_sentiment_ollama",
        lambda *args, **kwargs: SentimentResult(score=0.9, label="Positive"),
    )
    result = analyze_sentiment(
        _items("AAPL stock hit by lawsuit and selloff concerns"),
        provider="auto",
        ollama_model="llama3",
        llm_weight=0.6,
    )
    assert result is not None
    assert -1.0 <= result.score <= 1.0
    assert result.label in {"Positive", "Neutral", "Negative"}


def test_ollama_provider_falls_back_to_lexicon(monkeypatch) -> None:
    monkeypatch.setattr("src.sentiment.analyze_sentiment_ollama", lambda *args, **kwargs: None)
    result = analyze_sentiment(
        _items("MSFT posts strong growth and upbeat outlook"),
        provider="ollama",
        ollama_model="llama3",
    )
    assert result is not None
    assert result.label == "Positive"
