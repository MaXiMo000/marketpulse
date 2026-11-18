export const BAND_COLOR: Record<string, string> = {
  'Strong Buy': '#15803d',
  Buy: '#16a34a',
  Hold: '#6b7280',
  Sell: '#dc2626',
  'Strong Sell': '#991b1b',
}

export const GAIN = '#15803d'
export const LOSS = '#b91c1c'

export const signed = (n: number) => (n >= 0 ? '+' : '−') + Math.abs(n).toFixed(1)

export const usd = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

const cents = (n: number) => Math.round(n * 100) / 100

export const signedUsd = (n: number) => (cents(n) >= 0 ? '+' : '−') + usd(Math.abs(cents(n)))

export const pnlColor = (n: number) => (cents(n) > 0 ? GAIN : cents(n) < 0 ? LOSS : undefined)

export const BINDING_LABEL: Record<string, string> = {
  tier: 'tier cap',
  risk: 'risk limit',
  cash: 'available cash',
}
