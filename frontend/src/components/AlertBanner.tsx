import { useEffect, useState } from 'react'
import type { Alert } from '../lib/api'
import { utc } from '../lib/format'

const STORE = 'mp-dismissed-alerts'
const DAY_MS = 24 * 60 * 60 * 1000

const keyOf = (a: Alert) => `${a.symbol}|${a.computed_at}`

function loadDismissed(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(STORE) ?? '[]'))
  } catch {
    return new Set()
  }
}

/** Current time, refreshed once a minute so the 24h window keeps moving without impure calls in render. */
function useNow(): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60_000)
    return () => clearInterval(id)
  }, [])
  return now
}

export default function AlertBanner({ alerts, onSelect }: { alerts: Alert[]; onSelect: (symbol: string) => void }) {
  const [dismissed, setDismissed] = useState(loadDismissed)
  const now = useNow()
  const fresh = alerts
    .filter((a) => !dismissed.has(keyOf(a)) && now - utc(a.computed_at).getTime() < DAY_MS)
    .slice(0, 3)
  if (fresh.length === 0) return null

  const dismiss = (a: Alert) => {
    const next = new Set(dismissed).add(keyOf(a))
    setDismissed(next)
    try {
      localStorage.setItem(STORE, JSON.stringify([...next].slice(-100)))
    } catch {
      /* storage unavailable: the dismissal lasts until reload */
    }
  }

  return (
    <div role="region" aria-label="Signal flips">
      <div className="hazard" aria-hidden="true" />
      <div className="alerts">
        {fresh.map((a) => (
          <div className="alert" key={keyOf(a)}>
            <span className="siren" aria-hidden="true" />
            <button type="button" className="pick" onClick={() => onSelect(a.symbol)}>
              SIGNAL FLIP — {a.symbol}: {a.from_band} → <span className={a.direction}>{a.to_band}</span> ({a.from_score.toFixed(0)} →{' '}
              {a.to_score.toFixed(0)})
            </button>
            <button type="button" className="dismiss" aria-label={`Dismiss ${a.symbol} alert`} onClick={() => dismiss(a)}>
              Dismiss
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
