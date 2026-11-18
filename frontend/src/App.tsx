import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import AddTicker from './components/AddTicker'
import AlertBanner from './components/AlertBanner'
import BattleLog from './components/BattleLog'
import ChipRail from './components/ChipRail'
import CreatePortfolio from './components/CreatePortfolio'
import LiveGate from './components/LiveGate'
import Login from './components/Login'
import Logo from './components/Logo'
import MissionBriefing from './components/MissionBriefing'
import PriceChart from './components/PriceChart'
import ProofLab from './components/ProofLab'
import Terrain from './components/Terrain'
import { fetchAlerts, fetchBacktest, fetchPortfolios, fetchPositions, fetchToday, type Portfolio } from './lib/api'
import { AuthError, clearToken, useToken } from './lib/auth'
import { pnlClass, usd, utc } from './lib/format'
import { pulsingSymbols } from './lib/hud'

const REFRESH_MS = 60_000

function Setup() {
  return (
    <main className="setup">
      <Logo />
      <h2>Initialize your command deck</h2>
      <p className="muted">
        Every portfolio starts in paper mode. MarketPulse is an algorithmic signal, not personalized financial advice.
      </p>
      <CreatePortfolio />
      <h2>Watchlist</h2>
      <p className="muted">Add the tickers to track. Scores appear after the next worker cycle.</p>
      <AddTicker />
    </main>
  )
}

function Deck({ portfolio }: { portfolio: Portfolio }) {
  const today = useQuery({ queryKey: ['today', portfolio.id], queryFn: () => fetchToday(portfolio.id), refetchInterval: REFRESH_MS })
  const positions = useQuery({ queryKey: ['positions', portfolio.id], queryFn: () => fetchPositions(portfolio.id), refetchInterval: REFRESH_MS })
  const alerts = useQuery({ queryKey: ['alerts'], queryFn: fetchAlerts, refetchInterval: REFRESH_MS })
  const backtest = useQuery({ queryKey: ['backtest'], queryFn: fetchBacktest })
  const [picked, setPicked] = useState<string | null>(null)
  const [gateOpen, setGateOpen] = useState(false)
  const client = useQueryClient()
  const token = useToken()

  const rows = useMemo(() => today.data ?? [], [today.data])
  const selected = rows.find((r) => r.symbol === picked) ?? rows[0]
  const bars = useMemo(
    () => rows.filter((r) => r.score).map((r) => ({ symbol: r.symbol, score: r.score!.composite, band: r.score!.band })),
    [rows],
  )
  const pulsing = useMemo(() => pulsingSymbols(alerts.data ?? [], rows), [alerts.data, rows])
  const lastCycle = rows.reduce<string | null>((latest, r) => (r.score && (!latest || r.score.as_of > latest) ? r.score.as_of : latest), null)
  const isLive = portfolio.mode === 'live'

  return (
    <>
      <header className="topbar">
        <Logo />
        <div className="status">
          WATCHLIST: <b>{rows.length}</b> TICKERS · LAST CYCLE <b>{lastCycle ? utc(lastCycle).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</b> ·{' '}
          {portfolio.risk_tier.toUpperCase()} · CASH <b>{usd(portfolio.cash)}</b> · DAY{' '}
          <b className={pnlClass(portfolio.day_change)}>{(portfolio.day_change * 100).toFixed(2)}%</b> (BREAKER AT −
          {(portfolio.daily_loss_limit * 100).toFixed(0)}%)
        </div>
        {portfolio.breaker_tripped && (
          <div className="breaker" role="alert">BREAKER TRIPPED: NEW BUYING PAUSED TODAY</div>
        )}
        <button type="button" className={`mode ${isLive ? 'live' : 'paper'}`} onClick={() => setGateOpen(true)} aria-haspopup="dialog">
          <i aria-hidden="true" />
          {isLive ? 'LIVE — ARMED' : 'PAPER MODE'}
        </button>
        {token && (
          <button
            type="button"
            className="btn ghost lock"
            onClick={() => {
              clearToken()
              client.clear()
            }}
          >
            Lock
          </button>
        )}
      </header>

      <AlertBanner alerts={alerts.data ?? []} onSelect={setPicked} />

      <div className="deck">
        <div className="col">
          <section className="panel" aria-label="The Terrain">
            <div className="head">
              <div>
                <h2>The Terrain — signal skyline</h2>
                <div className="sub">height = composite score · color = band · pick a ticker below to brief</div>
              </div>
              <AddTicker />
            </div>
            <Terrain bars={bars} selected={selected?.symbol ?? null} pulsing={pulsing} />
            <ChipRail rows={rows} selected={selected?.symbol ?? null} onSelect={setPicked} />
          </section>
          {selected && <PriceChart symbol={selected.symbol} />}
        </div>

        <div className="col">
          {today.isError && <p role="alert" className="error">{today.error.message}</p>}
          {selected && (
            <MissionBriefing
              row={selected}
              position={positions.data?.positions.find((p) => p.symbol === selected.symbol && p.status !== 'closed')}
              verdict={backtest.data?.result.edge.verdict}
            />
          )}
          {positions.data && <BattleLog data={positions.data} mode={portfolio.mode} />}
        </div>
      </div>

      <div className="deck" style={{ gridTemplateColumns: 'minmax(0, 1fr)', paddingTop: 0 }}>
        <ProofLab />
      </div>

      <LiveGate portfolio={portfolio} open={gateOpen} onClose={() => setGateOpen(false)} />
    </>
  )
}

export default function App() {
  const client = useQueryClient()
  const token = useToken()
  const portfolios = useQuery({ queryKey: ['portfolios'], queryFn: fetchPortfolios, refetchInterval: REFRESH_MS })
  // a new or cleared token means every cached response is stale
  useEffect(() => {
    void client.invalidateQueries()
  }, [client, token])
  if (portfolios.error instanceof AuthError) return <Login />
  if (portfolios.isPending) return <p className="muted" style={{ padding: 24 }}>Loading…</p>
  if (portfolios.isError) return <p role="alert" className="error" style={{ padding: 24 }}>{portfolios.error.message}</p>
  const portfolio = portfolios.data[0]
  return portfolio ? <Deck portfolio={portfolio} /> : <Setup />
}
