import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { fetchBacktest, type Backtest, type MetricKey } from '../lib/api'
import { usd, utc } from '../lib/format'
import { diverging, icReading, verdictCopy } from '../lib/hud'

const pct = (v: number | null, digits = 1) => (v === null ? 'n/a' : `${v >= 0 ? '+' : '−'}${Math.abs(v * 100).toFixed(digits)}%`)

const share = (v: number | null) => (v === null ? 'n/a' : `${(v * 100).toFixed(0)}%`)

const ROWS: { key: MetricKey; label: string; note: string }[] = [
  { key: 'strategy', label: 'This strategy', note: 'sized plans, tranches, stops' },
  { key: 'equal_weight_matched', label: 'Same stocks, equal weight, same exposure', note: 'the fair comparison' },
  { key: 'benchmark_matched', label: 'Benchmark at the same exposure', note: 'rest in cash' },
  { key: 'benchmark', label: 'Benchmark, fully invested', note: '' },
  { key: 'equal_weight', label: 'Same stocks, equal weight, fully invested', note: '' },
]

const LINES: { key: MetricKey; label: string; color: string }[] = [
  { key: 'strategy', label: 'Strategy', color: 'var(--cyan)' },
  { key: 'equal_weight_matched', label: 'Same stocks, same exposure', color: 'var(--amber)' },
  { key: 'benchmark', label: 'Benchmark', color: 'var(--text)' },
]

function Curve({ result }: { result: Backtest['result'] }) {
  const c = result.equity_curve
  const W = 860
  const H = 200
  const all = LINES.flatMap((l) => c[l.key])
  const lo = Math.min(...all)
  const hi = Math.max(...all)
  const y = (v: number) => H - ((v - lo) / (hi - lo || 1)) * H
  const path = (values: number[]) =>
    values.map((v, i) => `${i === 0 ? 'M' : 'L'}${((i / (values.length - 1)) * W).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  return (
    <>
      <div className="legend" style={{ marginBottom: 6 }}>
        {LINES.map((l) => (
          <span key={l.key}><i style={{ background: l.color }} />{l.label}: {usd(c[l.key].at(-1) ?? 0)}</span>
        ))}
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        role="img"
        style={{ width: '100%', height: 200, display: 'block' }}
        aria-label={`Account value from ${usd(c.strategy[0])}: strategy ends at ${usd(c.strategy.at(-1) ?? 0)}, benchmark at ${usd(c.benchmark.at(-1) ?? 0)}`}
      >
        {LINES.map((l) => (
          <path key={l.key} d={path(c[l.key])} fill="none" stroke={l.color} strokeWidth="2" vectorEffect="non-scaling-stroke" />
        ))}
      </svg>
    </>
  )
}

export default function ProofLab() {
  const [horizon, setHorizon] = useState<'20' | '5'>('20')
  const run = useQuery({ queryKey: ['backtest'], queryFn: fetchBacktest })

  let body
  if (run.isPending) body = <p className="muted">Loading…</p>
  else if (run.isError) body = <p role="alert" className="error">{run.error.message}</p>
  else if (!run.data) {
    body = (
      <p className="muted">
        No backtest has been run yet, so nothing here has been checked against history. Run{' '}
        <code>python -m app.backtest NVDA AAPL MSFT JPM XOM</code> in the backend folder.
      </p>
    )
  } else {
    const { result } = run.data
    const { edge, params } = result
    const verdict = verdictCopy(edge.verdict)
    body = (
      <>
        <div className={`verdict ${verdict.tone}`} role="status">
          <strong>{verdict.headline}</strong>
          <div>
            Over {edge.horizon} trading days, Buy-band days returned {pct(edge.buy_mean, 2)} vs {pct(edge.sell_mean, 2)} for Sell-band
            days, relative to {params.benchmark}
            {edge.t_stat !== null && <> (spread {pct(edge.spread, 2)}, t = {edge.t_stat.toFixed(2)}; about 2 is the minimum to rule out chance)</>}.
          </div>
        </div>

        <h3>Do the bands predict returns?</h3>
        <div className="inline" role="group" aria-label="Forward return horizon">
          {(['20', '5'] as const).map((h) => (
            <button key={h} type="button" className="btn ghost" aria-pressed={horizon === h} onClick={() => setHorizon(h)}>
              {h} days ahead
            </button>
          ))}
        </div>
        <div className="scroll">
          <table>
            <thead>
              <tr><th>Band</th><th>Days</th><th>Avg return vs {params.benchmark}</th><th>Median</th><th>Beat {params.benchmark}</th></tr>
            </thead>
            <tbody>
              {result.calibration[horizon].map((b) => {
                const bar = diverging((b.mean ?? 0) * 100, 3)
                return (
                  <tr key={b.band}>
                    <td>{b.band}</td>
                    <td>{b.n.toLocaleString()}</td>
                    <td>
                      <div className="cell-bar">
                        <span>{pct(b.mean, 2)}</span>
                        <div className="track"><div className="mid" /><div className="fill" style={{ left: `${bar.left}%`, width: `${bar.width}%`, background: (b.mean ?? 0) >= 0 ? 'var(--buy)' : 'var(--sell)' }} /></div>
                      </div>
                    </td>
                    <td>{pct(b.median, 2)}</td>
                    <td>{b.hit_rate === null ? 'n/a' : `${(b.hit_rate * 100).toFixed(0)}%`}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <p className="muted">A working score would show Strong Buy highest and Strong Sell lowest, in order.</p>

        <h3>Which factors help?</h3>
        <div className="scroll">
          <table>
            <thead>
              <tr><th>Factor</th><th title="rank correlation with the next {edge.horizon} days' return vs benchmark">Correlation</th><th>t-stat</th><th>Reading</th></tr>
            </thead>
            <tbody>
              {result.factor_ic.map((f) => {
                const reading = icReading(f.t_stat)
                return (
                  <tr key={f.factor}>
                    <td>{f.factor}</td>
                    <td>{f.ic === null ? 'n/a' : f.ic.toFixed(3)}</td>
                    <td>{f.t_stat === null ? 'n/a' : f.t_stat.toFixed(2)}</td>
                    <td className={reading === 'helps' ? 'gain' : reading === 'hurts' ? 'loss' : 'muted'}>{reading}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <h3>Does the strategy beat simply holding?</h3>
        <div className="scroll">
          <table>
            <thead>
              <tr><th>Compared with</th><th>Total return</th><th>Per year</th><th>Worst drop</th><th>Sharpe</th></tr>
            </thead>
            <tbody>
              {ROWS.map(({ key, label, note }) => {
                const m = result.metrics[key]
                return (
                  <tr key={key} className={key === 'strategy' ? 'strong-row' : undefined}>
                    <td>{label}{note && <div className="muted">{note}</div>}</td>
                    <td>{pct(m.total_return)}</td>
                    <td>{pct(m.cagr)}</td>
                    <td>{pct(m.max_drawdown)}</td>
                    <td>{m.sharpe === null ? 'n/a' : m.sharpe.toFixed(2)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <p className="muted">
          The strategy held {share(result.metrics.strategy.avg_exposure ?? null)} of its capital on average, so
          fully invested rows are not like-for-like. Compare it with the rows marked "same exposure".
        </p>
        <Curve result={result} />

        <h3>The trades</h3>
        <p className="muted">
          {result.trades.closed} closed trades · {share(result.trades.win_rate)} winners · average win {pct(result.trades.avg_win_pct)}, average
          loss {pct(result.trades.avg_loss_pct)} · profit factor {result.trades.profit_factor?.toFixed(2) ?? 'n/a'} · held{' '}
          {result.trades.avg_days_held?.toFixed(0) ?? 'n/a'} days on average · exits:{' '}
          {Object.entries(result.trades.exit_reasons).map(([k, v]) => `${v} ${k}`).join(', ')}
        </p>

        <h3>Read this before trusting any of it</h3>
        <ul className="caveats">
          {result.caveats.map((c) => <li key={c}>{c}</li>)}
        </ul>
        <p className="muted">
          {params.symbols.join(', ')} · {params.start_date} to {params.end_date} ({params.trading_days.toLocaleString()} trading days) ·{' '}
          {params.tier} tier · run {utc(run.data.created_at).toLocaleDateString()}
        </p>
      </>
    )
  }

  return (
    <section className="panel proof" aria-label="Proof lab">
      <div className="head">
        <div>
          <h2>The Proof Lab: does the score actually work?</h2>
          <div className="sub">The real signal and ledger code, replayed over real history with no peeking at the future</div>
        </div>
      </div>
      {body}
    </section>
  )
}
