from __future__ import annotations

import json
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache, wraps
from pathlib import Path
from typing import Callable

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from flask_sock import Sock
except Exception:  # pragma: no cover - optional runtime dependency
    Sock = None

try:
    import pyotp
except Exception:  # pragma: no cover - optional runtime dependency
    pyotp = None

from .config import load_config, resolve_database_path, update_config_payload
from .db import (
    add_stock,
    approve_trade,
    count_stocks,
    create_run,
    create_user,
    disable_twofa,
    db_health,
    delete_stock,
    get_latest_run,
    get_trade_by_id,
    get_user_by_email,
    get_user_by_email_verification_token,
    get_user_by_id,
    get_user_by_reset_token,
    get_user_workspace_id,
    get_workspace_member_role,
    increment_metric,
    init_db,
    list_reports,
    list_runs,
    list_stocks,
    list_model_profiles,
    list_model_metrics,
    list_trades,
    list_workspaces,
    reject_trade,
    set_password_reset_token,
    set_twofa_secret,
    set_user_workspace,
    update_user_password,
    update_run,
    update_run_progress,
    verify_user_email,
)
from .live_kafka import LivePrice, start_consumer
from .observability import get_counters, increment_counter, log_event
from .execution import execute_trade_with_adapter
from .queueing import get_forecast_queue, queue_depth, redis_health
from .security import allow_request, get_client_ip, get_or_create_csrf, validate_csrf
from .symbol_lookup import resolve_symbol, search_symbols
from .tasks import run_forecast_job

LIVE_CACHE: dict[str, LivePrice] = {}
LIVE_LOCK = threading.Lock()
LIVE_CONSUMER_STARTED = False
LIVE_CONSUMER_THREAD: threading.Thread | None = None
ROLE_PRIORITY = {"none": 0, "member": 1, "admin": 2, "owner": 3}
CONFIG_PATH = Path(os.environ.get("STOCKS_CONFIG_PATH", "config/portfolio.json"))
ENGINE_NEWS_SOURCES = {"rss", "serpapi", "reddit", "x", "twitter", "social", "mixed", "all"}
ENGINE_SENTIMENT_PROVIDERS = {"auto", "ollama", "llm", "lexicon", "rule_based"}
ENGINE_NEWS_SOURCE_CHOICES = ["rss", "serpapi", "reddit", "x", "social", "mixed"]
ENGINE_SENTIMENT_PROVIDER_CHOICES = ["auto", "ollama", "lexicon"]


def _as_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _default_secret() -> str:
    return os.environ.get("STOCKS_SECRET_KEY", "dev-secret-change-me")


@lru_cache(maxsize=1)
def _load_runtime_config():
    return load_config(CONFIG_PATH)


def _db_path() -> Path:
    return resolve_database_path(_load_runtime_config())


def _login_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapper


def _workspace_role_required(required_role: str):
    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapper(*args, **kwargs):
            user_id = session.get("user_id")
            if not user_id:
                return redirect(url_for("login"))
            workspace_id = _current_workspace_id(user_id)
            actual_role = get_workspace_member_role(_db_path(), user_id, workspace_id)
            if ROLE_PRIORITY.get(actual_role, 0) < ROLE_PRIORITY.get(required_role, 0):
                flash(f"{required_role.title()} role is required for this action.")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)

        return wrapper

    return decorator


def _make_token() -> str:
    return secrets.token_urlsafe(32)


def _utc_plus_minutes(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).replace(microsecond=0).isoformat()


def _workspace_role(user_id: int, workspace_id: int) -> str:
    return get_workspace_member_role(_db_path(), user_id, workspace_id)


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"

MARKET_FLAGS = {
    "US": "🇺🇸",
    "India": "🇮🇳",
    "UK": "🇬🇧",
    "Canada": "🇨🇦",
    "Japan": "🇯🇵",
    "China": "🇨🇳",
    "Australia": "🇦🇺",
    "Europe": "🇪🇺",
    "Other": "🌐",
}


app = Flask(__name__, template_folder=str(TEMPLATES_DIR))
app.secret_key = _default_secret()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=24),
)

init_db(_db_path())

sock = Sock(app) if Sock is not None else None


def _current_workspace_id(user_id: int) -> int:
    return get_user_workspace_id(_db_path(), user_id)


def _resolve_report_root(config, user_id: int, workspace_id: int, report_date: str | None = None) -> Path:
    base = config.output_dir / f"user_{user_id}" / f"workspace_{workspace_id}"
    if report_date:
        candidate = base / report_date
        if candidate.exists():
            return candidate
        legacy = config.output_dir / f"user_{user_id}" / report_date
        return legacy
    return base


def _start_live_consumer() -> None:
    global LIVE_CONSUMER_STARTED, LIVE_CONSUMER_THREAD
    if LIVE_CONSUMER_STARTED and LIVE_CONSUMER_THREAD is not None and LIVE_CONSUMER_THREAD.is_alive():
        return
    config = _load_runtime_config()
    if not config.kafka_enabled:
        return
    LIVE_CONSUMER_THREAD = start_consumer(
        cache=LIVE_CACHE,
        lock=LIVE_LOCK,
        bootstrap_servers=config.kafka_bootstrap_servers,
        topic=config.kafka_topic,
    )
    LIVE_CONSUMER_STARTED = True
    log_event("live_consumer_started", bootstrap=config.kafka_bootstrap_servers, topic=config.kafka_topic)


_start_live_consumer()


def _live_cache_stats(stale_seconds: int) -> dict:
    with LIVE_LOCK:
        snapshot = list(LIVE_CACHE.values())
    total = len(snapshot)
    if total == 0:
        return {"live_symbols": 0, "live_stale_symbols": 0, "live_fresh_symbols": 0}
    now = datetime.now(timezone.utc)
    stale = 0
    for item in snapshot:
        ts_raw = (item.timestamp or "").strip()
        parsed = None
        if ts_raw:
            try:
                parsed = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except ValueError:
                parsed = None
        if parsed is None:
            stale += 1
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age_seconds = (now - parsed.astimezone(timezone.utc)).total_seconds()
        if age_seconds > stale_seconds:
            stale += 1
    return {
        "live_symbols": total,
        "live_stale_symbols": stale,
        "live_fresh_symbols": max(0, total - stale),
    }


def _rate_limit_response(scope: str, limit: int, period_seconds: int = 60):
    key = f"{scope}:{get_client_ip(request)}"
    if allow_request(key, limit=limit, window_seconds=period_seconds):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"error": "rate_limit_exceeded"}), 429
    flash("Too many requests. Please wait a minute and try again.")
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.before_request
def _security_hooks():
    session.permanent = True
    get_or_create_csrf(session)
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if request.endpoint and request.endpoint.startswith("static"):
            return None
        if not validate_csrf(request, session):
            log_event("csrf_rejected", path=request.path, ip=get_client_ip(request))
            if request.path.startswith("/api/"):
                return jsonify({"error": "invalid_csrf"}), 400
            abort(400, description="Invalid CSRF token")
    return None


@app.context_processor
def inject_globals():
    config = _load_runtime_config()
    workspace_id = 0
    workspace_role = "none"
    if "user_id" in session:
        workspace_id = _current_workspace_id(session["user_id"])
        workspace_role = _workspace_role(session["user_id"], workspace_id)
    return {
        "app_name": config.portfolio_name,
        "horizon_days": config.horizon_days,
        "live_refresh_seconds": config.live_refresh_seconds,
        "live_stale_seconds": config.live_stale_seconds,
        "market_flags": MARKET_FLAGS,
        "csrf_token": get_or_create_csrf(session),
        "websocket_supported": bool(sock and config.websocket_enabled),
        "current_workspace_id": workspace_id,
        "workspace_role": workspace_role,
    }


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    config = _load_runtime_config()
    if request.method == "POST":
        limited = _rate_limit_response("register", config.rate_limit_register_per_minute)
        if limited is not None:
            return limited

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not email or not password:
            flash("Email and password are required.")
            return redirect(url_for("register"))
        if get_user_by_email(_db_path(), email):
            flash("An account with that email already exists.")
            return redirect(url_for("register"))

        user = create_user(
            _db_path(),
            email,
            generate_password_hash(password),
            email_verified=1,
            email_verification_token="",
        )
        increment_metric(_db_path(), "register_success", 1.0)
        increment_counter("register_success", 1.0)
        log_event("register_success", user_id=user.id)
        flash("Account created. You can now login.")
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    config = _load_runtime_config()
    if request.method == "POST":
        limited = _rate_limit_response("login", config.rate_limit_login_per_minute)
        if limited is not None:
            return limited

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        otp = request.form.get("otp_code", "").strip()
        user = get_user_by_email(_db_path(), email)
        if not user or not check_password_hash(user.password_hash, password):
            increment_metric(_db_path(), "login_failed", 1.0)
            flash("Invalid email or password.")
            return redirect(url_for("login"))
        if int(user.twofa_enabled) == 1:
            if pyotp is None:
                flash("2FA requires pyotp package.")
                return redirect(url_for("login"))
            if not otp:
                flash("Enter OTP code for 2FA.")
                return redirect(url_for("login"))
            totp = pyotp.TOTP(user.twofa_secret or "")
            if not totp.verify(otp, valid_window=1):
                flash("Invalid OTP code.")
                return redirect(url_for("login"))
        session["user_id"] = user.id
        increment_metric(_db_path(), "login_success", 1.0)
        increment_counter("login_success", 1.0)
        log_event("login_success", user_id=user.id)
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/verify-email/<token>")
def verify_email(token: str):
    user = get_user_by_email_verification_token(_db_path(), token)
    if user is None:
        flash("Email verification is not required.")
        return redirect(url_for("login"))
    verify_user_email(_db_path(), user.id)
    flash("Email verification is no longer required.")
    return redirect(url_for("login"))


@app.route("/resend-verification", methods=["POST"])
def resend_verification():
    flash("Email verification is disabled.")
    return redirect(url_for("login"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    config = _load_runtime_config()
    if request.method == "POST":
        limited = _rate_limit_response("forgot_password", config.rate_limit_login_per_minute)
        if limited is not None:
            return limited
        email = request.form.get("email", "").strip().lower()
        user = get_user_by_email(_db_path(), email)
        if user:
            token = _make_token()
            set_password_reset_token(
                _db_path(),
                user.id,
                token=token,
                expires_at=_utc_plus_minutes(60),
            )
            reset_link = url_for("reset_password", token=token, _external=True)
            flash(f"Password reset link: {reset_link}")
        else:
            flash("If the account exists, a reset link has been generated.")
        return redirect(url_for("login"))
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    user = get_user_by_reset_token(_db_path(), token)
    if user is None:
        flash("Invalid or expired reset link.")
        return redirect(url_for("login"))
    if request.method == "POST":
        password = request.form.get("password", "").strip()
        if len(password) < 8:
            flash("Password must be at least 8 characters.")
            return redirect(url_for("reset_password", token=token))
        update_user_password(_db_path(), user.id, generate_password_hash(password))
        flash("Password updated. Login with new password.")
        return redirect(url_for("login"))
    return render_template("reset_password.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/security", methods=["GET", "POST"], endpoint="security_settings_legacy")
@app.route("/settings/security", methods=["GET", "POST"], endpoint="security_settings")
@_login_required
def security_settings():
    user = get_user_by_id(_db_path(), session["user_id"])
    pending_secret = session.get("pending_twofa_secret", "")

    if request.method == "POST":
        action = request.form.get("action", "").strip()
        if action == "generate":
            if pyotp is None:
                flash("pyotp package is required for 2FA.")
                return redirect(url_for("security_settings"))
            pending_secret = pyotp.random_base32()
            session["pending_twofa_secret"] = pending_secret
            flash("2FA secret generated. Enter OTP to confirm.")
            return redirect(url_for("security_settings"))
        if action == "enable":
            if pyotp is None:
                flash("pyotp package is required for 2FA.")
                return redirect(url_for("security_settings"))
            otp = request.form.get("otp_code", "").strip()
            pending_secret = session.get("pending_twofa_secret", "")
            if not pending_secret:
                flash("Generate a 2FA secret first.")
                return redirect(url_for("security_settings"))
            totp = pyotp.TOTP(pending_secret)
            if not totp.verify(otp, valid_window=1):
                flash("Invalid OTP code.")
                return redirect(url_for("security_settings"))
            set_twofa_secret(_db_path(), user.id, pending_secret, enabled=1)
            session.pop("pending_twofa_secret", None)
            flash("2FA enabled.")
            return redirect(url_for("security_settings"))
        if action == "disable":
            disable_twofa(_db_path(), user.id)
            session.pop("pending_twofa_secret", None)
            flash("2FA disabled.")
            return redirect(url_for("security_settings"))

    provisioning_uri = ""
    if pending_secret and pyotp is not None:
        provisioning_uri = pyotp.TOTP(pending_secret).provisioning_uri(
            name=user.email,
            issuer_name="Stocks AI",
        )
    return render_template(
        "security_settings.html",
        user=user,
        pending_twofa_secret=pending_secret,
        provisioning_uri=provisioning_uri,
    )


@app.route("/settings/engine", methods=["GET", "POST"])
@_login_required
def engine_settings():
    user_id = session["user_id"]
    workspace_id = _current_workspace_id(user_id)
    workspace_role = _workspace_role(user_id, workspace_id)
    can_edit = workspace_role in {"owner", "admin"}
    config = _load_runtime_config()

    env_overrides = {
        "serpapi_api_key": bool(os.environ.get("SERPAPI_API_KEY")),
        "x_api_bearer_token": bool(os.environ.get("X_API_BEARER_TOKEN")),
        "ollama_url": bool(os.environ.get("OLLAMA_URL")),
        "ollama_model": bool(os.environ.get("OLLAMA_MODEL")),
        "sentiment_provider": bool(os.environ.get("SENTIMENT_PROVIDER")),
    }

    if request.method == "POST":
        if not can_edit:
            flash("Admin or owner role is required for engine settings.")
            return redirect(url_for("engine_settings"))
        limited = _rate_limit_response("mutate", config.rate_limit_mutation_per_minute)
        if limited is not None:
            return limited

        news_source = (request.form.get("news_source", "rss") or "rss").strip().lower()
        if news_source not in ENGINE_NEWS_SOURCES:
            flash(f"Invalid news source: {news_source}")
            return redirect(url_for("engine_settings"))

        sentiment_provider = (request.form.get("sentiment_provider", "auto") or "auto").strip().lower()
        if sentiment_provider not in ENGINE_SENTIMENT_PROVIDERS:
            flash(f"Invalid sentiment provider: {sentiment_provider}")
            return redirect(url_for("engine_settings"))

        try:
            top_n = max(1, min(20, int(request.form.get("top_n", str(config.top_n)) or config.top_n)))
            news_max_items = max(
                1,
                min(25, int(request.form.get("news_max_items", str(config.news_max_items)) or config.news_max_items)),
            )
            min_return_pct = float(
                request.form.get(
                    "min_return_pct",
                    str(config.recommendation_defaults.min_return_pct),
                )
                or config.recommendation_defaults.min_return_pct
            )
            max_drop_pct = float(
                request.form.get(
                    "max_drop_pct",
                    str(config.recommendation_defaults.max_drop_pct),
                )
                or config.recommendation_defaults.max_drop_pct
            )
            sentiment_weight = float(
                request.form.get("sentiment_weight", str(config.sentiment_weight)) or config.sentiment_weight
            )
            sentiment_llm_weight = float(
                request.form.get("sentiment_llm_weight", str(config.sentiment_llm_weight))
                or config.sentiment_llm_weight
            )
        except ValueError:
            flash("Invalid numeric values in engine settings.")
            return redirect(url_for("engine_settings"))

        min_return_pct = max(0.1, min(100.0, min_return_pct))
        max_drop_pct = max(0.1, min(100.0, max_drop_pct))
        sentiment_weight = max(0.0, min(3.0, sentiment_weight))
        sentiment_llm_weight = max(0.0, min(1.0, sentiment_llm_weight))

        updates = {
            "top_n": top_n,
            "sentiment_enabled": _as_bool(request.form.get("sentiment_enabled")),
            "news_source": "x" if news_source == "twitter" else news_source,
            "news_max_items": news_max_items,
            "sentiment_provider": "ollama" if sentiment_provider == "llm" else sentiment_provider,
            "sentiment_weight": sentiment_weight,
            "sentiment_llm_weight": sentiment_llm_weight,
            "ollama_url": (request.form.get("ollama_url", "") or config.ollama_url).strip(),
            "ollama_model": (request.form.get("ollama_model", "") or config.ollama_model).strip(),
            "recommendation_defaults": {
                "min_return_pct": min_return_pct,
                "max_drop_pct": max_drop_pct,
            },
        }

        serpapi_api_key = (request.form.get("serpapi_api_key", "") or "").strip()
        x_api_bearer_token = (request.form.get("x_api_bearer_token", "") or "").strip()
        if _as_bool(request.form.get("clear_serpapi_api_key")):
            updates["serpapi_api_key"] = ""
        elif serpapi_api_key:
            updates["serpapi_api_key"] = serpapi_api_key
        if _as_bool(request.form.get("clear_x_api_bearer_token")):
            updates["x_api_bearer_token"] = ""
        elif x_api_bearer_token:
            updates["x_api_bearer_token"] = x_api_bearer_token

        try:
            update_config_payload(CONFIG_PATH, updates)
        except Exception as exc:
            flash(f"Unable to save engine settings: {exc}")
            return redirect(url_for("engine_settings"))
        _load_runtime_config.cache_clear()
        flash("Engine settings saved.")
        if any(env_overrides.values()):
            flash("Some values may still be overridden by environment variables.")
        return redirect(url_for("engine_settings"))

    return render_template(
        "engine_settings.html",
        config=config,
        workspace_role=workspace_role,
        can_edit=can_edit,
        news_sources=ENGINE_NEWS_SOURCE_CHOICES,
        sentiment_providers=ENGINE_SENTIMENT_PROVIDER_CHOICES,
        env_overrides=env_overrides,
    )


@app.route("/workspace/switch", methods=["POST"])
@_login_required
def switch_workspace():
    workspace_id = int(request.form.get("workspace_id", "0") or 0)
    if workspace_id <= 0:
        flash("Invalid workspace selection.")
        return redirect(url_for("dashboard"))
    try:
        set_user_workspace(_db_path(), session["user_id"], workspace_id)
        flash("Workspace switched.")
    except Exception:
        flash("Unable to switch workspace.")
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
@_login_required
def dashboard():
    config = _load_runtime_config()
    user = get_user_by_id(_db_path(), session["user_id"])
    workspace_id = _current_workspace_id(user.id)
    workspace_role = _workspace_role(user.id, workspace_id)
    stocks = list_stocks(_db_path(), user.id, workspace_id)
    market_filter = request.args.get("market", "").strip()
    if market_filter:
        stocks = [stock for stock in stocks if (stock.market or "").lower() == market_filter.lower()]
    reports = list_reports(_db_path(), user.id, workspace_id)
    runs = list_runs(_db_path(), user.id, workspace_id)[:5]
    markets = sorted({stock.market for stock in stocks if stock.market})
    usage = {
        "stocks_used": count_stocks(_db_path(), user.id, workspace_id),
        "stocks_limit": user.max_stocks,
        "plan": user.plan,
        "role": workspace_role,
    }
    workspaces = list_workspaces(_db_path(), user.id)

    grouped = {}
    for stock in stocks:
        market = stock.market or "Other"
        grouped.setdefault(market, []).append(stock)
    stocks_by_market = [(market, grouped[market]) for market in sorted(grouped)]

    return render_template(
        "dashboard.html",
        user=user,
        stocks=stocks,
        stocks_by_market=stocks_by_market,
        reports=reports,
        runs=runs,
        markets=markets,
        market_filter=market_filter,
        usage=usage,
        workspaces=workspaces,
        workspace_role=workspace_role,
        feature_intraday_model_selector=config.feature_intraday_model_selector,
        intraday_models_enabled=config.intraday_models_enabled,
        intraday_model_default=config.intraday_model,
    )


@app.route("/stocks/add", methods=["POST"])
@_login_required
@_workspace_role_required("admin")
def add_stock_route():
    config = _load_runtime_config()
    limited = _rate_limit_response("mutate", config.rate_limit_mutation_per_minute)
    if limited is not None:
        return limited

    user_id = session["user_id"]
    workspace_id = _current_workspace_id(user_id)
    user = get_user_by_id(_db_path(), user_id)
    if count_stocks(_db_path(), user_id, workspace_id) >= user.max_stocks:
        flash(f"Stock limit reached for your plan ({user.max_stocks}).")
        return redirect(url_for("dashboard"))

    symbol = request.form.get("symbol", "").strip().upper()
    company_name = request.form.get("company_name", "").strip()
    market = request.form.get("market", "").strip()
    stooq_symbol = request.form.get("stooq_symbol", "").strip() or None
    min_return_raw = request.form.get("min_return_pct", "").strip()
    max_drop_raw = request.form.get("max_drop_pct", "").strip()
    min_return_pct = float(min_return_raw) if min_return_raw else config.recommendation_defaults.min_return_pct
    max_drop_pct = float(max_drop_raw) if max_drop_raw else config.recommendation_defaults.max_drop_pct
    notes = request.form.get("notes", "").strip()

    if not symbol and not company_name:
        flash("Provide a symbol or company name.")
        return redirect(url_for("dashboard"))

    if not symbol and company_name and config.symbol_lookup_enabled:
        match = resolve_symbol(company_name, config.symbol_lookup_source)
        if match is None:
            flash("Could not resolve that company name. Try a ticker symbol instead.")
            return redirect(url_for("dashboard"))
        symbol = match.symbol.upper()
        if not company_name:
            company_name = match.name
        if not market:
            market = match.market
    elif symbol and not company_name and config.symbol_lookup_enabled:
        match = resolve_symbol(symbol, config.symbol_lookup_source)
        if match and match.symbol.upper() != symbol.upper():
            company_name = match.name
            symbol = match.symbol.upper()
            if not market:
                market = match.market

    if not market:
        market = "Other"

    add_stock(
        _db_path(),
        user_id,
        symbol,
        company_name,
        market,
        min_return_pct,
        max_drop_pct,
        stooq_symbol=stooq_symbol,
        notes=notes,
        workspace_id=workspace_id,
    )
    increment_metric(_db_path(), "stock_added", 1.0, tags=f"user:{user_id}")
    return redirect(url_for("dashboard"))


@app.route("/api/symbols")
@_login_required
def api_symbols():
    config = _load_runtime_config()
    limited = _rate_limit_response("api_symbols", 60)
    if limited is not None:
        return limited
    if not config.symbol_lookup_enabled:
        return {"results": []}
    query = request.args.get("query", "").strip()
    results = search_symbols(query, config.symbol_lookup_source, limit=6)
    return {
        "results": [
            {
                "symbol": match.symbol,
                "name": match.name,
                "exchange": match.exchange,
                "exchange_disp": match.exchange_disp,
                "market": match.market,
            }
            for match in results
        ]
    }


@app.route("/stocks/<int:stock_id>/delete", methods=["POST"])
@_login_required
@_workspace_role_required("admin")
def delete_stock_route(stock_id: int):
    config = _load_runtime_config()
    limited = _rate_limit_response("mutate", config.rate_limit_mutation_per_minute)
    if limited is not None:
        return limited
    user_id = session["user_id"]
    workspace_id = _current_workspace_id(user_id)
    delete_stock(_db_path(), user_id, stock_id, workspace_id=workspace_id)
    return redirect(url_for("dashboard"))


@app.route("/run", methods=["POST"])
@_login_required
@_workspace_role_required("admin")
def run_forecast_route():
    config = _load_runtime_config()
    limited = _rate_limit_response("mutate", config.rate_limit_mutation_per_minute)
    if limited is not None:
        return limited
    user_id = session["user_id"]
    workspace_id = _current_workspace_id(user_id)
    stocks = list_stocks(_db_path(), user_id, workspace_id)
    if not stocks:
        flash("Add at least one stock before running the forecast.")
        return redirect(url_for("dashboard"))

    latest = get_latest_run(_db_path(), user_id, workspace_id)
    if latest and latest.status in ("QUEUED", "RUNNING"):
        flash("A forecast run is already in progress for this workspace.")
        return redirect(url_for("live_view"))

    run = create_run(_db_path(), user_id, workspace_id)
    intraday_model_selected = (request.form.get("intraday_model", "") or "").strip().lower()
    if config.feature_intraday_model_selector and intraday_model_selected:
        if intraday_model_selected not in config.intraday_models_enabled:
            flash(f"Invalid intraday model: {intraday_model_selected}")
            return redirect(url_for("dashboard"))
    else:
        intraday_model_selected = config.intraday_model
    try:
        queue = get_forecast_queue(config)
        queue.enqueue(
            run_forecast_job,
            run.id,
            user_id,
            workspace_id,
            str(CONFIG_PATH),
            intraday_model_selected,
            job_timeout=config.rq_job_timeout_seconds,
            result_ttl=86400,
            failure_ttl=7 * 86400,
        )
    except Exception as exc:
        increment_metric(_db_path(), "forecast_enqueue_failed", 1.0, tags=f"user:{user_id}")
        log_event("forecast_enqueue_failed", user_id=user_id, workspace_id=workspace_id, run_id=run.id, error=str(exc))
        if config.queue_fallback_inline:
            update_run_progress(
                _db_path(),
                run.id,
                status="RUNNING",
                message="Queue unavailable. Running fallback worker.",
                progress=1,
            )

            def _fallback_worker() -> None:
                run_forecast_job(
                    run.id,
                    user_id,
                    workspace_id,
                    str(CONFIG_PATH),
                    intraday_model_selected,
                )

            threading.Thread(target=_fallback_worker, daemon=True).start()
            flash("Queue unavailable. Running fallback worker in web process.")
            return redirect(url_for("live_view"))
        update_run(_db_path(), run.id, "FAILED", message=f"Queue unavailable: {exc}")
        flash("Queue is unavailable. Start Redis and worker before running forecast.")
        return redirect(url_for("dashboard"))
    increment_metric(_db_path(), "forecast_runs_enqueued", 1.0, tags=f"user:{user_id}")
    increment_counter("forecast_runs_enqueued", 1.0)
    log_event("forecast_enqueued", user_id=user_id, workspace_id=workspace_id, run_id=run.id)
    flash("Forecast queued via Redis worker. Progress is shown in the footer bar.")
    return redirect(url_for("live_view"))


@app.route("/reports")
@_login_required
def report_list():
    user_id = session["user_id"]
    workspace_id = _current_workspace_id(user_id)
    reports = list_reports(_db_path(), user_id, workspace_id)
    runs = list_runs(_db_path(), user_id, workspace_id)
    return render_template("reports.html", reports=reports, runs=runs)


@app.route("/reports/<report_date>/index.html")
@_login_required
def report_index(report_date: str):
    user_id = session["user_id"]
    workspace_id = _current_workspace_id(user_id)
    config = _load_runtime_config()
    reports_root = _resolve_report_root(config, user_id, workspace_id, report_date)
    if not reports_root.exists():
        abort(404)
    return send_from_directory(reports_root, "index.html")


@app.route("/reports/<report_date>/<path:filename>")
@_login_required
def report_asset(report_date: str, filename: str):
    user_id = session["user_id"]
    workspace_id = _current_workspace_id(user_id)
    config = _load_runtime_config()
    reports_root = _resolve_report_root(config, user_id, workspace_id, report_date)
    if not reports_root.exists():
        abort(404)
    return send_from_directory(reports_root, filename)


@app.route("/api/runs/latest")
@_login_required
def api_latest_run():
    user_id = session["user_id"]
    workspace_id = _current_workspace_id(user_id)
    latest = get_latest_run(_db_path(), user_id, workspace_id)
    if latest is None:
        return {"run": None}
    return {
        "run": {
            "id": latest.id,
            "status": latest.status,
            "started_at": latest.started_at,
            "finished_at": latest.finished_at,
            "report_date": latest.report_date,
            "message": latest.message,
            "progress": latest.progress,
        }
    }


@app.route("/live")
@_login_required
def live_view():
    _start_live_consumer()
    user_id = session["user_id"]
    workspace_id = _current_workspace_id(user_id)
    config = _load_runtime_config()
    reports = list_reports(_db_path(), user_id, workspace_id)
    latest = reports[0] if reports else None
    stocks = list_stocks(_db_path(), user_id, workspace_id)
    charts = []
    markets_seen = set()
    summary_rows = []
    summary_map = {}

    if latest:
        report_dir = _resolve_report_root(config, user_id, workspace_id, latest.report_date)
        summary_path = report_dir / "summary.json"
        if summary_path.exists():
            try:
                summary_rows = json.loads(summary_path.read_text(encoding="utf-8"))
                summary_map = {row.get("symbol"): row for row in summary_rows}
            except json.JSONDecodeError:
                summary_map = {}

    for stock in stocks:
        summary = summary_map.get(stock.symbol, {})
        chart_link = summary.get("chart_link") or f"{stock.symbol}.html"
        charts.append(
            {
                "symbol": stock.symbol,
                "company_name": stock.company_name,
                "market": stock.market,
                "link": chart_link,
                "available": stock.symbol in summary_map,
            }
        )
        if stock.market:
            markets_seen.add(stock.market)

    chart_groups = {}
    for chart in charts:
        market = chart.get("market") or "Other"
        chart_groups.setdefault(market, []).append(chart)
    charts_by_market = [(market, chart_groups[market]) for market in sorted(chart_groups)]

    refresh_seconds = config.live_refresh_seconds
    if config.market_overrides and markets_seen:
        overrides = []
        for market in markets_seen:
            entry = config.market_overrides.get(market) or {}
            value = entry.get("live_refresh_seconds")
            if value:
                overrides.append(int(value))
        if overrides:
            refresh_seconds = min(overrides)

    return render_template(
        "live.html",
        latest_report=latest,
        charts=charts,
        charts_by_market=charts_by_market,
        live_refresh_seconds=refresh_seconds,
        summary_rows=summary_rows,
        feature_intraday_model_selector=config.feature_intraday_model_selector,
        intraday_models_enabled=config.intraday_models_enabled,
        intraday_model_default=config.intraday_model,
    )


@app.route("/api/live/stream")
@_login_required
def api_live_stream():
    _start_live_consumer()
    config = _load_runtime_config()

    def generate():
        while True:
            with LIVE_LOCK:
                snapshot = {
                    symbol: {
                        "symbol": item.symbol,
                        "price": item.price,
                        "timestamp": item.timestamp,
                        "source": item.source,
                        "market_open": item.market_open,
                    }
                    for symbol, item in LIVE_CACHE.items()
                }
            yield f"data: {json.dumps(snapshot)}\n\n"
            time.sleep(config.live_stream_seconds)

    return app.response_class(generate(), mimetype="text/event-stream")


@app.route("/api/live/capabilities")
@_login_required
def api_live_capabilities():
    _start_live_consumer()
    config = _load_runtime_config()
    return {"websocket": bool(sock and config.websocket_enabled)}


if sock is not None:

    @sock.route("/ws/live")
    def live_websocket(ws):  # pragma: no cover - websocket runtime path
        if "user_id" not in session:
            ws.close()
            return
        config = _load_runtime_config()
        while True:
            with LIVE_LOCK:
                snapshot = {
                    symbol: {
                        "symbol": item.symbol,
                        "price": item.price,
                        "timestamp": item.timestamp,
                        "source": item.source,
                        "market_open": item.market_open,
                    }
                    for symbol, item in LIVE_CACHE.items()
                }
            ws.send(json.dumps(snapshot))
            time.sleep(config.live_stream_seconds)


@app.route("/trades")
@_login_required
def trades_view():
    user_id = session["user_id"]
    workspace_id = _current_workspace_id(user_id)
    config = _load_runtime_config()
    status_filter = request.args.get("status", "").strip().upper() or None
    trades = list_trades(_db_path(), user_id, workspace_id=workspace_id, status=status_filter, limit=300)
    return render_template(
        "trades.html",
        trades=trades,
        status_filter=status_filter or "",
        broker_mode=config.broker_mode,
        allow_live_execution=config.allow_live_execution,
        live_broker_name=config.live_broker_name,
    )


@app.route("/models")
@_login_required
def model_leaderboard_view():
    user_id = session["user_id"]
    workspace_id = _current_workspace_id(user_id)
    metrics = list_model_metrics(_db_path(), user_id, workspace_id=workspace_id, limit=500)
    profiles = list_model_profiles(_db_path(), user_id, workspace_id=workspace_id, limit=500)
    grouped = {}
    for item in metrics:
        bucket = grouped.setdefault(item.model_name, {"count": 0, "mape_sum": 0.0, "rmse_sum": 0.0, "wins": 0})
        bucket["count"] += 1
        bucket["mape_sum"] += item.mape
        bucket["rmse_sum"] += item.rmse
        bucket["wins"] += 1 if item.selected else 0
    leaderboard = []
    for model_name, data in grouped.items():
        count = max(1, data["count"])
        leaderboard.append(
            {
                "model_name": model_name,
                "avg_mape": data["mape_sum"] / count,
                "avg_rmse": data["rmse_sum"] / count,
                "win_rate": (data["wins"] / count) * 100.0,
                "count": data["count"],
            }
        )
    leaderboard.sort(key=lambda row: row["avg_mape"])

    by_symbol_horizon = {}
    for item in metrics:
        key = (item.symbol, item.horizon)
        by_symbol_horizon.setdefault(key, []).append(item)
    symbol_accuracy = []
    for (symbol, horizon), entries in by_symbol_horizon.items():
        entries = sorted(entries, key=lambda x: x.created_at, reverse=True)
        recent = entries[:10]
        previous = entries[10:20]
        recent_mape = sum(x.mape for x in recent) / max(1, len(recent))
        recent_rmse = sum(x.rmse for x in recent) / max(1, len(recent))
        prev_mape = sum(x.mape for x in previous) / len(previous) if previous else recent_mape
        trend = prev_mape - recent_mape
        symbol_accuracy.append(
            {
                "symbol": symbol,
                "horizon": horizon,
                "samples": len(entries),
                "rolling_mape": recent_mape,
                "rolling_rmse": recent_rmse,
                "trend_delta": trend,
                "latest_model": recent[0].model_name if recent else "-",
            }
        )
    symbol_accuracy.sort(key=lambda row: (row["rolling_mape"], -row["samples"]))

    return render_template(
        "models.html",
        leaderboard=leaderboard,
        metrics=metrics,
        symbol_accuracy=symbol_accuracy,
        model_profiles=profiles,
    )


@app.route("/trades/<int:trade_id>/approve", methods=["POST"])
@_login_required
@_workspace_role_required("admin")
def approve_trade_route(trade_id: int):
    config = _load_runtime_config()
    limited = _rate_limit_response("mutate", config.rate_limit_mutation_per_minute)
    if limited is not None:
        return limited
    approve_trade(_db_path(), session["user_id"], trade_id)
    flash("Trade approved.")
    return redirect(url_for("trades_view"))


@app.route("/trades/<int:trade_id>/reject", methods=["POST"])
@_login_required
@_workspace_role_required("admin")
def reject_trade_route(trade_id: int):
    config = _load_runtime_config()
    limited = _rate_limit_response("mutate", config.rate_limit_mutation_per_minute)
    if limited is not None:
        return limited
    note = request.form.get("note", "").strip()
    reject_trade(_db_path(), session["user_id"], trade_id, note=note)
    flash("Trade rejected.")
    return redirect(url_for("trades_view"))


@app.route("/trades/<int:trade_id>/execute", methods=["POST"])
@_login_required
@_workspace_role_required("admin")
def execute_trade_route(trade_id: int):
    config = _load_runtime_config()
    limited = _rate_limit_response("mutate", config.rate_limit_mutation_per_minute)
    if limited is not None:
        return limited

    user_id = session["user_id"]
    trade = get_trade_by_id(_db_path(), user_id, trade_id)
    if trade is None:
        flash("Trade not found.")
        return redirect(url_for("trades_view"))

    price_raw = request.form.get("price", "").strip()
    executed_price = trade.reference_price
    if price_raw:
        try:
            executed_price = float(price_raw)
        except ValueError:
            executed_price = trade.reference_price
    else:
        with LIVE_LOCK:
            live = LIVE_CACHE.get(trade.symbol)
        if live and live.price > 0:
            executed_price = float(live.price)

    outcome = execute_trade_with_adapter(
        db_path=_db_path(),
        user_id=user_id,
        trade=trade,
        executed_price=executed_price,
        config=config,
    )
    if outcome.success:
        flash(outcome.message)
    else:
        flash(outcome.message)
    return redirect(url_for("trades_view"))


@app.route("/health")
def health():
    _start_live_consumer()
    config = _load_runtime_config()
    db_ok = db_health(_db_path())
    redis_ok = redis_health(config)
    live_stats = _live_cache_stats(config.live_stale_seconds)
    status = "ok" if db_ok and redis_ok else "degraded"
    code = 200 if (db_ok and redis_ok) else 503
    return (
        jsonify(
            {
                "status": status,
                "db_ok": db_ok,
                "redis_ok": redis_ok,
                "kafka_enabled": config.kafka_enabled,
                "live_cache_size": len(LIVE_CACHE),
                **live_stats,
                "rq_queue_depth": queue_depth(config),
                "counters": get_counters(),
            }
        ),
        code,
    )


@app.route("/api/metrics")
@_login_required
def api_metrics():
    config = _load_runtime_config()
    live_stats = _live_cache_stats(config.live_stale_seconds)
    return {
        "counters": get_counters(),
        "redis_ok": redis_health(config),
        "rq_queue_depth": queue_depth(config),
        **live_stats,
    }


def main() -> None:
    port = int(os.environ.get("PORT", 8000))
    _start_live_consumer()
    log_event("webapp_start", port=port)
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)


if __name__ == "__main__":
    main()
