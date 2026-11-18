import { useState, type FormEvent } from 'react'
import { setToken, useRejected } from '../lib/auth'
import Logo from './Logo'

export default function Login() {
  const rejected = useRejected()
  const [value, setValue] = useState('')

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (value.trim()) setToken(value.trim())
  }

  return (
    <main className="setup">
      <Logo />
      <h2>Command deck locked</h2>
      <p className="muted">Enter the access token configured for this server. It is kept only for this browser tab.</p>
      <form onSubmit={onSubmit}>
        <label>
          Access token
          <input
            type="password"
            autoComplete="off"
            spellCheck={false}
            required
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        </label>
        <div className="inline">
          <button type="submit" className="btn">Unlock</button>
          {rejected && <span role="alert" className="error">That token was not accepted.</span>}
        </div>
      </form>
    </main>
  )
}
