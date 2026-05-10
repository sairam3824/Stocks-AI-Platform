# 📈 Stocks AI Platform

**A local-first, SaaS-style stock analytics platform with AI-powered forecasting, live streaming, sentiment analysis, and paper-trading workflows.**

![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0+-000000?logo=flask&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-5.0+-DC382D?logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

---

## ✨ Features

**Portfolio & Forecasting**

- Multi-market portfolio management — track stocks across US 🇺🇸, India 🇮🇳, UK 🇬🇧, Japan 🇯🇵, and more with market flags and grouping
- AI-powered forecasting — configurable daily (21-day default) and intraday horizons with automatic model selection (`auto`, `stat`, `lstm`, `tft`)
- Smart recommendations — automated Upside / Neutral / Downside signals with ranking scores and per-stock thresholds
- Sentiment analysis — hybrid scoring via Ollama LLM + rule-based lexicon, with multi-source news ingestion (RSS, SerpAPI, Reddit, X/Twitter)
- Per-symbol model profiles — persists best-performing model per stock and retrains on a configurable schedule
- Company name lookup — symbol auto-complete and resolution for seamless stock discovery
- Custom skill overrides — fine-tune per-symbol behavior via `skills/<SYMBOL>.md` markdown files

**Live Streaming & Quotes**

- Real-time price streaming via Kafka/Redpanda with market-aware polling intervals
- SSE and WebSocket endpoints for push-based live updates
- Provider failover telemetry — tracks preferred vs. fallback provider usage
- Cache freshness monitoring — real-time stale/fresh symbol counters

**Paper Trading**

- Automated trade intents generated from top forecast recommendations
- Full trade lifecycle — approve, reject, execute with price overrides
- Broker adapter layer — `paper` and `live` modes with `allow_live_execution` safety gate
- Filterable trades dashboard with status-based views

**Reporting & Visualization**

- Interactive Plotly charts with confidence bands and forecast horizon markers
- Timestamped report history — per-run index and individual symbol pages
- Sortable report tables in the web UI
- Model leaderboard — MAPE, RMSE, and win rate across all runs with rolling out-of-sample accuracy

**Security & Access Control**

- Full auth system — register, login, logout, password reset with token flow
- Optional TOTP 2FA — setup, verify, and disable via security settings
- Workspace RBAC — `owner`, `admin`, `member` roles with route-level enforcement
- CSRF protection on all mutation routes
- Rate limiting on auth and mutation endpoints

**Observability**

- `/health` — DB health, Redis status, queue depth, runtime counters
- `/api/metrics` — structured telemetry for monitoring integrations
- Progress bar + toast notifications — real-time forecast progress in the UI

---

## 🏗 Architecture

```
                   ┌──────────────┐
                   │  Web Browser  │
                   └──────┬───────┘
                          │ HTTP / WSS
                   ┌──────▼───────┐
                   │    Nginx      │
                   │ Reverse Proxy │
                   └──────┬───────┘
                          │
          ┌───────────────▼───────────────┐
          │       Flask (Gunicorn)         │
          │         src/webapp.py          │
          └──┬──────────┬──────────┬──────┘
             │          │          │
    Enqueue  │   Read/  │   SSE/   │  Consume
      Job    │   Write  │    WS    │  Prices
             │          │          │
      ┌──────▼──┐  ┌────▼────┐  ┌─▼──────────┐
      │  Redis  │  │ SQLite  │  │  Redpanda   │
      │   RQ    │  │   DB    │  │   Kafka     │
      └──┬──────┘  └─────────┘  └─▲───────────┘
         │                        │
    Dequeue                  Publish Prices
         │                        │
  ┌──────▼──────────┐   ┌────────┴────────┐
  │   RQ Worker     │   │  Live Producer   │
  │  src/tasks.py   │   │ src/live_producer│
  └──────┬──────────┘   └─────────────────┘
         │
    ┌────▼─────┐
    │ Reports  │
    │  Output  │
    └──────────┘
```

**Runtime Flow:**

1. **User triggers** `/run` from the dashboard
2. **Flask** creates a `runs` record and enqueues `run_forecast_job` into Redis/RQ
3. **RQ Worker** consumes the job, executes the forecasting pipeline, writes report files, and records metrics/trades
4. **UI polls** the latest run status and displays a progress bar with a completion/failure toast

---

## 🚀 Quick Start

### Prerequisites

- **Python** 3.11+ (or Conda environment)
- **Docker Desktop** (recommended for Redis + Redpanda)
- **pip** for Python dependencies

### 1. Clone & Install

```bash
git clone https://github.com/sairam3824/Stocks-AI-Platform.git
cd Stocks-AI-Platform
pip install -r requirements.txt
```

### 2. Run Everything (One Command)

```bash
./scripts/run_all.sh config/portfolio.json 8000
```

This script handles:

- Starting Redis and Redpanda via Docker (if available)
- Running Alembic database migrations
- Starting the Gunicorn web server
- Starting the RQ background worker
- Starting the live price producer

Open **http://127.0.0.1:8000** in your browser.

### 3. Manual Setup (Separate Terminals)

**Terminal 1 — Infrastructure:**

```bash
docker compose up -d redis redpanda
```

**Terminal 2 — Database Migrations:**

```bash
./scripts/run_migrations.sh config/portfolio.json
```

**Terminal 3 — Web Server:**

```bash
./scripts/run_web.sh
```

**Terminal 4 — Background Worker:**

```bash
./scripts/run_worker.sh config/portfolio.json
```

**Terminal 5 — Live Price Producer (optional):**

```bash
./scripts/run_live_producer.sh config/portfolio.json
```

### 4. Docker Compose (Full Stack)

```bash
./scripts/run_docker_stack.sh
```

| Service | URL |
|---|---|
| App | http://127.0.0.1:8000 |
| Nginx Proxy | http://127.0.0.1:8080 |
| Redis | redis://127.0.0.1:6379/0 |
| Redpanda Console | http://127.0.0.1:9644 |

---

## 📁 Project Structure

```
stocks/
├── src/                        # Core application source code
│   ├── webapp.py               #   Flask routes, auth, RBAC, dashboards
│   ├── tasks.py                #   Background forecast job execution
│   ├── worker.py               #   RQ worker process
│   ├── pipeline.py             #   Forecast pipeline orchestration
│   ├── forecast.py             #   Forecasting model implementations
│   ├── recommendations.py      #   Buy/hold/sell signal generation
│   ├── sentiment.py            #   Hybrid sentiment scoring engine
│   ├── news.py                 #   Multi-source news aggregation
│   ├── live_producer.py        #   Real-time price producer
│   ├── live_kafka.py           #   Kafka consumer for live quotes
│   ├── db.py                   #   SQLite data access layer
│   ├── config.py               #   Configuration loader
│   ├── charts.py               #   Plotly chart generation
│   ├── report.py               #   HTML report builder
│   ├── security.py             #   Rate limiting & CSRF
│   ├── execution.py            #   Trade execution adapter
│   └── symbol_lookup.py        #   Company/symbol resolution
├── templates/                  # Jinja2 HTML templates
│   ├── base.html               #   Base layout with navigation
│   ├── dashboard.html          #   Main portfolio dashboard
│   ├── live.html               #   Real-time quotes page
│   ├── reports.html            #   Historical reports viewer
│   ├── trades.html             #   Paper trading dashboard
│   └── models.html             #   Model leaderboard
├── config/                     # Configuration files
│   └── portfolio.json          #   Primary runtime configuration
├── scripts/                    # Shell scripts for running services
├── migrations/                 # Alembic database migrations
├── docker/                     # Docker-related configs (nginx, etc.)
├── tests/                      # Test suite
├── skills/                     # Per-symbol skill overrides
├── data/                       # SQLite database storage
├── reports/                    # Generated forecast reports
├── Dockerfile                  # Container image definition
├── docker-compose.yml          # Multi-service orchestration
├── requirements.txt            # Python dependencies
└── pytest.ini                  # Test runner config
```

---

## 🔐 RBAC Matrix

| Action | Owner | Admin | Member |
|---|---|---|---|
| View Dashboard / Live / Reports | Yes | Yes | Yes |
| Add / Delete Stocks | Yes | Yes | No |
| Run Forecast | Yes | Yes | No |
| Approve / Reject / Execute Trades | Yes | Yes | No |
| Modify Engine Settings | Yes | Yes | No |
| Switch Workspaces | Yes | Yes | Yes |

---

## ⚙️ Configuration

Primary config file: `config/portfolio.json`

| Key | Default | Description |
|---|---|---|
| `redis_url` | `redis://localhost:6379/0` | Redis connection string |
| `rq_queue_name` | `forecast_jobs` | RQ queue name |
| `rq_job_timeout_seconds` | `3600` | Max job execution time |
| `database_url` | `sqlite:///data/stocks.db` | Database connection string |
| `horizon_days` | `21` | Forecast horizon (trading days) |
| `intraday_models_enabled` | `["auto","stat","lstm","tft"]` | Available intraday models |
| `model_retrain_interval_days` | `7` | Days between model retraining |
| `news_source` | `rss` | `rss`, `serpapi`, `reddit`, `x`, `social`, `mixed` |
| `sentiment_provider` | `auto` | `auto`, `ollama`, `lexicon` |
| `sentiment_llm_weight` | `0.7` | LLM vs. lexicon blend weight |
| `broker_mode` | `paper` | `paper` or `live` |
| `allow_live_execution` | `false` | Safety gate for live trades |

---

## 🔑 API Keys

| Use Case | Required Key | Notes |
|---|---|---|
| Daily historical forecasting | None | Uses Stooq (free) by default |
| Intraday forecasting / live quotes | `TWELVE_DATA_API_KEY` | Or Alpha Vantage key |
| Enhanced news coverage | `SERPAPI_API_KEY` | Optional, improves sentiment |
| X/Twitter sentiment | `X_API_BEARER_TOKEN` | For `news_source="x"`, `"social"`, or `"mixed"` |

Set keys as environment variables or in `config/portfolio.json`.

---

## 🔒 Auth Flows

- **Password Reset:** Forgot password → reset link (flashed) → set new password
- **2FA (TOTP):** Generate secret → confirm OTP → login requires OTP going forward

---

## 🧪 Testing

```bash
# Syntax check all source files
python -m compileall -q src templates migrations tests

# Run test suite
pytest -q
```

---

## 🔧 Troubleshooting

**Queue is unavailable**

- Start Redis: `docker compose up -d redis`
- Start worker: `./scripts/run_worker.sh config/portfolio.json`
- Fallback: set `queue_fallback_inline=true` to run forecasts in-process

**NoBrokersAvailable**

- Start Redpanda/Kafka: `docker compose up -d redpanda`
- Or disable Kafka/live producer for forecast-only runs

**gunicorn: not found / ModuleNotFoundError**

- Install dependencies: `pip install -r requirements.txt`
- `scripts/run_web.sh` falls back to Flask dev server if Gunicorn is missing

**TemplateNotFound**

- Ensure the app runs from the repository root so `templates/` resolves correctly

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](./LICENSE) file for details.
