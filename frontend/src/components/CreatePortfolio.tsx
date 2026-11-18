import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { createPortfolio, type RiskTier } from '../lib/api'

const TIERS: { value: RiskTier; label: string }[] = [
  { value: 'conservative', label: 'Conservative — 0.5% risk per trade, 3% max per position' },
  { value: 'moderate', label: 'Moderate — 1% risk per trade, 6% max per position' },
  { value: 'aggressive', label: 'Aggressive — 2% risk per trade, 10% max per position' },
]

export default function CreatePortfolio() {
  const client = useQueryClient()
  const [value, setValue] = useState('10000')
  const [tier, setTier] = useState<RiskTier>('moderate')
  const create = useMutation({
    mutationFn: () => createPortfolio(Number(value), tier),
    onSuccess: () => client.invalidateQueries({ queryKey: ['portfolios'] }),
  })

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    create.mutate()
  }

  return (
    <form onSubmit={onSubmit} className="panel">
      <strong>Create a paper portfolio</strong>
      <label>
        Capital (USD)
        <input type="number" min="1" step="any" required value={value} onChange={(e) => setValue(e.target.value)} />
      </label>
      <label>
        Risk tier
        <select value={tier} onChange={(e) => setTier(e.target.value as RiskTier)}>
          {TIERS.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </label>
      <button type="submit" disabled={create.isPending}>Create</button>
      {create.isError && <span role="alert" className="error">{create.error.message}</span>}
    </form>
  )
}
