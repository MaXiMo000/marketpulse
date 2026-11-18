import { useSyncExternalStore } from 'react'

// The token lives in sessionStorage: it survives a reload but not closing the tab, and is never written to disk by the app.
const KEY = 'mp-token'

let memory: string | null = null // used when storage is unavailable
let rejected = false
const listeners = new Set<() => void>()
const emit = () => listeners.forEach((l) => l())

export class AuthError extends Error {
  constructor() {
    super('Authentication required')
  }
}

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(KEY) ?? memory
  } catch {
    return memory
  }
}

export function setToken(token: string): void {
  memory = token
  rejected = false
  try {
    sessionStorage.setItem(KEY, token)
  } catch {
    /* kept in memory for this page load */
  }
  emit()
}

/** Forget the token. `wasRejected` marks that the server refused it, so the lock screen can say so. */
export function clearToken(wasRejected = false): void {
  memory = null
  if (wasRejected) rejected = true
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    /* nothing to clear */
  }
  emit()
}

export const authHeader = (): Record<string, string> => {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

const subscribe = (cb: () => void) => {
  listeners.add(cb)
  return () => listeners.delete(cb)
}

export const useToken = () => useSyncExternalStore(subscribe, getToken)
export const useRejected = () => useSyncExternalStore(subscribe, () => rejected)
