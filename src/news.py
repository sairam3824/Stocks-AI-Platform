from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Iterable, List, Optional

import feedparser
import requests


@dataclass
class NewsItem:
    title: str
    summary: str
    link: str
    published: str
    source: str = "news"


def fetch_news_rss(symbol: str, template: str, max_items: int = 8, timeout: int = 10) -> List[NewsItem]:
    url = template.format(symbol=symbol)
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()

    feed = feedparser.parse(response.text)
    items: List[NewsItem] = []
    for entry in feed.entries[:max_items]:
        items.append(
            NewsItem(
                title=entry.get("title", ""),
                summary=entry.get("summary", "") or entry.get("description", ""),
                link=entry.get("link", ""),
                published=entry.get("published", "") or entry.get("updated", ""),
                source="rss",
            )
        )

    return items


def fetch_news_serpapi(symbol: str, api_key: str, max_items: int = 8, timeout: int = 10) -> List[NewsItem]:
    if not api_key:
        return []
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_news",
        "q": f"{symbol} stock",
        "api_key": api_key,
    }
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    results = payload.get("news_results", []) or payload.get("organic_results", [])

    items: List[NewsItem] = []
    for entry in results[:max_items]:
        items.append(
            NewsItem(
                title=entry.get("title", ""),
                summary=entry.get("snippet", "") or entry.get("summary", ""),
                link=entry.get("link", ""),
                published=str(entry.get("date") or ""),
                source="serpapi",
            )
        )
    return items


def fetch_news_reddit(symbol: str, max_items: int = 8, timeout: int = 10) -> List[NewsItem]:
    url = "https://www.reddit.com/search.json"
    params = {
        "q": f"${symbol} stock",
        "sort": "new",
        "limit": max(10, max_items * 3),
        "t": "week",
        "restrict_sr": False,
    }
    headers = {"User-Agent": "stocks-ai/1.0"}
    response = requests.get(url, params=params, headers=headers, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    children = payload.get("data", {}).get("children", [])

    items: List[NewsItem] = []
    for child in children:
        post = child.get("data", {})
        title = str(post.get("title", "")).strip()
        if not title:
            continue
        permalink = str(post.get("permalink", "")).strip()
        link = f"https://www.reddit.com{permalink}" if permalink.startswith("/") else permalink
        created_utc = post.get("created_utc")
        published = ""
        if isinstance(created_utc, (int, float)):
            published = dt.datetime.utcfromtimestamp(float(created_utc)).isoformat() + "Z"
        items.append(
            NewsItem(
                title=title,
                summary=str(post.get("selftext", "")).strip(),
                link=link,
                published=published,
                source="reddit",
            )
        )
        if len(items) >= max_items:
            break
    return items


def fetch_news_x(
    symbol: str,
    bearer_token: str,
    max_items: int = 8,
    timeout: int = 10,
) -> List[NewsItem]:
    if not bearer_token:
        return []
    url = "https://api.twitter.com/2/tweets/search/recent"
    query = f"({symbol} OR ${symbol}) (stock OR earnings OR guidance) lang:en -is:retweet"
    headers = {"Authorization": f"Bearer {bearer_token}"}
    params = {
        "query": query,
        "max_results": min(100, max(10, max_items * 2)),
        "tweet.fields": "created_at",
    }
    response = requests.get(url, headers=headers, params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    tweets = payload.get("data", [])

    items: List[NewsItem] = []
    for tweet in tweets[:max_items]:
        text = str(tweet.get("text", "")).strip()
        if not text:
            continue
        tweet_id = str(tweet.get("id", "")).strip()
        link = f"https://x.com/i/web/status/{tweet_id}" if tweet_id else ""
        items.append(
            NewsItem(
                title=text[:140],
                summary=text,
                link=link,
                published=str(tweet.get("created_at", "") or ""),
                source="x",
            )
        )
    return items


def _dedupe_items(items: Iterable[NewsItem], max_items: int) -> List[NewsItem]:
    deduped: List[NewsItem] = []
    seen: set[str] = set()
    for item in items:
        key = item.title.strip().lower()
        if not item.title or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= max_items:
            break
    return deduped


def _load_items_for_source(
    source: str,
    symbol: str,
    template: str,
    max_items: int,
    timeout: int,
    serpapi_api_key: str,
    x_bearer_token: str,
) -> List[NewsItem]:
    source = source.strip().lower()
    if source == "serpapi":
        items = fetch_news_serpapi(symbol, serpapi_api_key, max_items=max_items, timeout=timeout)
        if items:
            return items
        return fetch_news_rss(symbol, template, max_items=max_items, timeout=timeout)
    if source == "reddit":
        return fetch_news_reddit(symbol, max_items=max_items, timeout=timeout)
    if source in ("x", "twitter"):
        return fetch_news_x(symbol, x_bearer_token, max_items=max_items, timeout=timeout)
    if source == "social":
        return _dedupe_items(
            [
                *fetch_news_reddit(symbol, max_items=max_items, timeout=timeout),
                *fetch_news_x(symbol, x_bearer_token, max_items=max_items, timeout=timeout),
            ],
            max_items=max_items,
        )
    if source in ("mixed", "all"):
        return _dedupe_items(
            [
                *fetch_news_rss(symbol, template, max_items=max_items, timeout=timeout),
                *fetch_news_serpapi(symbol, serpapi_api_key, max_items=max_items, timeout=timeout),
                *fetch_news_reddit(symbol, max_items=max_items, timeout=timeout),
                *fetch_news_x(symbol, x_bearer_token, max_items=max_items, timeout=timeout),
            ],
            max_items=max_items,
        )
    return fetch_news_rss(symbol, template, max_items=max_items, timeout=timeout)


def fetch_news(
    symbol: str,
    template: str,
    max_items: int = 8,
    timeout: int = 10,
    source: str = "rss",
    serpapi_api_key: Optional[str] = None,
    x_bearer_token: Optional[str] = None,
) -> List[NewsItem]:
    try:
        items = _load_items_for_source(
            source=source,
            symbol=symbol,
            template=template,
            max_items=max_items,
            timeout=timeout,
            serpapi_api_key=serpapi_api_key or "",
            x_bearer_token=x_bearer_token or "",
        )
        return _dedupe_items(items, max_items=max_items)
    except requests.RequestException:
        if source != "rss":
            return fetch_news_rss(symbol, template, max_items=max_items, timeout=timeout)
        return []
