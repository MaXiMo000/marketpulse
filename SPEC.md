# MarketPulse — SPEC v1

## 1. What this is, in one line

A personal swing-trading co-pilot: for a watchlist of tickers it computes a
transparent composite score, turns that score into a buy/sell/hold action,
and — for buy/sell — a sized entry/exit plan, all traceable back to named
formulas, not a black-box "AI thinks."

## 2. Why this, why now

Most retail signal tools stop at "here's the RSI, draw your own conclusion."
That's honest but unfinished — the actual decision (what to trade, how much,
when to get out) still has to happen in the user's head, under time pressure,
with no record of what the tool actually predicted last time. MarketPulse
closes that loop for one user's own portfolio: same transparent-formula
discipline, but it finishes the sentence — a score, a labeled action, a
position size bounded by the portfolio's own risk tier, and dated entry/exit
levels set before emotion has a vote.

It stays a personal tool by design (see §12 on the registration line) —
built for the one portfolio it's configured for, not a multi-tenant advice
product.

## 3. Scope decisions for v1 (each with its reasoning — don't relitigate)

- **One composite formula, four named factors, no ML.** trend, mean-reversion
  (RSI), relative strength vs. a benchmark, and a volatility penalty — each
  bounded, each visible, each independently inspectable. A model that can't
  show its work isn't trustworthy enough to size money against, and a
  from-scratch ML model needs far more data and validation than this project
  can honestly deliver at v1.
- **Paper mode is the default and cannot be skipped.** Every new portfolio
  starts in Paper. Live requires an explicit, dated acknowledgement stored
  per portfolio (§7.6) — not a one-time install checkbox. This is a product
  decision, not a legal-copy afterthought.
- **Delayed data is fine.** Finnhub + Twelve Data free tiers run ~20 minutes
  behind. Irrelevant at this system's timeframe: every plan in §7.4 is
  measured in trading *days*. This is a swing/position tool; it does not
  pretend to intraday latency it doesn't have.
- **One shared signal pool, per-portfolio sizing.** The composite score is
  computed once per ticker, on a 30-minute worker cycle, shared by every
  portfolio watching it. Sizing (which depends on each portfolio's risk
  tier and capital) happens cheaply at read time in the API. Don't
  recompute the expensive part (indicators, API calls) per portfolio.
- **No broker execution in v1.** Recommendations are plans, not orders.
  Broker integration is Phase 3, opt-in, and gated behind its own circuit
  breaker (§10) — never bundled into the core signal loop.

## 4. What v1 explicitly does NOT do (state it, don't silently skip it)

- No brokerage order placement (Phase 3, later, opt-in).
- No multi-user / multi-tenant advice product — one user's own portfolios.
- No intraday/day-trading timeframe — swing/position only, per §3.
- No machine-learned scoring model — formula only, per §3.
- No options, futures, or crypto in v1 — cash equities only.
- No backtesting engine in v1 (see §13 — worth having before trusting the
  formula with real money, deliberately not blocking Phase 0-1).

## 5. Architecture overview

One scheduled worker (Arq, Redis-backed) polls Finnhub and Twelve Data every
30 minutes during market hours for every ticker on the shared watchlist,
computes each ticker's composite score once, and writes it to Postgres.
FastAPI reads the latest score plus each portfolio's risk tier and capital
to build a sized recommendation at request time. The React + Vite frontend
polls `/v1/portfolios/{id}/today` via TanStack Query and renders it as a
2D price chart (real detail) plus a small-multiples 3D "Terrain" overview
(one bar per watched ticker — see §8.3), never the reverse: 3D is spent only
where a skyline reads better than a table, not for the detail view.

```
React + Vite  ──GET /today──▶  FastAPI  ◀──reads/writes──▶  Postgres
                                   ▲                              ▲
                                   │ sizes rec per portfolio       │ writes composite score
                                   │                              │
                              Arq worker ──every 30 min──▶  Finnhub / Twelve Data
                                   │
                                   ▼
                              Alert queue (band flips)
```

## 6. Data flow: from "add a ticker" to "see a sized recommendation"

1. User adds a ticker to the shared watchlist (`POST /v1/watchlist/tickers`).
2. On the next worker cycle (≤30 min), the worker pulls quotes + history for
   every watched ticker, computes MA20/MA100/RSI14/20d return/annualized
   vol, then the four named factors and the composite score (§7.2), and
   writes a `composite_scores` row.
3. Client calls `GET /v1/portfolios/{id}/today`. FastAPI joins the latest
   `composite_scores` row per ticker with the portfolio's risk tier, sizes
   a plan for any Buy/Sell band (§7.3–7.4), and returns the full picture —
   score, factors, action, size, entry/exit — in one response.
4. If a ticker's band changes between cycles, the worker also writes an
   alert-queue row; the frontend surfaces this as a distinct event, not a
   silently-updated number (§7.5's whole point).

## 7. Backend

### 7.1 Stack

- **FastAPI** + Pydantic v2 for the API.
- **Arq** — Redis-backed scheduled worker for the 30-minute signal cycle.
- **SQLAlchemy 2.0** + Alembic for the data model and migrations.
- **httpx** for Finnhub / Twelve Data calls, with response fixtures recorded
  for tests (§11).

### 7.2 The composite score, exactly how it's computed

```python
# all four factors are visible, bounded, and independently named
trend        = clip(((MA20/MA100) - 1) * 300, -20, 20)        # 20d vs 100d moving-average gap
reversion    = RSI <= 40 ? (40-RSI)*0.4 : (RSI >= 70 ? -(RSI-70)*0.5 : 0)
rel_strength = clip((ret_20d_stock - ret_20d_benchmark) * 200, -15, 15)
vol_penalty  = clip((annualised_vol_pct - 25) * 0.3, 0, 15)   # conviction, not direction

composite = clamp(50 + trend + reversion + rel_strength - vol_penalty, 0, 100)
```

Bands: ≥80 Strong Buy · 65–79 Buy · 45–64 Hold · 25–44 Sell · <25 Strong Sell.
"Strong" and regular bands share a hue (good vs. critical); the label always
says both direction and conviction in words, never color alone.

### 7.3 Position sizing — two independent caps, the smaller one wins

```python
risk_based_shares = (portfolio_value * risk_per_trade_pct) / (entry_price * stop_distance_pct)
cap_based_shares  = (portfolio_value * tier_max_position_pct) / entry_price
final_shares      = min(risk_based_shares, cap_based_shares)   # the tier cap is a hard rail
```

Risk tiers (set once per portfolio, applied automatically): Conservative —
0.5% risk/trade, 3% max/position · Moderate — 1% / 6% · Aggressive — 2% / 10%.
A Strong Buy never overrides the portfolio-level cap — conviction changes
the score, never the ceiling.

### 7.4 Entry, exit, and re-evaluation

- **Entry — tranches, not a lump sum.** Split the sized position across 3
  tranches (e.g. now / +2 trading days / +4 trading days). If the signal
  flips before the last tranche, the plan is cancelled, not completed.
- **Exit — set at entry.** Stop-loss (e.g. -8%), take-profit trim (e.g.
  +20%), and a trailing stop that tightens after a profit threshold are all
  computed and stored when the plan is created, not decided in the moment.
- **Re-evaluation is an event, not a silent update.** If a held position's
  composite drops below the Hold threshold, that fires a Trim/Sell plan
  immediately rather than waiting for the user to notice a changed number.
  Every recommendation carries an `as_of` timestamp from the last worker
  cycle.

### 7.5 Why polling, not WebSockets, for v1

The worker cycle is 30 minutes; nothing in this system needs sub-second
delivery. TanStack Query polling on the frontend is simpler to build, test,
and deploy than a WebSocket channel, and matches the actual data freshness
— adding push infra ahead of an actual latency requirement is exactly the
kind of premature aim this spec is trying to avoid. Band-change alerts
(§7.4) can start as poll-and-diff on the client and move to real push
(email/mobile) in Phase 2 once there's an actual delivery channel to push
to.

### 7.6 Data model (Postgres, via SQLAlchemy)

- **portfolios** — `id, user_id, total_value, risk_tier, mode ('paper'|
  'live'), live_ack_at (nullable)`.
- **tickers** — `symbol, benchmark_symbol`.
- **price_snapshots** — `ticker_id, observed_at, close, ma20, ma100, rsi14,
  ann_vol`.
- **composite_scores** — `ticker_id, computed_at, trend, reversion,
  rel_strength, vol_penalty, composite, band` — unique per (ticker, cycle).
- **positions** — `portfolio_id, ticker_id, shares, entry_price, stop,
  target, status ('planned'|'open'|'closed')`.

### 7.7 API endpoints (v1)

| Method & path | Purpose |
|---|---|
| `POST /v1/portfolios` | Create a portfolio — value, risk tier, mode (defaults to paper). |
| `POST /v1/portfolios/{id}/live-ack` | Record the dated disclosure acknowledgement, switch to Live. |
| `POST /v1/watchlist/tickers` | Add a ticker to the shared, once-computed signal pool. |
| `GET /v1/portfolios/{id}/today` | Every watched ticker's composite score, band, and — for Buy/Sell — a sized entry/exit plan. |
| `GET /v1/tickers/{symbol}/history?days=60` | Price + MA20 + MA100 series for the chart. |
| `GET /v1/portfolios/{id}/positions` | Open, planned, and closed positions with realised/unrealised outcome. |

## 8. Frontend

### 8.1 Stack

React 18 + Vite + TypeScript, React Three Fiber + drei (lazy-loaded chunk,
not on the critical render path), TanStack Query for polling/cache, plain
CSS custom properties — no UI kit.

### 8.2 Component tree

`App` (router + query client) → `PortfolioShell` (polls `/today`) →
`TerrainScene` (R3F canvas, lazy) + `RecommendationCard` (score, factors,
plan, disclosure) + `PriceChart` (SVG, MA overlays, hover tooltip) +
`PositionLedger` (paper + live track record).

### 8.3 The Terrain — what it encodes, and why 3D only here

One bar per watched ticker: height = composite score, color = band (hue)
× conviction (shade), a pulse ring fires once when a band changes, selection
happens via a 2D chip rail (not 3D picking, which is fiddly on a small
canvas). It's a genuine small-multiples view — a whole watchlist reads as
a skyline instead of a table scanned row by row. It deliberately does not
replace the price chart: extruded 3D candlesticks read worse than a 2D line,
so price history stays a proper SVG chart, and 3D is spent only on the
overview, where it earns its place.

### 8.4 Disclosure — in the product, not just in a terms page

Every recommendation card carries the disclosure inline, always expanded,
never a link-out: *algorithmic signal, not personalized financial advice*.
New portfolios default to Paper. Every closed position — stop-loss, take-
profit, or manual close — logs to a history the app shows by default, so
the tool's own miss rate is as visible as its calls (§10.5 of the roadmap
below exists specifically so this isn't decorative).

## 9. Folder structure

```
marketpulse/
  backend/
    app/
      main.py            # FastAPI app, route registration
      models.py           # SQLAlchemy models (§7.6)
      schemas.py           # Pydantic request/response models
      scoring.py           # composite score + bands (§7.2)
      sizing.py            # position sizing + entry/exit plans (§7.3–7.4)
      routers/             # one module per resource (portfolios, tickers, positions)
      worker.py            # Arq worker: 30-min signal cycle
      clients/             # finnhub.py, twelvedata.py — httpx wrappers
    alembic/
    tests/
      fixtures/            # recorded real API responses
  frontend/
    src/
      App.tsx
      components/           # PortfolioShell, TerrainScene, RecommendationCard, PriceChart, PositionLedger
      lib/                  # query client, types
    public/
  render.yaml
  SPEC.md
  README.md
```

## 10. Phased build order

**Phase 0 — signals only.** FastAPI + worker computing the composite score
and band (§7.2) for 5–10 real tickers against real Finnhub/Twelve Data
pulls — no sizing, no paper trading yet, flat non-3D UI (a table is fine).
**Goal: prove the formula produces sane, explainable bands on real tickers
before building anything on top of it.** No fixture data once this phase
starts — real API responses from day one, recorded as test fixtures.

**Phase 1 — sizing & paper trading.** Risk tiers, position sizing (§7.3),
entry/exit plans (§7.4), and a paper-mode ledger that tracks every planned
position through to a realised outcome. This is where the tool starts
producing something a person could actually act on, and it ships before
any visual polish — the part that changes what you do with money matters
more than the part that looks impressive.

**Phase 2 — the Terrain & alerts.** The R3F terrain scene (§8.3), the
Live-mode disclosure gate with dated acknowledgement (§8.4), and real
push/email delivery for band-change alerts (§7.4, §7.5).

**Phase 3 — broker integration (opt-in, higher risk).** Alpaca (US) or
Zerodha Kite Connect (India) for one-click execution of a planned tranche.
A mandatory daily-loss circuit breaker must exist and be tested *before*
this phase ships — it is the one phase where a bug moves real money, and
it is deliberately last.

**Explicitly out of scope for any v1 phase**: multi-tenant accounts, ML
scoring, options/futures/crypto, intraday timeframes, a mobile app. Noted
here so nobody "discovers" them mid-build as if they were forgotten — they
were considered and deferred on purpose.

## 11. Testing & verification discipline

- Real fixtures, not synthetic one-liners: record a handful of real
  Finnhub/Twelve Data responses once, commit them as test fixtures, don't
  hit live network on every CI run and don't mock a response shape you've
  never actually seen.
- **Live-verify each phase against real tickers** before calling it done —
  not just unit tests on the scoring math. Phase 0 in particular is only
  done once its bands look sane on tickers you actually recognize.
- The sizing math (§7.3) gets an explicit test asserting the tier cap wins
  even when the risk-based calculation would allow a larger position —
  that's the one invariant this whole system must never violate silently.
- The disclosure/paper-mode gate (§8.4) gets a test asserting a portfolio
  cannot reach `mode='live'` without a `live_ack_at` timestamp — this is
  the one guard that turns a bug into a real-money incident if it's ever
  bypassed.

## 12. Deployment

API + worker on Fly.io or Render (matching the `render.yaml` pattern this
portfolio already uses elsewhere), Postgres on Neon or Supabase free tier,
Redis on Upstash free tier, frontend on Vercel or Netlify. Cost at MVP
scale: $0 — Finnhub and Twelve Data free tiers plus the above cover a
personal build. Broker integration (Phase 3) may carry its own API fees,
evaluated then.

## 13. Open questions / risks deliberately left to the building agent

- **Registration reality.** Running this for yourself is a personal tool.
  The moment it gives buy/sell calls to *other* people — especially for
  pay — most jurisdictions treat that as regulated investment advice
  (SEC/state RIA in the US, SEBI Research Analyst / Investment Adviser
  rules in India). Decide which one this is before anyone else logs in;
  v1 assumes single-user.
- **No backtesting engine yet.** A transparent formula is not a proven
  edge. Worth building before trusting the formula with real (Live-mode)
  money — deliberately not a blocker for Phase 0–1, which are paper-only
  by default anyway.
- **Model risk stays real.** Momentum/mean-reversion rules can whipsaw in
  a sideways market. Stop-losses (§7.4) are the mitigation, not a promise
  the score is always right.
- **Which broker for Phase 3** — Alpaca vs. Zerodha depends on which
  market the live portfolio actually trades in; left open until Phase 3.
