import type { Alert, TodayRow } from './api.ts'

const BAND_COLOR: Record<string, string> = {
  'Strong Buy': '#3ddc84',
  Buy: '#2fb36b',
  Hold: '#8a94a6',
  Sell: '#ff6b81',
  'Strong Sell': '#ff3b5c',
}

export const bandColor = (band: string) => BAND_COLOR[band] ?? '#8a94a6'

export const isStrong = (band: string) => band.startsWith('Strong')

const isBuy = (band: string) => band === 'Buy' || band === 'Strong Buy'
const isSell = (band: string) => band === 'Sell' || band === 'Strong Sell'

export const MAX_BAR = 4

/** Skyline height for a composite score (0-100); never zero, so a weak ticker is still visible. */
export function barHeight(score: number): number {
  return Math.max(0.25, (Math.min(100, Math.max(0, score)) / 100) * MAX_BAR)
}

/** The briefing headline for a ticker. The band's own words always appear next to it in the UI. */
export function mission(row: TodayRow): { label: string; sub: string } {
  const band = row.score?.band
  if (!band) return { label: 'AWAITING INTEL', sub: 'No score yet. The next worker cycle will brief this ticker.' }
  if (row.plan?.kind === 'entry') {
    return { label: 'ACCUMULATE', sub: 'Build the position in tranches, not one lump sum.' }
  }
  if (row.plan?.kind === 'exit') {
    return { label: 'RETREAT — EXIT', sub: 'The signal fell below Hold. Sell the position.' }
  }
  if (row.holding && isBuy(band)) {
    return { label: 'HOLD THE LINE', sub: 'Position open and signal intact. Tranches and stops are running.' }
  }
  if (isBuy(band) && row.note) return { label: 'RECHARGING', sub: row.note }
  if (isSell(band)) return { label: 'STAND DOWN', sub: row.note ?? 'No position to sell.' }
  return { label: 'HOLD STEADY', sub: 'Mid-band. No sized action until the signal flips.' }
}

/** Tickers whose band flipped in the cycle that produced their current score. */
export function pulsingSymbols(alerts: Alert[], rows: TodayRow[]): Set<string> {
  const latest = new Map(rows.map((r) => [r.symbol, r.score?.as_of]))
  return new Set(alerts.filter((a) => latest.get(a.symbol) === a.computed_at).map((a) => a.symbol))
}

/** Bar for a signed factor: grows right (positive) or left (negative) from the 50% centre line. Values are percent of the track. */
export function diverging(value: number, max: number): { left: number; width: number } {
  const width = Math.min(50, (Math.abs(value) / max) * 50)
  return { left: value >= 0 ? 50 : 50 - width, width }
}

/** Bar for an unsigned penalty: grows from the left edge. */
export function penalty(value: number, max: number): { left: number; width: number } {
  return { left: 0, width: Math.min(100, (value / max) * 100) }
}

/** Reads a factor's information-coefficient t-statistic. Anything inside |t| < 2 is treated as noise. */
export function icReading(t: number | null): 'helps' | 'hurts' | 'no signal' {
  if (t === null) return 'no signal'
  return t >= 2 ? 'helps' : t <= -2 ? 'hurts' : 'no signal'
}

export type Verdict = 'supported' | 'inconclusive' | 'inverted'

export function verdictCopy(verdict: Verdict): { headline: string; tone: 'green' | 'amber' | 'red' } {
  switch (verdict) {
    case 'supported':
      return { headline: 'Buy-band days out-returned Sell-band days, in the order the score intends.', tone: 'green' }
    case 'inverted':
      return { headline: 'The score pointed the wrong way: Sell-band days did better than Buy-band days.', tone: 'red' }
    default:
      return { headline: 'No evidence the score predicts returns in this test.', tone: 'amber' }
  }
}

/** The standing sentence in every briefing about what the backtest says, so the app never implies more than it has shown. */
export function backtestNote(verdict: Verdict | null | undefined): string {
  switch (verdict) {
    case 'supported':
      return 'Backtest: the bands ordered forward returns as intended. See the Proof Lab for the limits.'
    case 'inverted':
      return 'Backtest: the score pointed the wrong way. See the Proof Lab.'
    case 'inconclusive':
      return 'Backtest: the score has not shown it predicts returns. See the Proof Lab.'
    default:
      return 'No backtest has been run, so this score has not been checked against history.'
  }
}
