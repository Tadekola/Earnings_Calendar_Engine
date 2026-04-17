# Earnings Calendar Engine (ECE)

> **An institutional-grade, fully automated Pre-Earnings Options Scanner, Scoring Engine, and Trade Builder for liquid U.S. equities and index products.**

[![Tests](https://img.shields.io/badge/tests-189%20passing-brightgreen)](./backend/tests)
[![Scoring](https://img.shields.io/badge/scoring-v1.1.0-orange)](./backend/app/services/scoring.py)
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
4. **Routes** candidates through a **4-layer state machine** that selects the optimal strategy based on days-to-earnings
5. **Builds** precise multi-leg trade structures with optimal strike and expiration selection
6. **Scores** every candidate with an 8–10 factor weighted model (v1.1.0)
7. **Explains** every decision with full audit trail and per-factor rationale
8. **Backtests** recommendations against historical scan data with P&L analytics

The platform supports **three strategy types** across **four execution layers**:

| Layer | Phase | Strategy | Days to Earnings |
|-------|-------|----------|-----------------|
| **L1** | Pre-Earnings Anticipation | Double Calendar (Long Vega) | ≥ 7 days |
| **L2** | Imminent Earnings | Iron Butterfly ATM (Short Vega) | 0–2 days |
| **L3** | Post-Earnings Drift | Iron Butterfly Bullish | −3 to −1 days |
| **L4** | Index Overlay | Iron Butterfly ATM | Non-earnings (XSP) |

The engine exploits two of the most reliable and repeatable phenomena in options markets:

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
│   Scoring Engine      │  8–10 factor weighted model (0-100)
└───────────────────────┘
        │
   ┌────┴────┐
   ▼         ▼
≥80pts     65-79pts    <65pts
RECOMMEND  WATCHLIST   NO_TRADE
```

---

## Scoring Model (v1.1.0)

### Double Calendar Scoring (L1)

| Factor | Weight | What It Measures |
|--------|--------|-----------------|
| **Liquidity Quality** | 25 | Stock volume, options volume, bid-ask spreads |
| **Vol Term Structure** | 20 | IV curve shape between front and back expirations |
| **Earnings Timing** | 15 | Optimal days-to-earnings positioning (ideal: 14d) |
| **Pre-earnings Containment** | 15 | Calendar spread contains the expected move |
| **Pricing Efficiency** | 10 | Bid-ask tightness near ATM |
| **Event Cleanliness** | 10 | Confirmed earnings date, no conflicting events |
| **Historical Fit** | 5 | Post-earnings price behaviour patterns |
| **IV vs HV Gap** | 10 | Front-month IV vs 30-day realized vol (ratio < 0.80 = cheap, > 1.30 = expensive) |
| *Capital Preservation* | +10 | Conditional bonus for favorable max-loss / credit ratio |
| *Regime Filter* | +10 | Conditional bonus for backwardation regime |

Weights are normalized at runtime (sum to 100%). Total factors per candidate: 8 base + up to 2 conditional bonuses.

### Iron Butterfly Scoring (L2 / L3 / L4)

Butterfly candidates are scored on three factors: **IV Percentile** (weight 35), **Vol Term Structure** (weight 25), and **Residual Gap Risk** (weight 40). High IVP (>70%) is required for optimal IV crush capture.

### Classification Thresholds

| Score | Classification | Meaning |
|-------|---------------|---------|
| ≥ 80 | **RECOMMEND** | Strong setup, trade construction available |
| 65–79 | **WATCHLIST** | Promising but one or more factors are marginal |
| < 65 | **NO_TRADE** | Does not meet minimum criteria |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend API** | FastAPI 0.110, Python 3.12, async/await |
| **Database** | PostgreSQL 16 (Docker), SQLite (local dev/default), SQLAlchemy 2.0 |
| **Migrations** | Alembic (auto-applied on Docker startup) |
| **Data Providers** | FMP (earnings + prices), Tradier (options chains + Greeks + fallback quotes) |
| **Volatility Engine** | Computed from historical price data (RV10, RV20, RV30, ATR, IV rank/percentile) |
| **Strategies** | Double Calendar, Iron Butterfly ATM, Iron Butterfly Bullish |
| **Scheduling** | APScheduler — 4 daily scans: pre-market (7 AM), market open (9:30 AM), midday (12:30 PM), post-market (3:30 PM CT) |
| **Backtesting** | Full-stack backtesting engine with P&L simulation, by-strategy/layer analytics, cumulative P&L curves |
| **Frontend** | Next.js 14, TypeScript, Tailwind CSS, shadcn/ui, Lucide React, Recharts, React Query, Sonner toasts |
| **Real-time** | WebSocket scan progress streaming |
| **Logging** | structlog (structured JSON), full audit trail |
| **Testing** | pytest, pytest-asyncio — **189 tests** across 17 test files |
| **Infra** | Docker Compose, GitHub Actions CI |

---

## Features

### Scanning & Scoring
- **Multi-stage Scan Pipeline** — Earnings eligibility → Stock liquidity → Options liquidity → Volatility → Scoring → Strategy selection → Trade construction
- **4-Layer State Machine** — Automatically routes candidates to Double Calendar (L1), Iron Butterfly ATM (L2), Iron Butterfly Bullish (L3), or Index Overlay (L4) based on days-to-earnings
- **8–10 Factor Scoring Engine** — Weighted model producing 0-100 composite score with per-factor breakdown, conditional bonuses (Capital Preservation, Regime Filter), and risk warnings
- **Index Product Support** — XSP (Mini-SPX) supported with Tradier price fallback and relaxed liquidity thresholds for cash-settled European-style index options
- **Multi-Account Routing** — Candidates routed to specific accounts (e.g., SHENIDO for equities, IBKR_PERSONAL for index products)

### Trade Construction
- **Double Calendar Builder** — 4-leg structure with optimal strike and expiration selection, entry/exit dates, and P&L estimation
- **Iron Butterfly Builder** — ATM and directional butterfly structures with defined-risk profiles
- **Full Explainability** — Every recommendation includes factor-by-factor rationale, rejection reasons, and risk warnings

### Backtesting & Validation
- **Backtesting Engine** — Run backtests against historical scan recommendations with configurable strategy filters, date ranges, and minimum score thresholds
- **P&L Analytics** — Cumulative P&L curves, by-strategy breakdown, by-layer breakdown, monthly P&L, win rate, average hold days, max drawdown, Sharpe ratio
- **IV Term Structure Charts** — ATM IV per expiration visualization for any candidate

### Data & Providers
- **Live Data Providers** — FMP (`/stable` endpoints) for earnings & prices, Tradier for options chains with full Greeks
- **Tradier Fallback Pricing** — Index products (XSP) automatically fall back to Tradier `/markets/quotes` when FMP returns no data
- **Computed Volatility** — RV10, RV20, RV30, ATR, ATM IV (averaged put+call), IV rank/percentile (proper percentile calculation), term structure slope

### Frontend
- **10 Frontend Pages** — Dashboard, Scan Results, Scan History, Trade Builder, Candidate Detail (with IV term structure chart), Rejections, Audit Trail, Settings, Backtests
- **React Query** — All pages use `@tanstack/react-query` with shared cache, 30s stale time, and auto-refetch on window focus
- **Toast Notifications** — Real-time feedback via Sonner on scan complete, trade build, settings save, scheduler trigger, backtest create/delete
- **Score Distribution Chart** — Histogram of all scored candidates per scan
- **P&L Payoff Diagram** — Visual profit/loss zones for constructed trades
- **Dark Mode** — Full dark/light theme toggle

### Operations
- **4x Daily Scans** — Pre-market (7 AM), market open (9:30 AM), midday (12:30 PM), post-market (3:30 PM CT) — weekdays only
- **Editable Settings** — All thresholds (earnings window, liquidity minimums, scoring weights) configurable at runtime via UI or API
- **Audit Trail** — Every setting change, scan run, and data fetch is logged with timestamps
- **CSV Export** — Export scans, candidates, and scores to CSV
- **Real-time Progress** — WebSocket streaming of scan progress with per-ticker classification
- **Health Endpoints** — Full provider health check, Kubernetes liveness/readiness probes
- **Docker Ready** — Single `docker-compose up --build` deployment with auto-migration

---

## Architecture

```
Earnings_Calendar_Engine/
├── backend/
│   ├── app/
│   │   ├── api/v1/routes/        # 13 route modules (scan, trades, candidates,
│   │   │                         #   earnings, settings, health, dashboard,
│   │   │                         #   rejections, export, universe, websocket,
│   │   │                         #   explain, backtests)
│   │   ├── core/                 # Config, enums, logging, error handling
│   │   ├── db/                   # SQLAlchemy async engine + session
│   │   ├── models/               # 9 DB model modules (scan, trade, backtest,
│   │   │                         #   earnings, options, market_data, audit,
│   │   │                         #   settings, universe)
│   │   ├── providers/
│   │   │   ├── base.py           # Abstract interfaces + dataclasses
│   │   │   ├── live/             # FMP (earnings+prices), Tradier (options+quotes)
│   │   │   ├── computed/         # Volatility metrics from historical data
│   │   │   └── mock/             # Mock providers for testing
│   │   ├── schemas/              # Pydantic request/response models
│   │   └── services/
│   │       ├── scan_pipeline.py  # Multi-stage scan + 4-layer state machine
│   │       ├── scoring.py        # 8–10 factor weighted scoring engine
│   │       ├── liquidity.py      # Stock + options liquidity (index-aware)
│   │       ├── trade_builder.py  # Double calendar + butterfly construction
│   │       ├── backtesting.py    # Historical replay + P&L analytics
│   │       ├── strategies/       # Strategy implementations
│   │       │   ├── double_calendar.py
│   │       │   └── butterfly.py
│   │       ├── scheduler.py      # APScheduler (4 daily scan jobs)
│   │       └── ...               # audit, persistence, settings, WS manager
│   ├── alembic/                  # DB migrations (auto-applied on startup)
│   ├── scripts/                  # live_validation.py + dev utilities
│   └── tests/                    # 189 pytest tests across 17 files
├── frontend/
│   └── src/
│       ├── app/                  # 10 Next.js pages (dashboard, scan, history,
│       │                         #   trades, candidates/[ticker], rejections,
│       │                         #   audit, settings, backtests)
│       ├── components/           # shadcn/ui, charts (PayoffDiagram, ScoreDistribution,
│       │                         #   IVTermStructure), GreeksSummary, Sidebar
│       └── lib/                  # api.ts client, useScanProgress WS hook
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
# Expected: 189 passed
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
| `GET` | `/api/v1/candidates/{ticker}/iv-term-structure` | ATM IV per expiration for term structure chart |
| `POST` | `/api/v1/backtests` | Create and run a new backtest |
| `GET` | `/api/v1/backtests` | List all backtests |
| `GET` | `/api/v1/backtests/{id}` | Backtest detail with all trades |
| `GET` | `/api/v1/backtests/{id}/analytics` | P&L curve, by-strategy, by-layer, monthly analytics |
| `DELETE` | `/api/v1/backtests/{id}` | Delete a backtest |
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

For testing or custom runs, a fallback `DEFAULT_UNIVERSE` of 20 high-liquidity tickers is available:
`SPY` `QQQ` `XSP` `AAPL` `MSFT` `NVDA` `AMZN` `META` `GOOGL` `TSLA` `AMD` `NFLX` `JPM` `BAC` `XOM` `CVX` `UNH` `COST` `AVGO` `PLTR`

**Index products** (`XSP`) are handled with special logic: no stock volume check, Tradier price fallback, relaxed options liquidity thresholds, and automatic routing to Iron Butterfly L4.

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
Per-ticker classification (RECOMMEND / WATCHLIST / NO_TRADE) with score, strategy type, layer ID, account routing, factor breakdown bars, risk warnings, and rejection reasons. Score distribution histogram. Filter by classification, sort by score or ticker.

### Candidate Detail
Full candidate analysis with IV term structure chart (ATM IV per expiration), score breakdown, and trade construction link.

### Trade Builder
Automatically constructed multi-leg trade (Double Calendar or Iron Butterfly) with optimal strikes, expirations, entry/exit dates, P&L payoff diagram, and Greeks summary.

### Backtests
Create backtests with strategy filters and date ranges. View cumulative P&L curves, monthly P&L bar charts, by-strategy and by-layer breakdowns, and full trade log with per-trade outcomes.

### Rejections
Full rejection log with stage reached, reason codes, and detailed rationale for every NO_TRADE decision.

### Settings
Runtime-configurable scoring weights, liquidity thresholds, earnings window parameters, and scheduler status with next-run times for all 4 daily scan jobs.

### Audit Trail
Complete history of every scan, setting change, and data fetch with timestamps.

---

## Testing

### Software Tests

189 pytest tests across 17 test files covering:

| Test Module | Coverage |
|-------------|----------|
| `test_api.py` | All API routes (scan, trades, candidates, earnings, settings, dashboard, rejections, export, universe, explain) |
| `test_e2e.py` | End-to-end scan → score → trade construction pipeline |
| `test_scoring.py` | All 8 scoring factors, weight normalization, threshold classification |
| `test_strategies.py` | Double Calendar and Iron Butterfly scoring and structure generation |
| `test_liquidity.py` | Stock liquidity, options liquidity, ATM filtering, index-aware thresholds |
| `test_scan_pipeline.py` | Multi-stage pipeline, rejection routing, XSP special handling |
| `test_trade_builder.py` | 4-leg construction, strike selection, expiration pairing |
| `test_providers.py` | Mock and live provider interfaces, rate limiting |
| `test_persistence.py` | Database CRUD for scan runs, results, scores |
| `test_guardrails.py` | Edge cases, degenerate inputs, boundary conditions |
| `test_health.py` | Health endpoints, provider health aggregation |
| `test_audit.py` | Audit trail logging and retrieval |
| `test_ws.py` | WebSocket scan progress streaming |

```bash
cd backend
pytest -v
# Expected: 189 passed
```

### Strategy Validation

Beyond software correctness, the engine includes tooling for **strategy-level validation** — proving that the scanner's recommendations are actually useful in real market conditions.

#### Built-in Backtesting Engine

The backtesting engine (`/api/v1/backtests`) replays historical scan recommendations and simulates trade outcomes:

- **Configurable parameters** — strategy filter, minimum score threshold, date range
- **Per-trade tracking** — entry date, entry debit, exit date, exit credit, realized P&L, hold days, outcome (win/loss)
- **Aggregate analytics** — win rate, average P&L per trade, max drawdown, Sharpe ratio, cumulative P&L curve
- **Breakdown views** — by strategy type (Double Calendar vs Iron Butterfly), by layer (L1–L4), by month
- **Frontend visualization** — cumulative P&L chart, monthly bar chart, strategy/layer breakdown tables, full trade log

#### Validation Framework (Planned / In Progress)

| Layer | Method | Status |
|-------|--------|--------|
| **Software correctness** | 189 automated tests, CI pipeline, mock + live provider coverage | ✅ Complete |
| **Market-logic validation** | Backtesting engine with P&L simulation, IV term structure visualization, per-factor explainability | ✅ Complete |
| **Forward paper-trading** | Live scan journaling with actual entry/exit tracking over 4–8 weeks | 🔜 Planned |
| **Scoring model validation** | Statistical analysis of score vs outcome correlation, false positive rate measurement | 🔜 Planned |

#### Key Questions the Validation Framework Addresses

1. **Does the scoring model predict anything?** — The backtester measures whether higher-scored candidates produce better outcomes than lower-scored ones.
2. **Are rejection decisions correct?** — The rejection log (`/api/v1/rejections`) with full rationale allows audit of every NO_TRADE decision.
3. **Is the term structure logic sound?** — The IV term structure endpoint (`/api/v1/candidates/{ticker}/iv-term-structure`) visualizes the actual curve shape the scoring engine evaluated.
4. **Does the engine add value over manual screening?** — Backtest analytics provide the quantitative basis for this comparison.

---

## CI/CD

GitHub Actions pipeline runs on every push to `main`:
- Lint (ruff)
- Type check (mypy)
- Full test suite (189 tests)
- Docker build validation

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes with tests
4. Run `pytest -v` — all 189 tests must pass
5. Submit a Pull Request

---

## License

MIT License — see [LICENSE](./LICENSE) for details.

---

> **Built with precision for systematic options traders.**


