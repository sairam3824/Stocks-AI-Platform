from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config
from .notify import send_ntfy
from .pipeline import run_forecast
from .recommendations import Recommendation
from .skills import load_skill_profile


def _format_top_line(rec: Recommendation) -> str:
    return f"{rec.symbol}: {rec.signal} ({rec.expected_return_pct:.2f}%)"


def run(config_path: Path) -> None:
    config = load_config(config_path)
    if not config.tickers:
        raise ValueError("No tickers configured in config/portfolio.json")
    profiles = [
        load_skill_profile(ticker, config.skills_dir, config.recommendation_defaults)
        for ticker in config.tickers
    ]

    report_dir, recommendations = run_forecast(
        portfolio_name=config.portfolio_name,
        profiles=profiles,
        history_years=config.history_years,
        horizon_days=config.horizon_days,
        data_source=config.data_source,
        alpha_vantage_api_key=config.alpha_vantage_api_key,
        output_dir=config.output_dir,
        top_n=config.top_n,
        sentiment_enabled=config.sentiment_enabled,
        news_rss_template=config.news_rss_template,
        news_max_items=config.news_max_items,
        news_source=config.news_source,
        serpapi_api_key=config.serpapi_api_key,
        x_api_bearer_token=config.x_api_bearer_token,
        sentiment_provider=config.sentiment_provider,
        ollama_url=config.ollama_url,
        ollama_model=config.ollama_model,
        sentiment_llm_weight=config.sentiment_llm_weight,
        sentiment_weight=config.sentiment_weight,
        market_overrides=config.market_overrides,
        report_timestamped=config.report_timestamped,
        intraday_enabled=config.intraday_enabled,
        intraday_interval_minutes=config.intraday_interval_minutes,
        intraday_horizon_bars=config.intraday_horizon_bars,
        intraday_history_days=config.intraday_history_days,
        intraday_data_source=config.intraday_data_source,
        intraday_model=config.intraday_model,
        twelve_data_api_key=config.twelve_data_api_key,
        max_history_stale_days=config.max_history_stale_days,
        max_daily_gap_ratio=config.max_daily_gap_ratio,
        max_intraday_gap_ratio=config.max_intraday_gap_ratio,
    )

    sorted_recs = sorted(recommendations, key=lambda r: r.score, reverse=True)
    date_label = report_dir.name

    if config.ntfy_topic and recommendations:
        top_lines = "\n".join(_format_top_line(rec) for rec in sorted_recs[: config.top_n])
        message = f"{config.portfolio_name} forecast for {date_label}\n{top_lines}"
        click_url = ""
        if config.reports_base_url:
            click_url = f"{config.reports_base_url.rstrip('/')}/{date_label}/index.html"
        send_ntfy(
            config.ntfy_server,
            config.ntfy_topic,
            title=f"{config.portfolio_name} Forecast",
            message=message,
            click_url=click_url or None,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run portfolio forecast pipeline")
    parser.add_argument(
        "--config",
        default="config/portfolio.json",
        help="Path to portfolio config JSON",
    )
    args = parser.parse_args()
    run(Path(args.config))


if __name__ == "__main__":
    main()
