from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Callable, Iterable, List, Tuple

import pandas as pd

from .charts import build_forecast_chart, save_chart
from .backtest import evaluate_models
from .data_sources import (
    PriceHistoryRequest,
    get_price_history,
    fetch_twelve_data_intraday,
    fetch_alpha_vantage_intraday,
)
from .forecast import forecast_close
from .recommendations import Recommendation, compute_recommendation
from .news import fetch_news
from .report import build_index_html, write_summary
from .sentiment import analyze_sentiment
from .skills import SkillProfile


def _assess_daily_quality(history_df, freq: str = "B") -> dict:
    if history_df.empty:
        return {"empty": True, "is_stale": True, "days_stale": 9999, "gap_ratio": 1.0, "gap_count": 0}
    ordered = history_df.sort_values("date")
    first_date = ordered["date"].iloc[0]
    last_date = ordered["date"].iloc[-1]
    gap_ratio = 0.0
    gap_count = 0
    try:
        expected_idx = set(dt_ for dt_ in ordered["date"].dt.normalize())
        all_idx = set(dt_ for dt_ in pd.date_range(first_date, last_date, freq=freq).normalize())
        gap_count = max(0, len(all_idx - expected_idx))
        gap_ratio = gap_count / max(1, len(all_idx))
    except Exception:
        gap_count = 0
        gap_ratio = 0.0
    try:
        days_stale = max(0, (dt.date.today() - last_date.date()).days)
    except Exception:
        days_stale = 9999
    return {
        "empty": False,
        "is_stale": days_stale > 7,
        "days_stale": days_stale,
        "gap_ratio": float(gap_ratio),
        "gap_count": int(gap_count),
        "first_date": str(first_date),
        "last_date": str(last_date),
        "window_days": int(max(1, (last_date - first_date).days)) if first_date is not None else 0,
    }


def _assess_intraday_quality(intraday_df, interval_minutes: int) -> dict:
    if intraday_df is None or intraday_df.empty:
        return {"empty": True, "is_stale": True, "minutes_stale": 999999, "gap_ratio": 1.0, "large_gap_count": 0}
    ordered = intraday_df.sort_values("date")
    last_date = ordered["date"].iloc[-1]
    minutes_stale = 999999
    try:
        minutes_stale = int((dt.datetime.now() - last_date.to_pydatetime()).total_seconds() / 60.0)
    except Exception:
        pass
    try:
        deltas = ordered["date"].diff().dropna().dt.total_seconds() / 60.0
        threshold = max(1, interval_minutes) * 3
        large_gap_count = int((deltas > threshold).sum())
        gap_ratio = large_gap_count / max(1, len(deltas))
    except Exception:
        large_gap_count = 0
        gap_ratio = 0.0
    return {
        "empty": False,
        "is_stale": minutes_stale > max(120, interval_minutes * 6),
        "minutes_stale": minutes_stale,
        "gap_ratio": float(gap_ratio),
        "large_gap_count": int(large_gap_count),
        "last_date": str(last_date),
    }


def run_forecast(
    portfolio_name: str,
    profiles: Iterable[SkillProfile],
    history_years: int,
    horizon_days: int,
    data_source: str,
    alpha_vantage_api_key: str,
    output_dir: Path,
    top_n: int,
    sentiment_enabled: bool = True,
    news_rss_template: str = "https://news.google.com/rss/search?q={symbol}+stock&hl=en-US&gl=US&ceid=US:en",
    news_max_items: int = 8,
    news_source: str = "rss",
    serpapi_api_key: str = "",
    x_api_bearer_token: str = "",
    sentiment_provider: str = "auto",
    ollama_url: str = "http://localhost:11434",
    ollama_model: str = "llama3.1",
    sentiment_llm_weight: float = 0.7,
    sentiment_weight: float = 0.25,
    market_overrides: dict | None = None,
    report_timestamped: bool = True,
    intraday_enabled: bool = True,
    intraday_interval_minutes: int = 5,
    intraday_horizon_bars: int = 24,
    intraday_history_days: int = 7,
    intraday_data_source: str = "twelve_data",
    intraday_model: str = "auto",
    twelve_data_api_key: str = "",
    progress_cb: Callable[[int, str], None] | None = None,
    model_metric_cb: Callable[[str, str, str, float, float, int], None] | None = None,
    model_pref_lookup_cb: Callable[[str, str], str | None] | None = None,
    model_pref_save_cb: Callable[[str, str, str, float, float], None] | None = None,
    quality_event_cb: Callable[[str, str, dict], None] | None = None,
    max_history_stale_days: int = 14,
    max_daily_gap_ratio: float = 0.35,
    max_intraday_gap_ratio: float = 0.5,
) -> Tuple[Path, List[Recommendation]]:
    profiles = list(profiles)
    if report_timestamped:
        date_label = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    else:
        date_label = dt.date.today().isoformat()
    report_dir = output_dir / date_label
    report_dir.mkdir(parents=True, exist_ok=True)

    recommendations: List[Recommendation] = []
    intraday_recommendations: List[Recommendation] = []
    chart_links: dict[str, str] = {}
    intraday_chart_links: dict[str, str] = {}

    market_overrides = market_overrides or {}

    def resolve_data_source(market: str) -> str:
        key = market or "Other"
        override = market_overrides.get(key) or {}
        source = override.get("data_source")
        if source:
            return str(source).strip().lower()
        fallback = market_overrides.get("Other") or {}
        return str(fallback.get("data_source") or data_source).strip().lower()

    if progress_cb:
        progress_cb(2, "Preparing forecast")

    total_profiles = max(1, len(profiles))

    for idx, profile in enumerate(profiles, start=1):
        if progress_cb:
            progress_cb(
                5 + int((idx - 1) / total_profiles * 70),
                f"Fetching data for {profile.symbol}",
            )
        resolved_source = resolve_data_source(profile.market)
        if resolved_source == "alpha_vantage" and not alpha_vantage_api_key:
            print(f"[WARN] Missing Alpha Vantage key. Falling back to stooq for {profile.symbol}.")
            resolved_source = "stooq"

        request = PriceHistoryRequest(
            symbol=profile.symbol,
            years=history_years,
            source=resolved_source,
            alpha_vantage_api_key=alpha_vantage_api_key,
            symbol_override=profile.stooq_symbol,
        )
        history = get_price_history(request)
        if history.empty:
            print(f"[WARN] No data for {profile.symbol}. Skipping.")
            if quality_event_cb:
                quality_event_cb(profile.symbol, "daily", {"empty": True})
            continue

        daily_quality = _assess_daily_quality(history, freq="B")
        if quality_event_cb:
            quality_event_cb(profile.symbol, "daily", daily_quality)
        if daily_quality.get("days_stale", 0) > max_history_stale_days:
            print(
                f"[WARN] Daily history for {profile.symbol} is stale ({daily_quality.get('days_stale')} days). Skipping."
            )
            continue
        if daily_quality.get("gap_ratio", 0.0) > max_daily_gap_ratio:
            print(
                f"[WARN] Daily history for {profile.symbol} has high gaps ({daily_quality.get('gap_ratio'):.2f}). Skipping."
            )
            continue

        if progress_cb:
            progress_cb(
                10 + int((idx - 1) / total_profiles * 70),
                f"Forecasting {profile.symbol}",
            )
        model_pref = None
        if model_pref_lookup_cb:
            model_pref = model_pref_lookup_cb(profile.symbol, "monthly")
        if not model_pref:
            backtest = evaluate_models(history, freq="B")
            model_pref = backtest.selected_model or "auto"
            if model_metric_cb:
                for idx_score, score in enumerate(backtest.scores):
                    model_metric_cb(
                        profile.symbol,
                        "monthly",
                        score.model_name,
                        score.mape,
                        score.rmse,
                        1 if idx_score == 0 else 0,
                    )
            if model_pref_save_cb and backtest.scores:
                leader = backtest.scores[0]
                model_pref_save_cb(profile.symbol, "monthly", model_pref, leader.mape, leader.rmse)

        forecast_result = forecast_close(history, horizon=horizon_days, freq="B", model_preference=model_pref)

        sentiment_score = None
        sentiment_label = None
        if sentiment_enabled:
            try:
                items = fetch_news(
                    profile.symbol,
                    news_rss_template,
                    max_items=news_max_items,
                    source=news_source,
                    serpapi_api_key=serpapi_api_key,
                    x_bearer_token=x_api_bearer_token,
                )
                sentiment = analyze_sentiment(
                    items,
                    provider=sentiment_provider,
                    ollama_model=ollama_model,
                    ollama_url=ollama_url,
                    llm_weight=sentiment_llm_weight,
                )
                if sentiment is not None:
                    sentiment_score = sentiment.score
                    sentiment_label = sentiment.label
            except Exception:
                sentiment_score = None

        recommendation = compute_recommendation(
            forecast_result.history,
            forecast_result.forecast,
            profile,
            sentiment_score=sentiment_score,
            sentiment_weight=sentiment_weight,
            sentiment_label=sentiment_label,
            model_name=forecast_result.model_name,
        )
        recommendations.append(recommendation)

        chart_title = f"{profile.symbol} Forecast ({forecast_result.model_name})"
        fig = build_forecast_chart(
            forecast_result.history,
            forecast_result.forecast,
            chart_title,
        )
        chart_path = report_dir / f"{profile.symbol}.html"
        save_chart(fig, chart_path, nav_url="index.html", report_label=date_label)
        chart_links[profile.symbol] = chart_path.name

        intraday_source = str(intraday_data_source).strip().lower()
        override = market_overrides.get(profile.market or "Other") or {}
        if override.get("intraday_data_source"):
            intraday_source = str(override.get("intraday_data_source")).strip().lower()

        if intraday_enabled:
            intraday_df = None
            if intraday_source == "twelve_data" and twelve_data_api_key:
                intraday_df = fetch_twelve_data_intraday(
                    profile.symbol,
                    twelve_data_api_key,
                    interval_minutes=intraday_interval_minutes,
                    outputsize=intraday_history_days * 100,
                )
            elif intraday_source == "alpha_vantage" and alpha_vantage_api_key:
                intraday_df = fetch_alpha_vantage_intraday(
                    profile.symbol,
                    alpha_vantage_api_key,
                    interval_minutes=intraday_interval_minutes,
                    outputsize="compact",
                )
            else:
                if intraday_source == "twelve_data" and alpha_vantage_api_key:
                    intraday_df = fetch_alpha_vantage_intraday(
                        profile.symbol,
                        alpha_vantage_api_key,
                        interval_minutes=intraday_interval_minutes,
                        outputsize="compact",
                    )
                elif intraday_source == "alpha_vantage" and twelve_data_api_key:
                    intraday_df = fetch_twelve_data_intraday(
                        profile.symbol,
                        twelve_data_api_key,
                        interval_minutes=intraday_interval_minutes,
                        outputsize=intraday_history_days * 100,
                    )

            if intraday_df is None or intraday_df.empty:
                if intraday_source in ("twelve_data", "alpha_vantage"):
                    print(
                        f"[WARN] Missing API key or data for intraday source '{intraday_source}'. Skipping intraday for {profile.symbol}."
                    )
                if quality_event_cb:
                    quality_event_cb(profile.symbol, "intraday", {"empty": True, "source": intraday_source})
            else:
                intraday_quality = _assess_intraday_quality(intraday_df, intraday_interval_minutes)
                if quality_event_cb:
                    intraday_quality["source"] = intraday_source
                    quality_event_cb(profile.symbol, "intraday", intraday_quality)
                if intraday_quality.get("gap_ratio", 0.0) > max_intraday_gap_ratio:
                    print(
                        f"[WARN] Intraday history for {profile.symbol} has high gaps ({intraday_quality.get('gap_ratio'):.2f}). Skipping intraday."
                    )
                    continue
                intraday_pref = intraday_model
                if intraday_model == "auto" and model_pref_lookup_cb:
                    cached = model_pref_lookup_cb(profile.symbol, "intraday")
                    if cached:
                        intraday_pref = cached
                if intraday_model == "auto" and intraday_pref == "auto":
                    intraday_backtest = evaluate_models(
                        intraday_df,
                        freq=f"{intraday_interval_minutes}min",
                    )
                    intraday_pref = intraday_backtest.selected_model or "auto"
                    if model_metric_cb:
                        for idx_score, score in enumerate(intraday_backtest.scores):
                            model_metric_cb(
                                profile.symbol,
                                "intraday",
                                score.model_name,
                                score.mape,
                                score.rmse,
                                1 if idx_score == 0 else 0,
                            )
                    if model_pref_save_cb and intraday_backtest.scores:
                        leader = intraday_backtest.scores[0]
                        model_pref_save_cb(profile.symbol, "intraday", intraday_pref, leader.mape, leader.rmse)
                intraday_forecast = forecast_close(
                    intraday_df,
                    horizon=intraday_horizon_bars,
                    freq=f"{intraday_interval_minutes}min",
                    model_preference=intraday_pref,
                )
                intraday_rec = compute_recommendation(
                    intraday_forecast.history,
                    intraday_forecast.forecast,
                    profile,
                    sentiment_score=sentiment_score,
                    sentiment_weight=sentiment_weight,
                    sentiment_label=sentiment_label,
                    model_name=intraday_forecast.model_name,
                )
                intraday_recommendations.append(intraday_rec)

                intraday_title = f"{profile.symbol} Intraday ({intraday_forecast.model_name}, {intraday_interval_minutes}m)"
                intraday_fig = build_forecast_chart(
                    intraday_forecast.history,
                    intraday_forecast.forecast,
                    intraday_title,
                )
                intraday_path = report_dir / f"{profile.symbol}_intraday.html"
                save_chart(intraday_fig, intraday_path, nav_url="index.html", report_label=date_label)
                intraday_chart_links[profile.symbol] = intraday_path.name

    if progress_cb:
        progress_cb(85, "Writing report")
    summary_df = write_summary(recommendations, report_dir, chart_links)
    if intraday_recommendations:
        write_summary(intraday_recommendations, report_dir, intraday_chart_links, file_prefix="summary_intraday")

    sorted_recs = sorted(recommendations, key=lambda r: r.score, reverse=True)
    top_symbols = [rec.symbol for rec in sorted_recs[:top_n]]

    index_html = build_index_html(
        portfolio_name,
        date_label,
        summary_df,
        chart_links,
        top_symbols,
        intraday_summary_path=report_dir / "summary_intraday.json",
        intraday_links=intraday_chart_links,
    )
    (report_dir / "index.html").write_text(index_html, encoding="utf-8")

    if progress_cb:
        progress_cb(100, "Report ready")

    return report_dir, recommendations
