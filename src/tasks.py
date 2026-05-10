from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta

from .config import load_config, resolve_database_path
from .db import (
    add_report,
    create_trade_intent,
    get_model_profile,
    increment_metric,
    list_stocks,
    record_model_metric,
    upsert_model_profile,
    update_run,
    update_run_progress,
)
from .observability import increment_counter, log_event
from .pipeline import run_forecast
from .skills import SkillProfile
from .trading import build_trade_candidates


def run_forecast_job(
    run_id: int,
    user_id: int,
    workspace_id: int,
    config_path: str = "config/portfolio.json",
    intraday_model_override: str | None = None,
) -> None:
    config = load_config(Path(config_path))
    db_path = resolve_database_path(config)
    stocks = list_stocks(db_path, user_id, workspace_id)
    if not stocks:
        update_run(db_path, run_id, "FAILED", message="No stocks configured.")
        return

    profiles = [
        SkillProfile(
            symbol=stock.symbol,
            stooq_symbol=stock.stooq_symbol,
            min_return_pct=stock.min_return_pct,
            max_drop_pct=stock.max_drop_pct,
            market=stock.market,
            notes=stock.notes,
        )
        for stock in stocks
    ]

    user_reports_dir = config.output_dir / f"user_{user_id}" / f"workspace_{workspace_id}"
    retrain_cutoff = datetime.utcnow() - timedelta(days=max(1, config.model_retrain_interval_days))

    def progress_cb(progress: int, message: str) -> None:
        update_run_progress(
            db_path,
            run_id,
            status="RUNNING",
            message=message,
            progress=progress,
        )

    def model_metric_cb(symbol: str, horizon: str, model_name: str, mape: float, rmse: float, selected: int) -> None:
        record_model_metric(
            db_path,
            user_id=user_id,
            workspace_id=workspace_id,
            symbol=symbol,
            horizon=horizon,
            model_name=model_name,
            mape=mape,
            rmse=rmse,
            selected=selected,
        )

    def model_pref_lookup_cb(symbol: str, horizon: str) -> str | None:
        profile = get_model_profile(
            db_path,
            user_id=user_id,
            workspace_id=workspace_id,
            symbol=symbol,
            horizon=horizon,
        )
        if profile is None:
            return None
        trained_raw = profile.last_trained_at.strip()
        if trained_raw:
            parsed = None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(trained_raw[:19], fmt)
                    break
                except ValueError:
                    continue
            if parsed is not None and parsed < retrain_cutoff:
                return None
        return profile.preferred_model

    def model_pref_save_cb(symbol: str, horizon: str, selected_pref: str, mape: float, rmse: float) -> None:
        upsert_model_profile(
            db_path,
            user_id=user_id,
            workspace_id=workspace_id,
            symbol=symbol,
            horizon=horizon,
            preferred_model=selected_pref,
            last_mape=mape,
            last_rmse=rmse,
        )

    def quality_event_cb(symbol: str, scope: str, payload: dict) -> None:
        is_empty = bool(payload.get("empty"))
        if is_empty:
            increment_metric(db_path, f"data_quality_{scope}_empty", 1.0, tags=f"user:{user_id}|symbol:{symbol}")
            increment_counter(f"data_quality_{scope}_empty", 1.0)
            return
        if payload.get("is_stale"):
            increment_metric(db_path, f"data_quality_{scope}_stale", 1.0, tags=f"user:{user_id}|symbol:{symbol}")
            increment_counter(f"data_quality_{scope}_stale", 1.0)
        gap_ratio = float(payload.get("gap_ratio", 0.0) or 0.0)
        if gap_ratio > 0:
            increment_metric(
                db_path,
                f"data_quality_{scope}_gap_ratio",
                gap_ratio,
                tags=f"user:{user_id}|symbol:{symbol}",
            )
        log_event("data_quality_event", user_id=user_id, workspace_id=workspace_id, symbol=symbol, scope=scope, **payload)

    try:
        report_dir, recommendations = run_forecast(
            portfolio_name=config.portfolio_name,
            profiles=profiles,
            history_years=config.history_years,
            horizon_days=config.horizon_days,
            data_source=config.data_source,
            alpha_vantage_api_key=config.alpha_vantage_api_key,
            output_dir=user_reports_dir,
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
            intraday_model=intraday_model_override or config.intraday_model,
            twelve_data_api_key=config.twelve_data_api_key,
            progress_cb=progress_cb,
            model_metric_cb=model_metric_cb,
            model_pref_lookup_cb=model_pref_lookup_cb,
            model_pref_save_cb=model_pref_save_cb,
            quality_event_cb=quality_event_cb,
            max_history_stale_days=config.max_history_stale_days,
            max_daily_gap_ratio=config.max_daily_gap_ratio,
            max_intraday_gap_ratio=config.max_intraday_gap_ratio,
        )

        add_report(db_path, user_id, report_dir.name, report_dir.name, workspace_id=workspace_id)

        trade_count = 0
        if config.paper_trading_enabled:
            candidates = build_trade_candidates(
                recommendations,
                top_n=config.top_n,
                min_confidence_pct=config.paper_trade_min_confidence,
            )
            for trade in candidates:
                create_trade_intent(
                    db_path,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    run_id=run_id,
                    symbol=trade.symbol,
                    side=trade.side,
                    reference_price=trade.reference_price,
                    expected_return_pct=trade.expected_return_pct,
                    confidence_pct=trade.confidence_pct,
                    reasoning=trade.reasoning,
                    quantity=1.0,
                    mode="PAPER",
                )
                trade_count += 1

        update_run(
            db_path,
            run_id,
            "DONE",
            report_date=report_dir.name,
            message=f"Report ready. {trade_count} paper trade recommendations pending approval.",
        )
        increment_metric(db_path, "forecast_runs_done", 1.0, tags=f"user:{user_id}")
        increment_counter("forecast_runs_done", 1.0)
        log_event("forecast_run_done", user_id=user_id, workspace_id=workspace_id, run_id=run_id, trades=trade_count)
    except Exception as exc:
        update_run(db_path, run_id, "FAILED", message=str(exc))
        increment_metric(db_path, "forecast_runs_failed", 1.0, tags=f"user:{user_id}")
        increment_counter("forecast_runs_failed", 1.0)
        log_event("forecast_run_failed", user_id=user_id, workspace_id=workspace_id, run_id=run_id, error=str(exc))
        raise
