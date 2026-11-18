# MarketPulse

A personal swing-trading co-pilot. Not just a signal — a transparent
composite score, a labeled buy/sell/hold action, and (for buy/sell) a sized
entry/exit plan, every number traceable to a named, visible formula. No
"our AI thinks," no hidden weights, no promise of returns.

> This is an algorithmic signal, not personalized financial advice.
> MarketPulse isn't a registered investment adviser. See SPEC.md §13 before
> using this with real money.

## Status

Phase 0 (signals only): a worker scores a watchlist and a flat table shows each
score, band and the four factors behind it. Position sizing, paper trading, the
3D Terrain and alerts come in later phases — see [SPEC.md](SPEC.md) §10.

## Features

- Composite score from four named, bounded factors: trend, mean-reversion (RSI),
  relative strength vs. a benchmark, and a volatility penalty ([SPEC.md §7.2](SPEC.md))
- Bands: Strong Buy · Buy · Hold · Sell · Strong Sell
- Daily price snapshots with MA20 / MA100 for charting
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
| `GET /health` | Liveness check. |

Interactive docs are served at `/docs`.

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest
cd frontend && npm run lint && npm run build
```

## License

MIT — see [LICENSE](LICENSE).
