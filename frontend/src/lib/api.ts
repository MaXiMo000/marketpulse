const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export interface Score {
  as_of: string
  trend: number
  reversion: number
  rel_strength: number
  vol_penalty: number
  composite: number
  band: string
}

export interface WatchlistRow {
  symbol: string
  benchmark_symbol: string
  score: Score | null
}

export async function fetchWatchlist(): Promise<WatchlistRow[]> {
  const res = await fetch(`${BASE}/v1/watchlist`)
  if (!res.ok) throw new Error(`watchlist request failed (${res.status})`)
  return res.json()
}

export async function addTicker(symbol: string): Promise<void> {
  const res = await fetch(`${BASE}/v1/watchlist/tickers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol }),
  })
  if (res.ok) return
  const body = await res.json().catch(() => null)
  const detail = typeof body?.detail === 'string' ? body.detail : 'invalid ticker symbol'
  throw new Error(detail)
}
