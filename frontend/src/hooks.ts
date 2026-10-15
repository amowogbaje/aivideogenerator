import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import type { AppConfig } from './types'

/** Loads data, exposes reload(), and re-polls while `keepPolling(data)` is true (e.g. a job is running). */
export function useLoader<T>(load: () => Promise<T>, keepPolling?: (d: T) => boolean, intervalMs = 1500) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const loadRef = useRef(load)
  loadRef.current = load

  const reload = useCallback(async () => {
    try {
      const d = await loadRef.current()
      setData(d)
      setError(null)
      return d
    } catch (e) {
      setError((e as Error).message)
      return null
    }
  }, [])

  useEffect(() => { void reload() }, [reload])

  useEffect(() => {
    if (!data || !keepPolling?.(data)) return
    const t = setTimeout(() => void reload(), intervalMs)
    return () => clearTimeout(t)
  }, [data, keepPolling, intervalMs, reload])

  return { data, error, reload, setData }
}

export function useConfig() {
  const [cfg, setCfg] = useState<AppConfig | null>(null)
  useEffect(() => { api.config().then(setCfg).catch(() => setCfg(null)) }, [])
  return cfg
}

/** Wraps an async action with a busy flag and an error message the UI can show. */
export function useAction() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const run = useCallback(async <R,>(fn: () => Promise<R>): Promise<R | undefined> => {
    setBusy(true); setError(null)
    try { return await fn() } catch (e) { setError((e as Error).message); return undefined } finally { setBusy(false) }
  }, [])
  return { busy, error, run, clearError: () => setError(null) }
}
