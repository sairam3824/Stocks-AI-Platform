import requests

from src.news import NewsItem, fetch_news


def test_fetch_news_mixed_dedupes_and_limits(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.news.fetch_news_rss",
        lambda *args, **kwargs: [
            NewsItem(title="AAPL beats earnings", summary="", link="", published="", source="rss"),
            NewsItem(title="MSFT cloud growth", summary="", link="", published="", source="rss"),
        ],
    )
    monkeypatch.setattr(
        "src.news.fetch_news_serpapi",
        lambda *args, **kwargs: [
            NewsItem(title="AAPL beats earnings", summary="", link="", published="", source="serpapi"),
            NewsItem(title="NVDA AI demand jumps", summary="", link="", published="", source="serpapi"),
        ],
    )
    monkeypatch.setattr("src.news.fetch_news_reddit", lambda *args, **kwargs: [])
    monkeypatch.setattr("src.news.fetch_news_x", lambda *args, **kwargs: [])

    items = fetch_news(symbol="AAPL", template="http://example/{symbol}", source="mixed", max_items=3)
    titles = [item.title for item in items]
    assert len(items) == 3
    assert titles.count("AAPL beats earnings") == 1


def test_fetch_news_non_rss_source_falls_back_to_rss(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.news._load_items_for_source",
        lambda *args, **kwargs: (_ for _ in ()).throw(requests.RequestException("boom")),
    )
    monkeypatch.setattr(
        "src.news.fetch_news_rss",
        lambda *args, **kwargs: [NewsItem(title="fallback", summary="", link="", published="", source="rss")],
    )
    items = fetch_news(symbol="AAPL", template="http://example/{symbol}", source="mixed", max_items=5)
    assert len(items) == 1
    assert items[0].title == "fallback"
