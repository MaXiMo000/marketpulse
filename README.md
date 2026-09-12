# MarketPulse

A personal swing-trading co-pilot. Not just a signal — a transparent
composite score, a labeled buy/sell/hold action, and (for buy/sell) a sized
entry/exit plan, every number traceable to a named, visible formula. No
"our AI thinks," no hidden weights, no promise of returns.

**Status: spec only, no code yet.** See [SPEC.md](SPEC.md) for the full
architecture, data model, API, and phased build order.

> This is an algorithmic signal, not personalized financial advice.
> MarketPulse isn't a registered investment adviser. See SPEC.md §13 before
> using this with real money.

## Stack

- **Backend:** FastAPI, Arq (Redis-backed worker), SQLAlchemy 2.0 + Alembic,
  httpx against Finnhub + Twelve Data.
- **Frontend:** React + Vite + TypeScript, React Three Fiber (lazy-loaded),
  TanStack Query.
- **Deploy:** Render/Fly.io + Postgres + Redis, all free-tier at MVP scale.

## Build order

Phase 0 (signals only) → Phase 1 (sizing & paper trading) → Phase 2 (the
Terrain & alerts) → Phase 3 (opt-in broker execution, gated behind a daily
loss circuit breaker). Details in [SPEC.md §10](SPEC.md#10-phased-build-order).

## License

MIT — see [LICENSE](LICENSE).
