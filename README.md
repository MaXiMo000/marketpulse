# MarketPulse

A personal swing-trading co-pilot. Not just a signal — a transparent
composite score, a labeled buy/sell/hold action, and (for buy/sell) a sized
entry/exit plan, every number traceable to a named, visible formula. No
"our AI thinks," no hidden weights, no promise of returns.

> This is an algorithmic signal, not personalized financial advice.
> MarketPulse isn't a registered investment adviser. See SPEC.md §13 before
> using this with real money.

## Status

Phases 0–1: a worker scores a watchlist; each portfolio sizes a plan from the score
and risk tier and tracks it in a paper ledger through to a realized outcome. The 3D
Terrain, alerts and live mode come in later phases — see [SPEC.md](SPEC.md) §10.

## Features

- Composite score from four named, bounded factors: trend, mean-reversion (RSI),
  relative strength vs. a benchmark, and a volatility penalty ([SPEC.md §7.2](SPEC.md))
- Bands: Strong Buy · Buy · Hold · Sell · Strong Sell
- Daily price snapshots with MA20 / MA100 for charting
- Risk tiers and position sizing: the smaller of a risk-based and a tier-cap size, so the tier cap is a hard limit
- Entry in three tranches, with stop-loss, take-profit and a trailing stop set when the plan is made
- Paper ledger: every plan is followed to a realized outcome, wins and losses included
- Portfolios are always created in paper mode; live mode requires a dated acknowledgement (enforced in the database)
- REST API with validated input and a CORS allowlist

## Stack

- **Backend:** FastAPI, Arq worker, SQLAlchemy 2.0 + Alembic, httpx
- **Data:** [Twelve Data](https://twelvedata.com) daily time series (free tier)
- **Frontend:** React + Vite + TypeScript, TanStack Query

## Setup

Requires Python 3.12+ and Node 20+.

```bash
# backend
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt   # macOS/Linux: .venv/bin/pip
cp .env.example .env                                  # then fill in TWELVEDATA_API_KEY
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m uvicorn app.main:app --port 8000

# frontend (second terminal)
cd frontend
cp .env.example .env
npm install
npm run dev
```

Open http://localhost:5173, add a ticker, then run a signal cycle:

```bash
cd backend
.venv/Scripts/python -m app.worker        # one cycle now, any time of day
.venv/Scripts/arq app.worker.WorkerSettings   # scheduled: every 30 min in US market hours (needs Redis)
```

## Paper trading rules

Each worker cycle, after scoring, every portfolio is advanced:

- A Buy or Strong Buy opens a plan sized to the portfolio's tier (risk per trade / max position) and its free cash.
- The position is bought in three tranches: now, +2 and +4 trading days. If the signal leaves the Buy bands before the
  last tranche, the remaining tranches are cancelled.
- Exits: stop-loss at −8%; half sold at +20%; a trailing stop that follows the high at 5% once the position is +10%;
  and a full exit if the score falls into the Sell bands.
- A ticker cannot be re-entered for 5 trading days after an exit.
- Fills use the latest daily close, with no slippage or fees. Exchange holidays are not modelled.

## Configuration

| Variable | Where | Purpose |
|---|---|---|
| `DATABASE_URL` | backend | SQLAlchemy URL. Defaults to a local SQLite file; use Postgres in production. |
| `REDIS_URL` | backend | Redis for the Arq scheduler. |
| `TWELVEDATA_API_KEY` | backend | Twelve Data API key (free tier is enough). |
| `CORS_ORIGINS` | backend | Comma-separated origins allowed to call the API. |
| `VITE_API_URL` | frontend | Base URL of the API. |

## API

| Method & path | Purpose |
|---|---|
| `POST /v1/watchlist/tickers` | Add a ticker (optional `benchmark_symbol`, default `SPY`). |
| `GET /v1/watchlist` | Every watched ticker with its latest score, factors and band. |
| `GET /v1/tickers/{symbol}/history?days=60` | Daily close with MA20 / MA100. |
| `POST /v1/portfolios` | Create a paper portfolio (`total_value`, `risk_tier`: conservative / moderate / aggressive). |
| `GET /v1/portfolios` | List portfolios with free cash. |
| `GET /v1/portfolios/{id}/today` | Every watched ticker with score, band, holding and — for Buy/Sell — a sized plan. |
| `GET /v1/portfolios/{id}/positions` | Planned, open and closed positions with fills, P&L and a win/loss summary. |
| `GET /health` | Liveness check. |

Interactive docs are served at `/docs`.

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest
cd frontend && npm run lint && npm run build
```

## License

MIT — see [LICENSE](LICENSE).
