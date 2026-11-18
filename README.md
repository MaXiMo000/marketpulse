# MarketPulse

A personal swing-trading co-pilot. Not just a signal — a transparent
composite score, a labeled buy/sell/hold action, and (for buy/sell) a sized
entry/exit plan, every number traceable to a named, visible formula. No
"our AI thinks," no hidden weights, no promise of returns.

> This is an algorithmic signal, not personalized financial advice.
> MarketPulse isn't a registered investment adviser. See SPEC.md §13 before
> using this with real money.

## Status

Phases 0–2: a worker scores a watchlist; each portfolio sizes a plan from the score
and risk tier and tracks it in a paper ledger through to a realized outcome. The app
shows the watchlist as a 3D skyline, raises an alert when a ticker's band changes, and
gates live mode behind a dated acknowledgement. It deploys to Render from the included
Blueprint. Broker execution is not implemented — see [SPEC.md](SPEC.md) §10.

## Features

- Composite score from four named, bounded factors: trend, mean-reversion (RSI),
  relative strength vs. a benchmark, and a volatility penalty ([SPEC.md §7.2](SPEC.md))
- Bands: Strong Buy · Buy · Hold · Sell · Strong Sell
- Daily price snapshots with MA20 / MA100 for charting
- Risk tiers and position sizing: the smaller of a risk-based and a tier-cap size, so the tier cap is a hard limit
- Entry in three tranches, with stop-loss, take-profit and a trailing stop set when the plan is made
- Paper ledger: every plan is followed to a realized outcome, wins and losses included
- A daily-loss circuit breaker that pauses new buying after a bad day
- Portfolios are always created in paper mode; live mode requires a dated acknowledgement (enforced in the database), and live portfolios are never simulated
- The Terrain: the watchlist as a 3D skyline (height = score, color = band), with a pulse when a band flips
- Alerts when a ticker's band changes between cycles, shown in the app and optionally sent by email
- A backtest that checks the score and the paper-trading rules against real history, shown in the app as the Proof Lab
- REST API with token authentication, validated input, rate limiting and a CORS allowlist

## Stack

- **Backend:** FastAPI, SQLAlchemy 2.0 + Alembic, httpx; SQLite for local use, Postgres in production
- **Data:** [Twelve Data](https://twelvedata.com) daily time series (free tier)
- **Frontend:** React + Vite + TypeScript, TanStack Query, React Three Fiber (lazy-loaded)

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
.venv/Scripts/python -m app.worker               # one cycle now, any time of day
.venv/Scripts/python -m app.worker --scheduled   # same, but does nothing outside US market hours (for a scheduler)
```

The worker is a one-shot command: run it every 30 minutes from cron, a Render cron job, or any scheduler. It exits non-zero if
the cycle crashed or any ticker failed, so a scheduler can flag the run.

## Backtesting

```bash
cd backend
.venv/Scripts/python -m app.backtest AAPL MSFT NVDA JPM XOM JNJ --years 5 --tier moderate
```

This downloads daily history (one API call per ticker, so it takes a couple of minutes on the free tier), replays the same
signal and ledger code the worker uses once per trading day with no access to future data, stores the result, and prints a summary.
The Proof Lab panel in the app shows it. It reports:

- Forward returns by band, relative to the benchmark, and whether Buy-band days beat Sell-band days beyond chance
- How well each of the four factors, and the composite, rank-correlates with forward returns
- The strategy against the benchmark and against the same stocks held at the strategy's own average exposure
- Trade statistics, and the limits of the test (survivorship bias, same-day fills, no costs)

A transparent formula is not a proven edge; this is how you find out whether it has one.

To test candidate factors properly, run the research tool. It ranks stocks by each factor every day, compares them with their
next-20-day returns, judges each factor on the first 60% of the history and confirms on the untouched rest:

```bash
.venv/Scripts/python -m app.research            # 30 large caps, 10 years; downloads are cached in .dev/cache
```

## What the evidence says

On 31 US large caps from 2015 to 2026, the composite score's day-by-day rank correlation with the next 20 days' returns was not
statistically significant in the period it was judged on, and changed sign in the held-back final 40% of the history. The candidate
factors tested alongside it (12-1 month momentum, 5- and 21-day reversal, low volatility) did not hold up in both periods either.
In the 5-year backtest, the strategy performed about the same as holding the same stocks at the same average exposure; its
measurable difference was lower drawdowns from the stop-loss rules.

Treat MarketPulse as a framework for position sizing, staged entries and pre-set exits, not as a forecast. Both tools are in the
repository so you can re-run them on your own tickers and periods.

## Paper trading rules

Each worker cycle, after scoring, every portfolio is advanced:

- A Buy or Strong Buy opens a plan sized to the portfolio's tier (risk per trade / max position) and its free cash.
- The position is bought in three tranches: now, +2 and +4 trading days. If the signal leaves the Buy bands before the
  last tranche, the remaining tranches are cancelled.
- Exits: stop-loss at −8%; half sold at +20%; a trailing stop that follows the high at 5% once the position is +10%;
  and a full exit if the score falls into the Sell bands.
- A ticker cannot be re-entered for 5 trading days after an exit.
- Daily-loss circuit breaker: if equity falls by the tier's limit (1% / 2% / 3%) from the previous close, new buying is paused for
  that day. Exits keep working.
- Fills use the latest daily close, with no slippage or fees. Exchange holidays are not modelled.

## Deploying on Render

`render.yaml` is a Blueprint for the whole app:

| Service | Type | What it does |
|---|---|---|
| `marketpulse-api` | Web service (free plan) | The API. Runs migrations on start. Sleeps after 15 idle minutes and takes about a minute to wake. |
| `marketpulse-cycle` | Cron job | Runs `python -m app.worker --scheduled` every 30 minutes during US market hours. |
| `marketpulse-app` | Static site | The frontend, built with a Content-Security-Policy that allows only itself and the API. |
| `marketpulse-db` | Postgres | Paid plan: Render deletes free Postgres databases 30 days after creation, which would destroy the ledger. |

Render's plans and prices change; check the dashboard before creating the Blueprint. The cron job and the database are paid.

1. Push this repository to GitHub. In Render choose **New > Blueprint** and select it. Enter your `TWELVEDATA_API_KEY` when prompted.
2. Wait for the first deploy. If Render assigned URLs other than `marketpulse-api.onrender.com` and `marketpulse-app.onrender.com`
   (names are global), rename the services in `render.yaml` and update `CORS_ORIGINS` (API) and `VITE_API_URL` (static site) to match.
3. Open `marketpulse-api` > **Environment** and copy the generated `API_TOKEN`. Open the app URL and paste it when asked.
4. Create a paper portfolio and add tickers. Scores appear at the next cron run, or trigger one from the cron job's page.
5. Pushes to `main` redeploy automatically once CI passes.

Optional:

- **Email alerts:** add `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_EMAIL_FROM` and `ALERT_EMAIL_TO` to the cron job
  (the job sends them). Use an SMTP provider on port 587; Render blocks outbound port 25.
- **A backtest in the hosted app:** the database accepts internal connections only. Temporarily add your IP under the database's
  access settings, then run `DATABASE_URL=<external connection string> python -m app.backtest AAPL MSFT NVDA` from `backend/`.
- **Rotating secrets:** change `API_TOKEN` or `TWELVEDATA_API_KEY` in the dashboard and redeploy; sign in again with the new token.

Production refuses to start without a strong `API_TOKEN`, explicit `CORS_ORIGINS` and a non-SQLite `DATABASE_URL`. Keep the API at a
single instance: rate limiting is held in process memory. `PROXY_HOPS=1` makes it use the client address Render's proxy recorded.

## Configuration

| Variable | Where | Purpose |
|---|---|---|
| `APP_ENV` | backend | `development` (default) or anything else for production. Production refuses to start without a strong `API_TOKEN` and explicit `CORS_ORIGINS`, and serves no API docs. |
| `API_TOKEN` | backend | Access token for every `/v1` endpoint (32+ characters outside development). The app asks for it on first load. |
| `DATABASE_URL` | backend | Database URL. Defaults to a local SQLite file, which production refuses; `postgres://` and `postgresql://` URLs from a host work as given. |
| `PROXY_HOPS` | backend | Trusted reverse proxies in front of the API (default 0, which ignores `X-Forwarded-For`; use 1 on Render). |
| `TWELVEDATA_API_KEY` | backend | Twelve Data API key (free tier is enough). |
| `CORS_ORIGINS` | backend | Comma-separated origins allowed to call the API. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | backend | Optional SMTP server for flip emails (STARTTLS). Email is off while `SMTP_HOST` is empty. |
| `ALERT_EMAIL_FROM`, `ALERT_EMAIL_TO` | backend | Sender and recipient of flip emails. |
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
| `POST /v1/portfolios/{id}/live-ack` | Record the dated acknowledgement (`{"acknowledge": true}`) and switch to live mode. |
| `POST /v1/portfolios/{id}/paper` | Return to paper mode and clear the acknowledgement. |
| `GET /v1/alerts?limit=50` | Recent band flips, newest first. |
| `GET /v1/backtest` | The latest stored backtest result. |
| `GET /health` | Liveness and database check (no authentication). |

Interactive docs are served at `/docs`.

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest
cd frontend && npm run lint && npm test && npm run build
```

Four extra tests run every migration up and down and exercise a cycle, the ledger and the API on a real Postgres. They are skipped
unless you point `TEST_DATABASE_URL` at an empty database, for example
`TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/marketpulse_test`. CI runs them on every push and also validates
`render.yaml` against Render's schema.

## License

MIT — see [LICENSE](LICENSE).
