import { useQuery } from '@tanstack/react-query'
import { useState, type PointerEvent } from 'react'
import { fetchHistory, type HistoryPoint } from '../lib/api'
import { usd } from '../lib/format'

const W = 860
const H = 220

const path = (points: HistoryPoint[], pick: (p: HistoryPoint) => number, y: (v: number) => number) =>
  points.map((p, i) => `${i === 0 ? 'M' : 'L'}${((i / (points.length - 1)) * W).toFixed(1)},${y(pick(p)).toFixed(1)}`).join(' ')

export default function PriceChart({ symbol }: { symbol: string }) {
  const history = useQuery({ queryKey: ['history', symbol], queryFn: () => fetchHistory(symbol), refetchInterval: 60_000 })
  const [hover, setHover] = useState<number | null>(null)
  const points = history.data?.points ?? []

  let body
  if (history.isPending) body = <p className="muted">Loading…</p>
  else if (history.isError) body = <p role="alert" className="error">{history.error.message}</p>
  else if (points.length < 2) body = <p className="muted">Waiting for price history. It appears after the next worker cycle.</p>
  else {
    const values = points.flatMap((p) => [p.close, p.ma20, p.ma100])
    const lo = Math.min(...values)
    const hi = Math.max(...values)
    const pad = (hi - lo) * 0.08 || 1
    const y = (v: number) => H - ((v - (lo - pad)) / (hi - lo + 2 * pad)) * H
    const onMove = (e: PointerEvent<SVGSVGElement>) => {
      const box = e.currentTarget.getBoundingClientRect()
      const ratio = Math.min(1, Math.max(0, (e.clientX - box.left) / box.width))
      setHover(Math.round(ratio * (points.length - 1)))
    }
    const shown = points[hover ?? points.length - 1]
    body = (
      <>
        <div className="readout" aria-live="off">
          {shown.date} · close {usd(shown.close)} · MA20 {usd(shown.ma20)} · MA100 {usd(shown.ma100)}
        </div>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          role="img"
          aria-label={`${symbol} price with 20 and 100 day moving averages over ${points.length} days`}
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
        >
          {[0.2, 0.4, 0.6, 0.8].map((f) => (
            <line key={f} x1="0" x2={W} y1={H * f} y2={H * f} stroke="var(--line)" vectorEffect="non-scaling-stroke" />
          ))}
          <path d={path(points, (p) => p.ma100, y)} fill="none" stroke="var(--amber)" strokeWidth="2" opacity="0.8" vectorEffect="non-scaling-stroke" />
          <path d={path(points, (p) => p.ma20, y)} fill="none" stroke="var(--cyan)" strokeWidth="2" opacity="0.9" vectorEffect="non-scaling-stroke" />
          <path d={path(points, (p) => p.close, y)} fill="none" stroke="var(--text)" strokeWidth="2.5" vectorEffect="non-scaling-stroke" />
          {hover !== null && (
            <line x1={(hover / (points.length - 1)) * W} x2={(hover / (points.length - 1)) * W} y1="0" y2={H} stroke="var(--dim)" vectorEffect="non-scaling-stroke" />
          )}
        </svg>
      </>
    )
  }

  return (
    <section className="panel chart" aria-label={`${symbol} price chart`}>
      <div className="head">
        <h2>Price — {symbol} <span className="muted">60D</span></h2>
        <div className="legend">
          <span><i style={{ background: 'var(--text)' }} />PRICE</span>
          <span><i style={{ background: 'var(--cyan)' }} />MA20</span>
          <span><i style={{ background: 'var(--amber)' }} />MA100</span>
        </div>
      </div>
      {body}
    </section>
  )
}
