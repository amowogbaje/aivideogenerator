import { useRef, useState } from 'react'
import { api } from '../api'
import type { Voice } from '../types'

/** Voice profile dropdown + a ▶ button that synthesises a short sample with the provider currently configured. */
export function VoicePicker(props: {
  voices: Voice[]
  value: string | null
  onChange: (id: string) => void
  disabled?: boolean
  sample?: string
}) {
  const audio = useRef<HTMLAudioElement | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const play = async () => {
    if (!props.value) return
    setLoading(true); setErr(null)
    try {
      const r = await api.previewVoice(props.value, props.sample)
      audio.current?.pause()
      audio.current = new Audio(r.url)
      await audio.current.play()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="voice-picker">
      <div className="row">
        <select value={props.value ?? ''} disabled={props.disabled} onChange={(e) => props.onChange(e.target.value)}>
          {props.voices.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
        </select>
        <button type="button" className="btn small" onClick={play} disabled={loading || !props.value} title="Hear this voice">
          {loading ? '…' : '▶ Preview'}
        </button>
      </div>
      {err && <div className="error small">{err}</div>}
    </div>
  )
}
