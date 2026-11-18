import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { acknowledgeLive, backToPaper, type Portfolio } from '../lib/api'
import { utc } from '../lib/format'

interface Props {
  portfolio: Portfolio
  open: boolean
  onClose: () => void
}

export default function LiveGate({ portfolio, open, onClose }: Props) {
  const client = useQueryClient()
  const ref = useRef<HTMLDialogElement>(null)
  const [understood, setUnderstood] = useState(false)
  const isLive = portfolio.mode === 'live'

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  const handleClose = () => {
    setUnderstood(false)
    onClose()
  }

  const switchMode = useMutation({
    mutationFn: () => (isLive ? backToPaper(portfolio.id) : acknowledgeLive(portfolio.id)),
    onSuccess: async () => {
      await client.invalidateQueries()
      onClose()
    },
  })

  return (
    <dialog ref={ref} onClose={handleClose} aria-labelledby="gate-title">
      {isLive ? (
        <>
          <h3 id="gate-title">Live mode is on</h3>
          <p>
            Acknowledged{portfolio.live_ack_at ? ` on ${utc(portfolio.live_ack_at).toLocaleString()}` : ''}. Returning to paper mode
            clears the acknowledgement; going live again needs a fresh one.
          </p>
        </>
      ) : (
        <>
          <h3 id="gate-title">Switch to live mode</h3>
          <p>
            Live mode shows sized plans you can act on with real money. MarketPulse does not place orders, and paper-trading results
            do not predict live results.
          </p>
          <p>
            The score is an algorithmic signal, not personalized financial advice. It can be wrong, strategies of this kind can lose
            money in sideways markets, and you alone are responsible for any trade you make.
          </p>
          <label className="check">
            <input type="checkbox" checked={understood} onChange={(e) => setUnderstood(e.target.checked)} />
            <span>I have read this. I understand the score is not financial advice and that I can lose money.</span>
          </label>
        </>
      )}
      {switchMode.isError && <p role="alert" className="error">{switchMode.error.message}</p>}
      <div className="actions">
        <button type="button" className="btn ghost" onClick={handleClose}>Cancel</button>
        <button
          type="button"
          className={isLive ? 'btn' : 'btn danger'}
          disabled={switchMode.isPending || (!isLive && !understood)}
          onClick={() => switchMode.mutate()}
        >
          {isLive ? 'Return to paper mode' : 'Enable live mode'}
        </button>
      </div>
    </dialog>
  )
}
