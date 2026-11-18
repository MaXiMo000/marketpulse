import { useQuery } from '@tanstack/react-query'
import { fetchToday, type Plan, type TodayRow } from '../lib/api'
import { BAND_COLOR, BINDING_LABEL, pnlColor, signed, signedUsd, usd } from '../lib/format'

function PlanCell({ row }: { row: TodayRow }) {
  const plan: Plan | null = row.plan
  if (!plan) return <span className="muted">{row.note ?? '—'}</span>
  if (plan.kind === 'exit') {
    return <strong>Sell all {plan.shares} sh ({usd(plan.notional)})</strong>
  }
  return (
    <div>
      <strong>Buy {plan.shares} sh ({usd(plan.notional)})</strong>
      <div className="muted">
        {plan.tranches.map((t) => `${t.shares} ${t.label}`).join(' / ')}
      </div>
      <div className="muted">
        stop {usd(plan.stop ?? 0)} · target {usd(plan.target ?? 0)} · risk {usd(plan.risk_amount ?? 0)} ·
        sized by {BINDING_LABEL[plan.binding ?? ''] ?? plan.binding}
      </div>
    </div>
  )
}

export default function TodayTable({ portfolioId }: { portfolioId: number }) {
  const today = useQuery({
    queryKey: ['today', portfolioId],
    queryFn: () => fetchToday(portfolioId),
    refetchInterval: 60_000,
  })

  if (today.isPending) return <p>Loading…</p>
  if (today.isError) return <p role="alert" className="error">{today.error.message}</p>
  return (
    <div className="scroll">
      <table>
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Price</th>
            <th>Score</th>
            <th>Band</th>
            <th title="trend · reversion · relative strength · volatility penalty">Why</th>
            <th>Plan</th>
            <th>Holding</th>
          </tr>
        </thead>
        <tbody>
          {today.data.map((row) => (
            <tr key={row.symbol}>
              <td>{row.symbol}</td>
              <td>{row.price === null ? '—' : usd(row.price)}</td>
              {row.score ? (
                <>
                  <td>{row.score.composite.toFixed(1)}</td>
                  <td style={{ color: BAND_COLOR[row.score.band], fontWeight: 600 }}>{row.score.band}</td>
                  <td className="muted">
                    {signed(row.score.trend)} · {signed(row.score.reversion)} · {signed(row.score.rel_strength)} · −
                    {row.score.vol_penalty.toFixed(1)}
                  </td>
                </>
              ) : (
                <td colSpan={3} className="muted">waiting for the next worker cycle</td>
              )}
              <td><PlanCell row={row} /></td>
              <td>
                {row.holding ? (
                  <>
                    {row.holding.shares} sh @ {usd(row.holding.avg_entry)}
                    <div style={{ color: pnlColor(row.holding.unrealized_pnl) }}>
                      {signedUsd(row.holding.unrealized_pnl)}
    </div>
                </>
              ) : (
                <span className="muted">—</span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
</div>
  )
}
