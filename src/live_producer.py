from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kafka import KafkaProducer
from kafka.errors import KafkaError

from .config import load_config, resolve_database_path
from .data_sources import fetch_twelve_data_quote, fetch_alpha_vantage_quote, fetch_yahoo_quote
from .db import increment_metric, list_all_stocks
from .observability import increment_counter, log_event


def _coerce_price(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _extract_twelve_data_price(quote: dict) -> float:
    # TwelveData quote commonly returns `close`; keep `price` for compatibility.
    for key in ("price", "close", "last", "previous_close"):
        price = _coerce_price(quote.get(key))
        if price > 0:
            return price
    return 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Poll live prices and push to Kafka")
    parser.add_argument("--config", default="config/portfolio.json")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    db_path = resolve_database_path(config)

    def record_metric(name: str, value: float = 1.0, tags: str = "") -> None:
        try:
            increment_metric(db_path, name, value, tags=tags)
        except Exception:
            pass

    def connect_producer() -> KafkaProducer:
        while True:
            try:
                return KafkaProducer(
                    bootstrap_servers=config.kafka_bootstrap_servers,
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                )
            except Exception as exc:
                print(f"[WARN] Kafka unavailable ({exc}). Retrying in 5s.")
                time.sleep(5)

    producer = connect_producer()

    def _normalize_timestamp(value) -> str:
        if value is None or value == "":
            return datetime.now(timezone.utc).isoformat()
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
        text = str(value)
        if text.isdigit():
            return datetime.fromtimestamp(int(text), tz=timezone.utc).isoformat()
        try:
            return datetime.fromisoformat(text).isoformat()
        except ValueError:
            return datetime.now(timezone.utc).isoformat()

    def resolve_live_provider(market: str | None) -> tuple[str, str]:
        market = market or "Other"
        override = config.market_overrides.get(market) or {}
        provider = str(override.get("live_provider") or config.live_provider).strip().lower()
        api_key = (
            override.get("live_api_key")
            or config.live_api_key
            or config.twelve_data_api_key
            or config.alpha_vantage_api_key
        )
        return provider, api_key

    def resolve_poll_seconds(market: str | None) -> int:
        market = market or "Other"
        override = config.market_overrides.get(market) or {}
        return int(override.get("live_poll_seconds") or config.live_poll_seconds)

    def market_is_open(market: str | None) -> bool:
        # Lightweight market schedule gates to reduce unnecessary provider calls.
        now = datetime.now(timezone.utc)
        if now.weekday() >= 5:
            return False
        minutes = now.hour * 60 + now.minute
        market_norm = (market or "Other").strip().lower()
        if market_norm == "us":
            return 14 * 60 + 30 <= minutes <= 21 * 60
        if market_norm == "india":
            return 3 * 60 + 45 <= minutes <= 10 * 60
        return True

    def fetch_quote(symbol: str, market: str | None) -> tuple[float, str, str]:
        provider, api_key = resolve_live_provider(market)
        preferred_provider = provider
        providers = [provider, "twelve_data", "alpha_vantage", "yahoo"]
        seen = set()
        for candidate in providers:
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                if candidate == "alpha_vantage":
                    av_key = api_key if preferred_provider == "alpha_vantage" else (
                        config.alpha_vantage_api_key or config.live_api_key
                    )
                    if not av_key:
                        continue
                    quote = fetch_alpha_vantage_quote(symbol, av_key)
                    price = float(quote.get("05. price", 0) or 0)
                    timestamp = _normalize_timestamp(quote.get("07. latest trading day"))
                elif candidate == "yahoo":
                    quote = fetch_yahoo_quote(symbol)
                    price = float(quote.get("regularMarketPrice", 0) or 0)
                    timestamp = _normalize_timestamp(quote.get("regularMarketTime"))
                else:
                    td_key = api_key if preferred_provider == "twelve_data" else (
                        config.twelve_data_api_key or config.live_api_key
                    )
                    if not td_key:
                        continue
                    quote = fetch_twelve_data_quote(symbol, td_key)
                    price = _extract_twelve_data_price(quote)
                    timestamp = _normalize_timestamp(quote.get("datetime"))
                if price > 0:
                    increment_counter(f"live_provider_success_{candidate}", 1.0)
                    record_metric("live_provider_success", 1.0, tags=f"provider:{candidate}|symbol:{symbol}")
                    if candidate != preferred_provider:
                        increment_counter("live_provider_failover", 1.0)
                        record_metric(
                            "live_provider_failover",
                            1.0,
                            tags=f"preferred:{preferred_provider}|selected:{candidate}|symbol:{symbol}",
                        )
                        log_event(
                            "live_provider_failover",
                            symbol=symbol,
                            market=market or "Other",
                            preferred=preferred_provider,
                            selected=candidate,
                        )
                    return price, timestamp, candidate
            except Exception:
                increment_counter(f"live_provider_error_{candidate}", 1.0)
                record_metric("live_provider_error", 1.0, tags=f"provider:{candidate}|symbol:{symbol}")
                continue
        increment_counter("live_provider_quote_miss", 1.0)
        record_metric("live_provider_quote_miss", 1.0, tags=f"provider:{preferred_provider}|symbol:{symbol}")
        return 0.0, _normalize_timestamp(None), provider or "unknown"

    last_poll_by_market: dict[str, float] = {}

    while True:
        stocks = list_all_stocks(db_path)
        now = time.time()
        markets_due = set()
        intervals = {}
        for stock in stocks:
            market = stock.market or "Other"
            interval = resolve_poll_seconds(market)
            intervals[market] = interval
            if now - last_poll_by_market.get(market, 0) >= interval:
                markets_due.add(market)
        if not markets_due:
            time.sleep(1)
            continue

        seen = set()
        for stock in stocks:
            if stock.symbol in seen:
                continue
            seen.add(stock.symbol)
            market = stock.market or "Other"
            if market not in markets_due:
                continue
            try:
                is_open = market_is_open(market)
                price, timestamp, source = fetch_quote(stock.symbol, market)
                payload = {
                    "symbol": stock.symbol,
                    "price": price,
                    "timestamp": timestamp,
                    "market": stock.market,
                    "source": source,
                    "market_open": is_open,
                }
                producer.send(config.kafka_topic, payload)
            except KafkaError:
                producer = connect_producer()
                log_event("kafka_reconnect", component="live_producer")
                continue
            except Exception:
                continue
        try:
            producer.flush()
        except KafkaError:
            producer = connect_producer()
        for market in markets_due:
            last_poll_by_market[market] = now
        time.sleep(1)


if __name__ == "__main__":
    main()
