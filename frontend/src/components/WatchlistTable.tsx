import { useQuery } from '@tanstack/react-query'
import { fetchWatchlist } from '../lib/api'
import { BAND_COLOR, signed } from '../lib/format'

export default function WatchlistTable() {
  const watchlist = useQuery({ queryKey: ['watchlist'], queryFn: fetchWatchlist, refetchInterval: 60_000 })

  if (watchlist.isPending) return <p>Loading…</p>
  if (watchlist.isError) return <p role="alert" className="error">{watchlist.error.message}</p>
  return (
    <div className="scroll">
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
                  <td>{signed(score.trend)}</td>
                  <td>{signed(score.reversion)}</td>
                  <td>{signed(score.rel_strength)}</td>
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
    </div>
  )
}
