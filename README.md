# Earnings Calendar Engine (ECE)

> **An institutional-grade, fully automated Pre-Earnings Double Calendar Scanner and Trade Builder for liquid U.S. equities.**

[![Tests](https://img.shields.io/badge/tests-113%20passing-brightgreen)](./backend/tests)
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-14-black)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/docker-compose-2496ED)](https://www.docker.com/)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

---

## What Is This?

The **Earnings Calendar Engine** is a full-stack quantitative options scanning platform that:

1. **Monitors** the S&P 500 universe (or custom watchlists) for upcoming earnings events
2. **Pre-filters** candidates by price, options activity, and weekly expiration availability
3. **Scans** each ticker through a multi-stage filtering and scoring pipeline
4. **Identifies** high-probability pre-earnings Double Calendar spread opportunities
5. **Builds** the precise 4-leg trade structure with optimal strike and expiration selection
6. **Explains** every decision with full audit trail and rationale

The platform is built for traders who want to systematically exploit two of the most reliable and repeatable phenomena in options markets:

- **Theta Decay Differential** — Short-dated options decay exponentially faster than long-dated options
- **Post-Earnings IV Crush** — Implied Volatility collapses 20-40% immediately after an earnings announcement, benefiting the premium seller

> **Disclaimer:** This application is for educational and decision-support purposes only. It does not guarantee profits. Options trading involves significant risk of loss. Always consult a licensed financial advisor before trading.

---

## The Strategy: Pre-Earnings Double Calendar

### Structure
A Double Calendar spread consists of **4 legs**:

| Leg | Action | Strike | Expiration |
|-----|--------|--------|------------|
| 1 | **SELL** | Lower (Put) | Front month (before earnings) |
| 2 | **BUY** | Lower (Put) | Back month (after earnings) |
| 3 | **SELL** | Upper (Call) | Front month (before earnings) |
| 4 | **BUY** | Upper (Call) | Back month (after earnings) |

### Why It Works
- **Positive Theta**: The short-dated options you sell decay faster every day, generating income
- **Defined Risk**: Maximum loss is capped at the initial net debit paid
- **Wide Profit Range**: Unlike a single calendar, the double structure creates a profit tent spanning ±8-10% of the stock price
- **Delta Neutral**: Opposing deltas cancel out, isolating pure volatility and time exposure
- **IV Crush Capture**: Selling expensive pre-earnings IV and buying cheaper post-earnings IV locks in the volatility premium

### Candidate Selection Flow

```
S&P 500 Universe (~500 tickers)
        │
        ▼
┌───────────────────────┐
│  Quality Pre-Filter   │  Price ≥ $100, ≥ 6 future expirations,
│                       │  weekly options required → drops ~50%
└───────────────────────┘
        │ Pass
        ▼
┌───────────────────────┐
│  Earnings Eligibility │  7-21 days to earnings, confirmed date
└───────────────────────┘
        │ Pass
        ▼
┌───────────────────────┐
│   Stock Liquidity     │  > 2M average daily volume
└───────────────────────┘
        │ Pass
        ▼
┌───────────────────────┐
│  Options Liquidity    │  > 50 avg volume, < 25% bid-ask spread
│                       │  (Filtered to ATM-adjacent strikes)
└───────────────────────┘
        │ Pass
        ▼
┌───────────────────────┐
│  Volatility Profile   │  RV 20-40%, favorable term structure
└───────────────────────┘
        │ Pass
        ▼
┌───────────────────────┐
│   Scoring Engine      │  7-factor weighted model (0-100)
└───────────────────────┘
        │
   ┌────┴────┐
   ▼         ▼
≥80pts     65-79pts    <65pts
RECOMMEND  WATCHLIST   NO_TRADE
```

---

## Scoring Model (v1.0.0)

| Factor | Weight | What It Measures |
|--------|--------|-----------------|
| **Liquidity Quality** | 25% | Stock volume, options volume, bid-ask spreads |
| **Vol Term Structure** | 20% | IV curve shape between front and back expirations |
| **Earnings Timing** | 15% | Optimal days-to-earnings positioning |
| **Pre-earnings Containment** | 15% | Calendar spread contains the expected move |
| **Pricing Efficiency** | 10% | IV relative to historical realized volatility |
| **Event Cleanliness** | 10% | Confirmed earnings date, no conflicting events |
| **Historical Fit** | 5% | Post-earnings price behaviour patterns |

**Classification Thresholds:** `≥80` → RECOMMEND | `≥65` → WATCHLIST | `<65` → NO_TRADE

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend API** | FastAPI 0.110, Python 3.12, async/await |
| **Database** | PostgreSQL 16 (Docker), SQLite (local dev/default), SQLAlchemy 2.0 |
| **Migrations** | Alembic (14 tables) |
| **Data Providers** | FMP (earnings + prices), Tradier (options chains + Greeks) |
| **Volatility Engine** | Computed from historical price data (RV10, RV20, RV30, ATR) |
| **Scheduling** | APScheduler (daily pre-market + evening post-market scans) |
| **Frontend** | Next.js 14, TypeScript, Tailwind CSS |
| **Real-time** | WebSocket scan progress streaming |
| **Logging** | structlog (structured JSON), full audit trail |
| **Testing** | pytest, pytest-asyncio (113 tests) |
| **Infra** | Docker Compose, GitHub Actions CI |

---

## Features

- **Live Data Providers** — FMP (`/stable` endpoints) for earnings & prices, Tradier for options chains with full Greeks
- **Multi-stage Scan Pipeline** — Earnings eligibility → Stock liquidity → Options liquidity → Volatility → Scoring → Trade construction
- **7-Factor Scoring Engine** — Weighted model producing 0-100 composite score with full factor-level breakdown
- **4-Leg Trade Builder** — Automatic optimal strike and expiration selection for double calendar construction
- **Full Explainability** — Every recommendation includes factor-by-factor rationale, rejection reasons, and audit logs
- **Real-time Progress** — WebSocket streaming of scan progress with per-ticker classification
- **8 Frontend Pages** — Dashboard, Scan Results, Scan History, Trade Builder, Candidate Detail, Rejections, Audit Trail, Settings
- **Editable Settings** — All thresholds (earnings window, liquidity minimums, scoring weights) configurable at runtime
- **Audit Trail** — Every setting change, scan run, and data fetch is logged with timestamps and actor
- **CSV Export** — Export scans, candidates, and scores to CSV
- **APScheduler** — Automatic daily scans at pre-market and post-market hours
- **Dark Mode** — Full dark/light theme toggle
- **Docker Ready** — Single `docker-compose up --build` deployment

---

## Architecture

```
Earnings_Calendar_Engine/
├── backend/
│   ├── app/
│   │   ├── api/v1/routes/        # 12 route modules (scan, trades, candidates,
│   │   │                         #   earnings, settings, health, dashboard,
│   │   │                         #   rejections, export, universe, websocket, explain)
│   │   ├── core/                 # Config, enums, logging, error handling
│   │   ├── db/                   # SQLAlchemy async engine + session
│   │   ├── models/               # 8 DB table models
│   │   ├── providers/
│   │   │   ├── base.py           # Abstract interfaces + dataclasses
│   │   │   ├── live/             # FMP (earnings+prices) + Tradier (options)
│   │   │   ├── computed/         # Volatility metrics from historical data
│   │   │   └── mock/             # Mock providers for testing
│   │   ├── schemas/              # Pydantic request/response models
│   │   └── services/
│   │       ├── scan_pipeline.py  # Multi-stage scan orchestration
│   │       ├── scoring.py        # 7-factor weighted scoring engine
│   │       ├── liquidity.py      # Stock + options liquidity evaluation
│   │       ├── trade_builder.py  # 4-leg double calendar construction
│   │       └── ...               # other core service modules
│   ├── alembic/                  # DB migrations
│   ├── scripts/                  # live_validation.py + dev utilities
│   └── tests/                    # 113 pytest tests across 14 files
├── frontend/
│   └── src/
│       ├── app/                  # 7 Next.js pages
│       ├── components/           # Toast, Providers, shared UI
│       └── lib/                  # api.ts client, useScanProgress WebSocket hook
├── docker-compose.yml
├── .env.template
└── .gitignore
```

---

## Quick Start

### Prerequisites

- Docker Desktop installed and running
- FMP API key (paid tier) — [financialmodelingprep.com](https://financialmodelingprep.com)
- Tradier API key (paid tier) — [tradier.com](https://tradier.com)

### 1. Clone & Configure

```bash
git clone https://github.com/Tadekola/Earnings_Calendar_Engine.git
cd Earnings_Calendar_Engine
cp .env.template .env
```

Edit `.env` with your API keys:

```env
FMP_API_KEY=your_fmp_key_here
TRADIER_ACCESS_TOKEN=your_tradier_key_here
TRADIER_BASE_URL=https://api.tradier.com/v1
STRICT_LIVE_DATA=True
ALLOW_SIMULATION=False
```

### 2. Docker Compose (Recommended)

```bash
docker-compose up --build
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3002 |
| Backend API | http://localhost:8002 |
| API Docs (Swagger) | http://localhost:8002/docs |
| API Docs (ReDoc) | http://localhost:8002/redoc |

### 3. Local Development

**Backend:**
```bash
cd backend
pip install poetry
poetry install
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev   # runs on http://localhost:3001
```

### 4. Run Tests

```bash
cd backend
pytest -v
# Expected: 113 passed
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | System health + all provider statuses |
| `GET` | `/health/live` | Kubernetes liveness probe |
| `GET` | `/health/ready` | Kubernetes readiness probe |
| `POST` | `/api/v1/scan/run` | Trigger full universe scan (synchronous) |
| `POST` | `/api/v1/scan/run/async` | Trigger async scan (returns run_id immediately) |
| `GET` | `/api/v1/scan/run/{run_id}` | Poll for async scan results |
| `GET` | `/api/v1/scan/results` | List all past scan summaries |
| `GET` | `/api/v1/candidates/{ticker}` | Full candidate detail + score breakdown |
| `GET` | `/api/v1/trades/{ticker}/recommended` | Recommended double calendar trade |
| `POST` | `/api/v1/trades/build` | Build trade for any ticker |
| `POST` | `/api/v1/trades/reprice` | Reprice trade with custom parameters |
| `GET` | `/api/v1/earnings/upcoming` | Upcoming earnings calendar (configurable window) |
| `GET` | `/api/v1/universe` | Active ticker universe |
| `GET` | `/api/v1/explain/{ticker}` | Full explainability report with rationale |
| `GET` | `/api/v1/rejections` | Rejection log with reasons and codes |
| `GET` | `/api/v1/dashboard/summary` | Dashboard KPIs and recent scans |
| `GET` | `/api/v1/dashboard/audit` | Full audit trail |
| `GET` | `/api/v1/settings` | Current application settings |
| `PUT` | `/api/v1/settings` | Update settings at runtime |
| `GET` | `/api/v1/settings/scheduler` | Scheduled job status |
| `POST` | `/api/v1/settings/scheduler/trigger` | Manually trigger scheduled scan |
| `GET` | `/api/v1/export/scans/csv` | Export scan history to CSV |
| `GET` | `/api/v1/export/candidates/csv` | Export candidates to CSV |
| `GET` | `/api/v1/export/scores/csv` | Export score breakdowns to CSV |
| `WS` | `/api/v1/ws/scan` | WebSocket real-time scan progress stream |

---

## Data Providers

| Provider | Purpose | Endpoint Base |
|----------|---------|--------------|
| **FMP (Financial Modeling Prep)** | Earnings calendar, historical prices, quotes | `https://financialmodelingprep.com/stable` |
| **Tradier** | Options chains, Greeks, expirations | `https://api.tradier.com/v1` |
| **Computed Volatility** | RV10/RV20/RV30, ATR, IV rank/percentile | Derived from FMP historical data |
| **Mock** | All data types (for testing/dev) | Local in-memory |

---

## Universe

The default scan universe is the **S&P 500** (`UNIVERSE_SOURCE=STATIC`).

For testing or custom runs, a fallback `DEFAULT_UNIVERSE` of 19 high-liquidity U.S. equities is available:
`SPY` `QQQ` `AAPL` `MSFT` `NVDA` `AMZN` `META` `GOOGL` `TSLA` `AMD` `NFLX` `JPM` `BAC` `XOM` `CVX` `UNH` `COST` `AVGO` `PLTR`

The universe is fully configurable via the Settings page or API.

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FMP_API_KEY` | Financial Modeling Prep API key | Required for live mode |
| `TRADIER_ACCESS_TOKEN` | Tradier brokerage API key | Required for live mode |
| `TRADIER_BASE_URL` | Tradier API base URL | `https://api.tradier.com/v1` |
| `STRICT_LIVE_DATA` | Reject mock/fallback data | `True` |
| `ALLOW_SIMULATION` | Allow simulated data in strict mode | `False` |
| `UNIVERSE_SOURCE` | Source of ticker universe (`STATIC`, `S&P500`, etc) | `STATIC` |
| `PREFILTER_ENABLED` | Pre-filter universe before options chain fetch | `True` |
| `PREFILTER_MIN_STOCK_PRICE` | Minimum stock price for pre-filter | `100.0` |
| `PREFILTER_MIN_EXPIRATION_COUNT`| Minimum future expirations required | `6` |
| `EARN_MIN_DAYS_TO_EARNINGS` | Minimum days to earnings | `7` |
| `EARN_MAX_DAYS_TO_EARNINGS` | Maximum days to earnings | `21` |
| `LIQ_MIN_AVG_STOCK_VOLUME` | Minimum average daily stock volume | `2000000` |
| `LIQ_MIN_AVG_OPTION_VOLUME` | Minimum average option contract volume | `50` |
| `LIQ_MAX_BID_ASK_PCT` | Maximum bid-ask spread as % of price | `0.25` |
| `SCORING_RECOMMEND_THRESHOLD` | Minimum score for RECOMMEND | `80.0` |
| `SCORING_WATCHLIST_THRESHOLD` | Minimum score for WATCHLIST | `65.0` |
| `DATABASE_URL` | SQLAlchemy database URL | SQLite in dev |

---

## Screenshots

### Dashboard
Real-time KPIs, system health, provider status, top candidates, recent scans, and upcoming earnings calendar.

### Scan Results
Per-ticker classification (RECOMMEND / WATCHLIST / NO_TRADE) with score, factor breakdown, and rejection reasons.

### Trade Builder
Automatically constructed 4-leg double calendar with optimal strikes, expirations, and entry/exit guidelines.

### Rejections
Full rejection log with stage reached, reason codes, and detailed rationale for every NO_TRADE decision.

### Audit Trail
Complete history of every scan, setting change, and data fetch with timestamps.

---

## CI/CD

GitHub Actions pipeline runs on every push to `main`:
- Lint (ruff)
- Type check (mypy)
- Full test suite (113 tests)
- Docker build validation

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes with tests
4. Run `pytest -v` — all 113 tests must pass
5. Submit a Pull Request

---

## License

MIT License — see [LICENSE](./LICENSE) for details.

---

> **Built with precision for systematic options traders.**
