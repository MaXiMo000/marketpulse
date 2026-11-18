import { AuthError, authHeader, clearToken, getToken } from './auth'

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

export type RiskTier = 'conservative' | 'moderate' | 'aggressive'

export interface Portfolio {
  id: number
  total_value: number
  risk_tier: RiskTier
  mode: string
  live_ack_at: string | null
  cash: number
}

export interface Plan {
  kind: 'entry' | 'exit'
  shares: number
  price: number
  notional: number
  stop: number | null
  target: number | null
  risk_amount: number | null
  binding: string | null
  tranches: { label: string; offset_days: number; shares: number }[]
}

export interface Holding {
  shares: number
  avg_entry: number
  unrealized_pnl: number
  stop: number
  target: number
}

export interface TodayRow {
  symbol: string
  score: Score | null
  price: number | null
  price_date: string | null
  holding: Holding | null
  plan: Plan | null
  note: string | null
}

export interface Fill {
  side: string
  shares: number
  price: number
  data_date: string
  reason: string
}

export interface Position {
  id: number
  symbol: string
  status: 'planned' | 'open' | 'closed'
  plan_date: string
  planned_shares: number
  shares: number
  avg_entry: number
  stop: number
  target: number
  trimmed: boolean
  plan_cancelled: boolean
  close_reason: string | null
  realized_pnl: number
  unrealized_pnl: number | null
  fills: Fill[]
}

export interface Positions {
  summary: { open: number; closed: number; wins: number; losses: number; realized_pnl: number }
  positions: Position[]
}

async function failure(res: Response, fallback: string): Promise<Error> {
  if (res.status === 401) {
    clearToken(getToken() !== null) // a token was sent and refused
    return new AuthError()
  }
  if (res.status === 429) return new Error('Too many requests. Wait a minute and try again.')
  const body = await res.json().catch(() => null)
  return new Error(typeof body?.detail === 'string' ? body.detail : fallback)
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: authHeader() })
  if (!res.ok) throw await failure(res, `request failed (${res.status})`)
  return res.json()
}

async function postJson<T>(path: string, body: unknown, fallback: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeader() },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw await failure(res, fallback)
  return res.json()
}

export const fetchWatchlist = () => getJson<WatchlistRow[]>('/v1/watchlist')
export const fetchPortfolios = () => getJson<Portfolio[]>('/v1/portfolios')
export const fetchToday = (id: number) => getJson<TodayRow[]>(`/v1/portfolios/${id}/today`)
export const fetchPositions = (id: number) => getJson<Positions>(`/v1/portfolios/${id}/positions`)

export const addTicker = (symbol: string) =>
  postJson<unknown>('/v1/watchlist/tickers', { symbol }, 'invalid ticker symbol')

export const createPortfolio = (total_value: number, risk_tier: RiskTier) =>
  postJson<Portfolio>('/v1/portfolios', { total_value, risk_tier }, 'could not create portfolio')

export interface Alert {
  symbol: string
  computed_at: string
  from_band: string
  to_band: string
  from_score: number
  to_score: number
  direction: 'up' | 'down'
}

export interface HistoryPoint {
  date: string
  close: number
  ma20: number
  ma100: number
}

export const fetchAlerts = () => getJson<Alert[]>('/v1/alerts?limit=20')
export const fetchHistory = (symbol: string) =>
  getJson<{ symbol: string; points: HistoryPoint[] }>(`/v1/tickers/${encodeURIComponent(symbol)}/history?days=60`)

export const acknowledgeLive = (id: number) =>
  postJson<Portfolio>(`/v1/portfolios/${id}/live-ack`, { acknowledge: true }, 'could not enable live mode')
export const backToPaper = (id: number) =>
  postJson<Portfolio>(`/v1/portfolios/${id}/paper`, {}, 'could not switch to paper mode')

export interface BandStat {
  band: string
  n: number
  mean: number | null
  median: number | null
  hit_rate: number | null
}

export interface RunMetrics {
  total_return: number
  cagr: number | null
  max_drawdown: number
  volatility: number
  sharpe: number | null
  avg_exposure?: number
}

export type MetricKey = 'strategy' | 'equal_weight_matched' | 'benchmark_matched' | 'benchmark' | 'equal_weight'

export interface Backtest {
  created_at: string
  result: {
    params: { symbols: string[]; benchmark: string; tier: string; capital: number; start_date: string; end_date: string; trading_days: number }
    calibration: Record<string, BandStat[]>
    edge: {
      horizon: number
      verdict: 'supported' | 'inconclusive' | 'inverted'
      reason: string
      buy_mean: number | null
      sell_mean: number | null
      spread: number | null
      t_stat: number | null
    }
    factor_ic: { factor: string; ic: number | null; t_stat: number | null; n: number }[]
    metrics: Record<MetricKey, RunMetrics>
    trades: {
      closed: number
      wins: number
      losses: number
      win_rate: number | null
      avg_win_pct: number | null
      avg_loss_pct: number | null
      profit_factor: number | null
      avg_days_held: number | null
      exit_reasons: Record<string, number>
    }
    equity_curve: { dates: string[] } & Record<MetricKey, number[]>
    caveats: string[]
  }
}

/** Resolves to null when no backtest has been run yet. */
export async function fetchBacktest(): Promise<Backtest | null> {
  const res = await fetch(`${BASE}/v1/backtest`, { headers: authHeader() })
  if (res.status === 404) return null
  if (!res.ok) throw await failure(res, `request failed (${res.status})`)
  return res.json()
}
