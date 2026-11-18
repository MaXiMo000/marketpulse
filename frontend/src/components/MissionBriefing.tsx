import type { Position, TodayRow } from '../lib/api'
import { BINDING_LABEL, pnlClass, signed, signedUsd, usd } from '../lib/format'
import { bandColor, diverging, isStrong, mission, penalty } from '../lib/hud'

interface Props {
  row: TodayRow
  position: Position | undefined
}

export default function MissionBriefing({ row, position }: Props) {
  const { label, sub } = mission(row)
  const s = row.score
  const color = s ? bandColor(s.band) : '#8a94a6'
  const deg = s ? Math.min(100, s.composite) * 3.6 : 0

  const factors = s
    ? [
        { name: 'Trend', text: signed(s.trend), bar: diverging(s.trend, 20), color: s.trend >= 0 ? 'var(--buy)' : 'var(--sell)' },
        { name: 'Mean-reversion', text: signed(s.reversion), bar: diverging(s.reversion, 20), color: s.reversion >= 0 ? 'var(--buy)' : 'var(--sell)' },
        { name: 'Relative strength', text: signed(s.rel_strength), bar: diverging(s.rel_strength, 15), color: s.rel_strength >= 0 ? 'var(--buy)' : 'var(--sell)' },
        { name: 'Volatility penalty', text: (s.vol_penalty > 0 ? '−' : '') + s.vol_penalty.toFixed(1), bar: penalty(s.vol_penalty, 15), color: 'var(--amber)' },
      ]
    : []

  const bought = position?.fills.filter((f) => f.side === 'buy').reduce((n, f) => n + f.shares, 0) ?? 0

  return (
    <section className="panel briefing" style={{ borderColor: color, boxShadow: `0 0 30px -12px ${color}` }} aria-label={`Mission briefing for ${row.symbol}`}>
      {s && isStrong(s.band) && <div className="stamp-top" style={{ color }}>CONVICTION: MAXED</div>}

      <div className="who">
        <div className="gauge" style={{ background: `conic-gradient(${color} ${deg}deg, var(--line) 0)` }}>
          <div>
            <b style={{ color }}>{s ? s.composite.toFixed(0) : '—'}</b>
            <small>/ 100</small>
          </div>
        </div>
        <div>
          <div className="sym-big">{row.symbol}</div>
          <div className="muted">{row.price === null ? 'no price yet' : `${usd(row.price)} · ${row.price_date}`}</div>
          {s && <div className="band" style={{ color }}>{s.band.toUpperCase()}</div>}
        </div>
      </div>

      <div className="mission" style={{ color }}>MISSION: {label}</div>
      <div className="mission-sub">{sub}</div>

      {factors.length > 0 && (
        <div className="factors">
          {factors.map((f) => (
            <div className="factor" key={f.name}>
              <div className="row">
                <span>{f.name}</span>
                <b style={{ color: f.color }}>{f.text}</b>
              </div>
              <div className="track">
                <div className="mid" />
                <div className="fill" style={{ left: `${f.bar.left}%`, width: `${f.bar.width}%`, background: f.color }} />
              </div>
            </div>
          ))}
        </div>
      )}

      {row.plan?.kind === 'entry' && (
        <div className="plan">
          <strong>Buy {row.plan.shares} sh ({usd(row.plan.notional)})</strong>
          {row.plan.tranches.map((t) => (
            <div className="tranche" key={t.label}>
              <i />
              <b>{t.label.toUpperCase()}</b>
              <span className="muted">{t.shares} sh</span>
            </div>
          ))}
          <div className="muted">
            Stop {usd(row.plan.stop ?? 0)} · target {usd(row.plan.target ?? 0)} · risk {usd(row.plan.risk_amount ?? 0)} · sized
            by {BINDING_LABEL[row.plan.binding ?? ''] ?? row.plan.binding}
          </div>
        </div>
      )}

      {row.plan?.kind === 'exit' && (
        <div className="plan">
          <strong>Sell all {row.plan.shares} sh ({usd(row.plan.notional)})</strong>
        </div>
      )}

      {row.holding && (
        <div className="plan">
          <div>
            <strong>
              Holding {row.holding.shares} sh @ {usd(row.holding.avg_entry)}
            </strong>{' '}
            <span className={pnlClass(row.holding.unrealized_pnl)}>{signedUsd(row.holding.unrealized_pnl)}</span>
          </div>
          {position && position.planned_shares > bought && !position.plan_cancelled && (
            <>
              <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={position.planned_shares} aria-valuenow={bought} aria-label="Plan filled">
                <div style={{ width: `${(bought / position.planned_shares) * 100}%` }} />
              </div>
              <div className="muted">Bought {bought} of {position.planned_shares} planned shares</div>
            </>
          )}
          <div className="muted">Stop {usd(row.holding.stop)} · target {usd(row.holding.target)}</div>
        </div>
      )}

      <div className="disclosure">
        <i aria-hidden="true">i</i>
        <span>Algorithmic signal, not personalized financial advice. Every number above comes from a named formula (SPEC.md §7.2).</span>
      </div>
    </section>
  )
}
