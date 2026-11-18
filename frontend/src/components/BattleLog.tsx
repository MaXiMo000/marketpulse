import type { Portfolio, Position, Positions } from '../lib/api'
import { pnlClass, signedUsd, usd } from '../lib/format'

const REASON: Record<string, string> = {
  stop: 'stop-loss',
  signal: 'signal fell below Hold',
  target: 'take-profit',
  cancelled: 'plan cancelled before any fill',
}

function pill(p: Position): { text: string; color: string } {
  if (p.status === 'open') return { text: 'OPEN', color: 'var(--cyan)' }
  if (p.status === 'planned') return { text: 'PLANNED', color: 'var(--amber)' }
  if (p.realized_pnl > 0.005) return { text: 'WIN', color: 'var(--buy)' }
  if (p.realized_pnl < -0.005) return { text: 'LOSS', color: 'var(--sell)' }
  return { text: 'CLOSED', color: 'var(--hold)' }
}

function outcome(p: Position): string {
  if (p.status === 'closed') return REASON[p.close_reason ?? ''] ?? 'closed'
  if (p.trimmed) return 'half sold at target'
  if (p.plan_cancelled) return 'signal flipped, remaining tranches cancelled'
  if (p.status === 'planned') return 'planned'
  const bought = p.fills.filter((f) => f.side === 'buy').reduce((n, f) => n + f.shares, 0)
  return `building: ${bought} of ${p.planned_shares} shares bought`
}

export default function BattleLog({ data, mode }: { data: Positions; mode: Portfolio['mode'] }) {
  const { summary, positions } = data
  return (
    <section className="panel" aria-label="Battle log">
      <div className="head">
        <h2>Battle log</h2>
      </div>
      <p className="muted log-summary">
        {summary.open} open · {summary.closed} closed ({summary.wins} wins, {summary.losses} losses) · realized{' '}
        <span className={pnlClass(summary.realized_pnl)}>{signedUsd(summary.realized_pnl)}</span>
      </p>
      {positions.length === 0 ? (
        <p className="muted">
          {mode === 'live'
            ? 'Live positions are recorded once broker execution is enabled.'
            : 'No positions yet. Plans open automatically when a ticker reaches a Buy band.'}
        </p>
      ) : (
        <div className="log">
          {positions.map((p) => {
            const { text, color } = pill(p)
            const pnl = p.status === 'closed' ? p.realized_pnl : (p.unrealized_pnl ?? 0) + p.realized_pnl
            return (
              <details className="log-row" key={p.id}>
                <summary>
                  <span className="sym">{p.symbol}</span>
                  <span className="pill" style={{ color }}>{text}</span>
                  <span className="what">{outcome(p)}</span>
                  <span className={`pnl ${pnlClass(pnl)}`}>{signedUsd(pnl)}</span>
                </summary>
                <ul className="fills">
                  <li>
                    held {p.shares} / planned {p.planned_shares} · avg entry {p.avg_entry ? usd(p.avg_entry) : '—'} · stop {usd(p.stop)} ·
                    target {usd(p.target)}
                  </li>
                  {p.fills.map((f, i) => (
                    <li key={i}>
                      {f.data_date} {f.side} {f.shares} @ {usd(f.price)} ({f.reason})
                    </li>
                  ))}
                </ul>
              </details>
            )
          })}
        </div>
      )}
    </section>
  )
}
