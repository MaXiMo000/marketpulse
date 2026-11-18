import { useQuery } from '@tanstack/react-query'
import { fetchPositions, type Position } from '../lib/api'
import { pnlColor, signedUsd, usd } from '../lib/format'

const REASON: Record<string, string> = {
  stop: 'stop-loss',
  signal: 'signal fell below Hold',
  target: 'take-profit',
  cancelled: 'plan cancelled before any fill',
}

function outcome(p: Position): string {
  if (p.status === 'closed') return REASON[p.close_reason ?? ''] ?? 'closed'
  if (p.trimmed) return 'half sold at target'
  if (p.plan_cancelled) return 'signal flipped, remaining tranches cancelled'
  if (p.status === 'planned') return 'planned'
  const bought = p.fills.filter((f) => f.side === 'buy').reduce((n, f) => n + f.shares, 0)
  return `building: ${bought} of ${p.planned_shares} shares bought`
}

export default function Ledger({ portfolioId }: { portfolioId: number }) {
  const positions = useQuery({
    queryKey: ['positions', portfolioId],
    queryFn: () => fetchPositions(portfolioId),
    refetchInterval: 60_000,
  })

  if (positions.isPending) return <p>Loading…</p>
  if (positions.isError) return <p role="alert" className="error">{positions.error.message}</p>
  const { summary, positions: rows } = positions.data
  return (
    <>
      <p className="muted">
        {summary.open} open · {summary.closed} closed ({summary.wins} wins, {summary.losses} losses) · realized{' '}
        <span style={{ color: pnlColor(summary.realized_pnl) }}>{signedUsd(summary.realized_pnl)}</span>
      </p>
      {rows.length === 0 ? (
        <p className="muted">No positions yet. Plans open automatically when a ticker reaches a Buy band.</p>
      ) : (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Status</th>
                <th>Held / planned</th>
                <th>Avg entry</th>
                <th>Stop</th>
                <th>Target</th>
                <th>Outcome</th>
                <th>P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => {
                const pnl = p.status === 'closed' ? p.realized_pnl : (p.unrealized_pnl ?? 0) + p.realized_pnl
                return (
                  <tr key={p.id}>
                    <td>
                      <details>
                        <summary>{p.symbol}</summary>
                        <ul className="fills">
                          {p.fills.map((f, i) => (
                            <li key={i}>
                              {f.data_date} {f.side} {f.shares} @ {usd(f.price)} ({f.reason})
                            </li>
                          ))}
                        </ul>
                      </details>
                    </td>
                    <td>{p.status}</td>
                    <td>{p.shares} / {p.planned_shares}</td>
                    <td>{p.avg_entry ? usd(p.avg_entry) : '—'}</td>
                    <td>{usd(p.stop)}</td>
                    <td>{usd(p.target)}</td>
                    <td className="muted">{outcome(p)}</td>
                    <td style={{ color: pnlColor(pnl) }}>{signedUsd(pnl)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
