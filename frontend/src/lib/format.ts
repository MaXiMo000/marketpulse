export const signed = (n: number) => (n >= 0 ? '+' : '−') + Math.abs(n).toFixed(1)

export const usd = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

// Sub-cent float residue should read as zero, not as a gain or a loss.
const cents = (n: number) => Math.round(n * 100) / 100

export const signedUsd = (n: number) => (cents(n) >= 0 ? '+' : '−') + usd(Math.abs(cents(n)))

export const pnlClass = (n: number) => (cents(n) > 0 ? 'gain' : cents(n) < 0 ? 'loss' : '')

/** Timestamps from the API are UTC but carry no zone suffix. */
export const utc = (iso: string) => new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z')

export const BINDING_LABEL: Record<string, string> = {
  tier: 'tier cap',
  risk: 'risk limit',
  cash: 'available cash',
}
