import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { addTicker, fetchWatchlist } from './lib/api'

const BAND_COLOR: Record<string, string> = {
  'Strong Buy': '#15803d',
  Buy: '#16a34a',
  Hold: '#6b7280',
  Sell: '#dc2626',
  'Strong Sell': '#991b1b',
}

const fmt = (n: number) => (n >= 0 ? '+' : '') + n.toFixed(1)

export default function App() {
  const client = useQueryClient()
  const [symbol, setSymbol] = useState('')
  const watchlist = useQuery({
    queryKey: ['watchlist'],
    queryFn: fetchWatchlist,
    refetchInterval: 60_000,
  })
  const add = useMutation({
    mutationFn: addTicker,
    onSuccess: () => {
      setSymbol('')
      return client.invalidateQueries({ queryKey: ['watchlist'] })
    },
  })

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (symbol.trim()) add.mutate(symbol.trim())
  }

  return (
    <main>
      <h1>MarketPulse</h1>
      <p className="note">
        Algorithmic signal, not personalized financial advice. Scores update on the worker cycle
        (every 30 minutes during market hours).
      </p>

      <form onSubmit={onSubmit}>
        <input
          aria-label="Ticker symbol"
          placeholder="Add ticker, e.g. NVDA"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          maxLength={16}
        />
        <button type="submit" disabled={add.isPending}>
          Add
        </button>
        {add.isError && <span role="alert" className="error">{add.error.message}</span>}
      </form>

      {watchlist.isPending && <p>Loading…</p>}
      {watchlist.isError && <p role="alert" className="error">{watchlist.error.message}</p>}
      {watchlist.data && (
        <table>
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Score</th>
              <th>Band</th>
              <th title="20d vs 100d moving-average gap, −20…+20">Trend</th>
              <th title="RSI mean-reversion, oversold up / overbought down">Reversion</th>
              <th title="20d return vs benchmark, −15…+15">Rel. strength</th>
              <th title="Annualized volatility penalty, 0…15 (subtracted)">Vol penalty</th>
              <th>As of</th>
            </tr>
          </thead>
          <tbody>
            {watchlist.data.map(({ symbol, benchmark_symbol, score }) => (
              <tr key={symbol}>
                <td>
                  {symbol} <small>vs {benchmark_symbol}</small>
                </td>
                {score ? (
                  <>
                    <td>{score.composite.toFixed(1)}</td>
                    <td style={{ color: BAND_COLOR[score.band], fontWeight: 600 }}>{score.band}</td>
                    <td>{fmt(score.trend)}</td>
                    <td>{fmt(score.reversion)}</td>
                    <td>{fmt(score.rel_strength)}</td>
                    <td>{score.vol_penalty > 0 ? '−' : ''}{score.vol_penalty.toFixed(1)}</td>
                    <td>{new Date(score.as_of + 'Z').toLocaleString()}</td>
                  </>
                ) : (
                  <td colSpan={7}>waiting for the next worker cycle</td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  )
}
