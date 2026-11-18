import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import CreatePortfolio from './components/CreatePortfolio'
import Ledger from './components/Ledger'
import TodayTable from './components/TodayTable'
import WatchlistTable from './components/WatchlistTable'
import { addTicker, fetchPortfolios } from './lib/api'
import { usd } from './lib/format'

function AddTicker() {
  const client = useQueryClient()
  const [symbol, setSymbol] = useState('')
  const add = useMutation({
    mutationFn: addTicker,
    onSuccess: () => {
      setSymbol('')
      return client.invalidateQueries()
    },
  })

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (symbol.trim()) add.mutate(symbol.trim())
  }

  return (
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
  )
}

export default function App() {
  const portfolios = useQuery({ queryKey: ['portfolios'], queryFn: fetchPortfolios, refetchInterval: 60_000 })
  const portfolio = portfolios.data?.[0]

  return (
    <main>
      <h1>MarketPulse</h1>
      <p className="note">
        Algorithmic signal, not personalized financial advice. Scores and paper positions update on the worker
        cycle (every 30 minutes during market hours); paper fills use the latest daily close.
      </p>

      <AddTicker />

      {portfolios.isError && <p role="alert" className="error">{portfolios.error.message}</p>}
      {portfolios.data && !portfolio && (
        <>
          <CreatePortfolio />
          <WatchlistTable />
        </>
      )}
      {portfolio && (
        <>
          <p className="panel">
            <span className="badge">{portfolio.mode.toUpperCase()}</span>
            <strong>{portfolio.risk_tier}</strong> · capital {usd(portfolio.total_value)} · cash {usd(portfolio.cash)}
          </p>
          <h2>Today</h2>
          <TodayTable portfolioId={portfolio.id} />
          <h2>Ledger</h2>
          <Ledger portfolioId={portfolio.id} />
        </>
      )}
    </main>
  )
}
