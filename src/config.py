from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class RecommendationDefaults:
    min_return_pct: float = 2.0
    max_drop_pct: float = 2.0


@dataclass
class PortfolioConfig:
    portfolio_name: str
    tickers: List[str]
    history_years: int = 5
    horizon_days: int = 21
    data_source: str = "stooq"
    alpha_vantage_api_key: str = ""
    output_dir: Path = Path("reports")
    reports_base_url: str = ""
    ntfy_server: str = "https://ntfy.sh"
    ntfy_topic: str = ""
    skills_dir: Path = Path("skills")
    recommendation_defaults: RecommendationDefaults = field(default_factory=RecommendationDefaults)
    top_n: int = 3
    publish_dir: Path = Path("docs")
    sentiment_enabled: bool = True
    news_rss_template: str = "https://news.google.com/rss/search?q={symbol}+stock&hl=en-US&gl=US&ceid=US:en"
    news_max_items: int = 8
    news_source: str = "rss"
    serpapi_api_key: str = ""
    x_api_bearer_token: str = ""
    sentiment_provider: str = "auto"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    sentiment_llm_weight: float = 0.7
    sentiment_weight: float = 0.25
    live_refresh_seconds: int = 60
    symbol_lookup_enabled: bool = True
    symbol_lookup_source: str = "yahoo"
    market_overrides: dict = field(default_factory=dict)
    report_timestamped: bool = True
    intraday_enabled: bool = True
    intraday_interval_minutes: int = 5
    intraday_horizon_bars: int = 24
    intraday_history_days: int = 7
    intraday_data_source: str = "twelve_data"
    intraday_model: str = "auto"
    intraday_models_enabled: List[str] = field(default_factory=lambda: ["auto", "stat", "lstm", "tft"])
    feature_intraday_model_selector: bool = True
    twelve_data_api_key: str = ""
    kafka_enabled: bool = True
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic: str = "stocks.live"
    live_poll_seconds: int = 10
    live_stream_seconds: int = 2
    live_provider: str = "twelve_data"
    live_api_key: str = ""
    live_stale_seconds: int = 180
    paper_trading_enabled: bool = True
    paper_trade_min_confidence: float = 60.0
    job_max_retries: int = 3
    rate_limit_login_per_minute: int = 10
    rate_limit_register_per_minute: int = 5
    rate_limit_mutation_per_minute: int = 30
    websocket_enabled: bool = True
    model_retrain_interval_days: int = 7
    max_history_stale_days: int = 14
    max_daily_gap_ratio: float = 0.35
    max_intraday_gap_ratio: float = 0.5
    broker_mode: str = "paper"
    allow_live_execution: bool = False
    live_broker_name: str = "webull"
    queue_fallback_inline: bool = True
    redis_url: str = "redis://localhost:6379/0"
    rq_queue_name: str = "forecast_jobs"
    rq_job_timeout_seconds: int = 3600
    database_url: str = "sqlite:///data/stocks.db"


def _coerce_path(base_dir: Path, value: Optional[str], default: Path) -> Path:
    if not value:
        return (base_dir / default).resolve()
    path = Path(value)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _load_recommendation_defaults(raw: Dict[str, Any]) -> RecommendationDefaults:
    return RecommendationDefaults(
        min_return_pct=float(raw.get("min_return_pct", 2.0)),
        max_drop_pct=float(raw.get("max_drop_pct", 2.0)),
    )


def resolve_database_path(config: PortfolioConfig) -> Path:
    database_url = str(config.database_url or "").strip()
    if database_url.startswith("sqlite:///"):
        return Path(database_url.replace("sqlite:///", "", 1)).expanduser()
    return Path("data") / "stocks.db"


def _deep_merge_dict(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def update_config_payload(config_path: str | Path, updates: Dict[str, Any]) -> Dict[str, Any]:
    path = Path(config_path).expanduser().resolve()
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    merged = _deep_merge_dict(payload, updates)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(merged, handle, indent=2)
        handle.write("\n")
    tmp_path.replace(path)
    return merged


def load_config(config_path: str | Path) -> PortfolioConfig:
    path = Path(config_path).expanduser().resolve()
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    base_dir = path.parent

    tickers = payload.get("tickers", [])
    if not isinstance(tickers, list):
        raise ValueError("tickers must be a list")

    portfolio_name = payload.get("portfolio_name", "Portfolio")

    history_years = int(payload.get("history_years", 5))
    horizon_days = int(payload.get("horizon_days", 21))
    if history_years <= 0 or horizon_days <= 0:
        raise ValueError("history_years and horizon_days must be positive")

    data_source = payload.get("data_source", "stooq")

    recommendation_defaults = _load_recommendation_defaults(
        payload.get("recommendation_defaults", {})
    )

    config = PortfolioConfig(
        portfolio_name=str(portfolio_name),
        tickers=[str(ticker).upper() for ticker in tickers],
        history_years=history_years,
        horizon_days=horizon_days,
        data_source=str(data_source),
        alpha_vantage_api_key=str(os.environ.get("ALPHA_VANTAGE_API_KEY", payload.get("alpha_vantage_api_key", ""))),
        output_dir=_coerce_path(base_dir, payload.get("output_dir"), Path("reports")),
        reports_base_url=str(payload.get("reports_base_url", "")),
        ntfy_server=str(payload.get("ntfy_server", "https://ntfy.sh")),
        ntfy_topic=str(payload.get("ntfy_topic", "")),
        skills_dir=_coerce_path(base_dir, payload.get("skills_dir"), Path("skills")),
        recommendation_defaults=recommendation_defaults,
        top_n=int(payload.get("top_n", 3)),
        publish_dir=_coerce_path(base_dir, payload.get("publish_dir"), Path("docs")),
        sentiment_enabled=bool(payload.get("sentiment_enabled", True)),
        news_rss_template=str(
            payload.get(
                "news_rss_template",
                "https://news.google.com/rss/search?q={symbol}+stock&hl=en-US&gl=US&ceid=US:en",
            )
        ),
        news_max_items=int(payload.get("news_max_items", 8)),
        news_source=str(payload.get("news_source", "rss")),
        serpapi_api_key=str(os.environ.get("SERPAPI_API_KEY", payload.get("serpapi_api_key", ""))),
        x_api_bearer_token=str(os.environ.get("X_API_BEARER_TOKEN", payload.get("x_api_bearer_token", ""))),
        sentiment_provider=str(
            os.environ.get("SENTIMENT_PROVIDER", payload.get("sentiment_provider", "auto"))
        ).strip().lower(),
        ollama_url=str(os.environ.get("OLLAMA_URL", payload.get("ollama_url", "http://localhost:11434"))),
        ollama_model=str(os.environ.get("OLLAMA_MODEL", payload.get("ollama_model", "llama3.1"))),
        sentiment_llm_weight=float(payload.get("sentiment_llm_weight", 0.7)),
        sentiment_weight=float(payload.get("sentiment_weight", 0.25)),
        live_refresh_seconds=int(payload.get("live_refresh_seconds", 60)),
        symbol_lookup_enabled=bool(payload.get("symbol_lookup_enabled", True)),
        symbol_lookup_source=str(payload.get("symbol_lookup_source", "yahoo")),
        market_overrides=dict(payload.get("market_overrides", {})),
        report_timestamped=bool(payload.get("report_timestamped", True)),
        intraday_enabled=bool(payload.get("intraday_enabled", True)),
        intraday_interval_minutes=int(payload.get("intraday_interval_minutes", 5)),
        intraday_horizon_bars=int(payload.get("intraday_horizon_bars", 24)),
        intraday_history_days=int(payload.get("intraday_history_days", 7)),
        intraday_data_source=str(payload.get("intraday_data_source", "twelve_data")),
        intraday_model=str(payload.get("intraday_model", "auto")),
        intraday_models_enabled=[
            str(item).strip().lower()
            for item in payload.get("intraday_models_enabled", ["auto", "stat", "lstm", "tft"])
            if str(item).strip()
        ],
        feature_intraday_model_selector=bool(payload.get("feature_intraday_model_selector", True)),
        twelve_data_api_key=str(os.environ.get("TWELVE_DATA_API_KEY", payload.get("twelve_data_api_key", ""))),
        kafka_enabled=bool(payload.get("kafka_enabled", True)),
        kafka_bootstrap_servers=str(os.environ.get("KAFKA_BOOTSTRAP_SERVERS", payload.get("kafka_bootstrap_servers", "localhost:9092"))),
        kafka_topic=str(os.environ.get("KAFKA_TOPIC", payload.get("kafka_topic", "stocks.live"))),
        live_poll_seconds=int(payload.get("live_poll_seconds", 10)),
        live_stream_seconds=int(payload.get("live_stream_seconds", 2)),
        live_provider=str(os.environ.get("LIVE_PROVIDER", payload.get("live_provider", "twelve_data"))),
        live_api_key=str(os.environ.get("LIVE_API_KEY", payload.get("live_api_key", ""))),
        live_stale_seconds=int(payload.get("live_stale_seconds", 180)),
        paper_trading_enabled=bool(payload.get("paper_trading_enabled", True)),
        paper_trade_min_confidence=float(payload.get("paper_trade_min_confidence", 60.0)),
        job_max_retries=int(payload.get("job_max_retries", 3)),
        rate_limit_login_per_minute=int(payload.get("rate_limit_login_per_minute", 10)),
        rate_limit_register_per_minute=int(payload.get("rate_limit_register_per_minute", 5)),
        rate_limit_mutation_per_minute=int(payload.get("rate_limit_mutation_per_minute", 30)),
        websocket_enabled=bool(payload.get("websocket_enabled", True)),
        model_retrain_interval_days=int(payload.get("model_retrain_interval_days", 7)),
        max_history_stale_days=int(payload.get("max_history_stale_days", 14)),
        max_daily_gap_ratio=float(payload.get("max_daily_gap_ratio", 0.35)),
        max_intraday_gap_ratio=float(payload.get("max_intraday_gap_ratio", 0.5)),
        broker_mode=str(os.environ.get("BROKER_MODE", payload.get("broker_mode", "paper"))).strip().lower(),
        allow_live_execution=bool(payload.get("allow_live_execution", False)),
        live_broker_name=str(payload.get("live_broker_name", "webull")).strip().lower(),
        queue_fallback_inline=bool(payload.get("queue_fallback_inline", True)),
        redis_url=str(os.environ.get("REDIS_URL", payload.get("redis_url", "redis://localhost:6379/0"))),
        rq_queue_name=str(os.environ.get("RQ_QUEUE_NAME", payload.get("rq_queue_name", "forecast_jobs"))),
        rq_job_timeout_seconds=int(
            os.environ.get(
                "RQ_JOB_TIMEOUT_SECONDS",
                payload.get("rq_job_timeout_seconds", 3600),
            )
        ),
        database_url=str(os.environ.get("DATABASE_URL", payload.get("database_url", "sqlite:///data/stocks.db"))),
    )

    if not config.intraday_models_enabled:
        config.intraday_models_enabled = ["auto", "stat", "lstm", "tft"]

    return config
