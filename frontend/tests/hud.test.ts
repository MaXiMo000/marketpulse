import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Alert, TodayRow } from '../src/lib/api.ts'
import { barHeight, bandColor, isStrong, mission, pulsingSymbols } from '../src/lib/hud.ts'

const score = (band: string, as_of = '2025-07-07T15:00:00') => ({
  as_of, trend: 0, reversion: 0, rel_strength: 0, vol_penalty: 0, composite: 50, band,
})

const row = (over: Partial<TodayRow> & { band?: string }): TodayRow => ({
  symbol: 'AAA', price: 100, price_date: '2025-07-07', holding: null, plan: null, note: null,
  score: over.band ? score(over.band) : null,
  ...over,
})

const entryPlan = { kind: 'entry', shares: 10, price: 100, notional: 1000, stop: 92, target: 120, risk_amount: 80, binding: 'tier', tranches: [] } as const
const exitPlan = { kind: 'exit', shares: 10, price: 100, notional: 1000, stop: null, target: null, risk_amount: null, binding: null, tranches: [] } as const
const holding = { shares: 10, avg_entry: 100, unrealized_pnl: 0, stop: 92, target: 120 }

test('mission wording follows the plan, not just the band', () => {
  assert.equal(mission(row({})).label, 'AWAITING INTEL')
  assert.equal(mission(row({ band: 'Strong Buy', plan: entryPlan })).label, 'ACCUMULATE')
  assert.equal(mission(row({ band: 'Sell', plan: exitPlan, holding })).label, 'RETREAT — EXIT')
  assert.equal(mission(row({ band: 'Buy', holding })).label, 'HOLD THE LINE')
  assert.equal(mission(row({ band: 'Buy', note: 'cooling down after a recent exit' })).label, 'RECHARGING')
  assert.equal(mission(row({ band: 'Sell', note: 'no position to sell' })).label, 'STAND DOWN')
  assert.equal(mission(row({ band: 'Hold' })).label, 'HOLD STEADY')
})

test('every band has a colour and only the Strong bands are strong', () => {
  for (const b of ['Strong Buy', 'Buy', 'Hold', 'Sell', 'Strong Sell']) assert.match(bandColor(b), /^#[0-9a-f]{6}$/i)
  assert.deepEqual(['Strong Buy', 'Buy', 'Hold', 'Sell', 'Strong Sell'].map(isStrong), [true, false, false, false, true])
})

test('bar height scales with score and never collapses to nothing', () => {
  assert.equal(barHeight(100), 4)
  assert.equal(barHeight(50), 2)
  assert.ok(barHeight(0) > 0)
  assert.ok(barHeight(150) <= 4 && barHeight(-5) > 0)
})

test('only tickers whose latest cycle flipped their band pulse', () => {
  const flip = (symbol: string, computed_at: string): Alert => ({
    symbol, computed_at, from_band: 'Hold', to_band: 'Buy', from_score: 55, to_score: 68, direction: 'up',
  })
  const rows = [
    row({ symbol: 'NOW', band: 'Buy' }),                                              // as_of 15:00
    { ...row({ symbol: 'OLD' }), score: score('Buy', '2025-07-07T15:30:00') },        // flipped, but a newer cycle ran since
    row({ symbol: 'NONE', band: 'Hold' }),
  ]
  const alerts = [flip('NOW', '2025-07-07T15:00:00'), flip('OLD', '2025-07-07T15:00:00')]
  assert.deepEqual([...pulsingSymbols(alerts, rows)], ['NOW'])
})

test('diverging factor bars grow from the centre line and are capped at the track edge', async () => {
  const { diverging, penalty } = await import('../src/lib/hud.ts')
  assert.deepEqual(diverging(10, 20), { left: 50, width: 25 })     // half of the right half
  assert.deepEqual(diverging(-10, 20), { left: 25, width: 25 })    // mirrored to the left
  assert.deepEqual(diverging(99, 20), { left: 50, width: 50 })     // capped
  assert.deepEqual(diverging(0, 20), { left: 50, width: 0 })
  assert.deepEqual(penalty(7.5, 15), { left: 0, width: 50 })
  assert.deepEqual(penalty(40, 15), { left: 0, width: 100 })
})

test('a factor is only said to help or hurt when its t-statistic clears the bar', async () => {
  const { icReading } = await import('../src/lib/hud.ts')
  assert.equal(icReading(2.5), 'helps')
  assert.equal(icReading(-2.5), 'hurts')
  assert.equal(icReading(1.9), 'no signal')
  assert.equal(icReading(-0.3), 'no signal')
  assert.equal(icReading(null), 'no signal')
})

test('the backtest verdict wording never overclaims', async () => {
  const { verdictCopy } = await import('../src/lib/hud.ts')
  assert.match(verdictCopy('supported').headline, /out-returned/i)
  assert.match(verdictCopy('inconclusive').headline, /no evidence/i)
  assert.match(verdictCopy('inverted').headline, /wrong way/i)
  assert.equal(verdictCopy('inconclusive').tone, 'amber')
})

test('every briefing states what the backtest has and has not shown', async () => {
  const { backtestNote } = await import('../src/lib/hud.ts')
  assert.match(backtestNote(null), /no backtest/i)
  assert.match(backtestNote(undefined), /no backtest/i)
  assert.match(backtestNote('inconclusive'), /not shown it predicts/i)
  assert.match(backtestNote('inverted'), /wrong way/i)
  assert.match(backtestNote('supported'), /limits/i)
})
