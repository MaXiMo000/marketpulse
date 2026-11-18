import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { addTicker } from '../lib/api'

export default function AddTicker() {
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
    <form onSubmit={onSubmit} className="inline">
      <input
        aria-label="Ticker symbol"
        placeholder="Add ticker, e.g. NVDA"
        value={symbol}
        onChange={(e) => setSymbol(e.target.value)}
        maxLength={16}
      />
      <button type="submit" className="btn ghost" disabled={add.isPending}>Add</button>
      {add.isError && <span role="alert" className="error">{add.error.message}</span>}
    </form>
  )
}
