import { Component, lazy, Suspense, useState, type ReactNode } from 'react'
import type { TerrainBar } from './TerrainScene'

const TerrainScene = lazy(() => import('./TerrainScene'))

class Boundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? (
      <div className="empty">The 3D skyline could not start on this device. Use the ticker chips below.</div>
    ) : (
      this.props.children
    )
  }
}

interface Props {
  bars: TerrainBar[]
  selected: string | null
  pulsing: Set<string>
}

export default function Terrain({ bars, selected, pulsing }: Props) {
  const [animate] = useState(() => !window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const summary = bars.map((b) => `${b.symbol} ${b.band} ${b.score.toFixed(0)}`).join(', ')

  return (
    <div className="terrain" role="img" aria-label={`Skyline of ${bars.length} tickers by score. ${summary}`}>
      {bars.length === 0 ? (
        <div className="empty">Add a ticker to raise the first building.</div>
      ) : (
        <Boundary>
          <Suspense fallback={<div className="empty">Loading skyline…</div>}>
            <TerrainScene bars={bars} selected={selected} pulsing={pulsing} animate={animate} />
          </Suspense>
        </Boundary>
      )}
    </div>
  )
}
