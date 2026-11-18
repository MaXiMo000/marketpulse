import type { TodayRow } from '../lib/api'
import { bandColor } from '../lib/hud'

interface Props {
  rows: TodayRow[]
  selected: string | null
  onSelect: (symbol: string) => void
}

export default function ChipRail({ rows, selected, onSelect }: Props) {
  return (
    <div className="rail" role="group" aria-label="Select a ticker">
      {rows.map(({ symbol, score }) => (
        <button
          key={symbol}
          type="button"
          className="chip"
          aria-pressed={symbol === selected}
          aria-label={score ? `${symbol}, ${score.band}, score ${score.composite.toFixed(0)}` : `${symbol}, no score yet`}
          onClick={() => onSelect(symbol)}
        >
          <span className="sym">{symbol}</span>
          {score ? (
            <>
              <span className="score" style={{ color: bandColor(score.band) }}>{score.composite.toFixed(0)}</span>
              <span className="meta">{score.band}</span>
            </>
          ) : (
            <span className="meta">awaiting intel</span>
          )}
        </button>
      ))}
    </div>
  )
}
