import { useEffect, useState } from 'react'
import { api } from '../api'
import { useAction } from '../hooks'
import type { Asset, Scene } from '../types'
import { CorrectionDialog } from './CorrectionDialog'

export function SceneCard({ scene, characters, aspect, editable, onChanged }: {
  scene: Scene
  characters: Asset[]
  aspect: string
  editable: boolean
  onChanged: () => void
}) {
  const [text, setText] = useState(scene.narration_text)
  const [fixOpen, setFixOpen] = useState(false)
  const act = useAction()
  useEffect(() => setText(scene.narration_text), [scene.narration_text])

  const generating = scene.image_status === 'generating'
  const dirty = text.trim() !== scene.narration_text

  const saveText = () => act.run(async () => { await api.updateScene(scene.id, { narration_text: text }); onChanged() })
  const setSpeaker = (v: string) => act.run(async () => {
    await api.updateScene(scene.id, { speaker_asset_id: v ? Number(v) : null }); onChanged()
  })
  const regenerate = (correction?: string) => act.run(async () => {
    await api.regenerateScene(scene.id, correction); setFixOpen(false); onChanged()
  })

  return (
    <div className="card scene">
      <div className="frame" style={{ aspectRatio: aspect.replace(':', '/') }}>
        {scene.image_url && !generating ? <img src={scene.image_url} alt={`Scene ${scene.number}`} /> : (
          <div className="spinner-box">
            {generating ? <><div className="spinner" /><span>{scene.correction_pending ? 'Regenerating with your fix…' : 'Generating…'}</span></>
                        : <span>{scene.image_status === 'failed' ? 'Failed' : 'Waiting'}</span>}
          </div>
        )}
        <span className="badge kind">Scene {scene.number}</span>
      </div>
      <div className="body">
        <div className="chips">
          {scene.environment && <span className="chip env">📍 {scene.environment.name}</span>}
          {scene.characters.map((c) => <span key={c.id} className="chip char">🧑 {c.name}</span>)}
          {scene.props.map((p) => <span key={p.id} className="chip prop">🔹 {p.name}</span>)}
        </div>

        <label className="small muted">Spoken by</label>
        <select value={scene.speaker?.id ?? ''} disabled={!editable || act.busy} onChange={(e) => setSpeaker(e.target.value)}>
          <option value="">Narrator</option>
          {characters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>

        <label className="small muted">Narration / dialogue (becomes the voice and the captions)</label>
        <textarea rows={3} value={text} disabled={!editable} onChange={(e) => setText(e.target.value)} />

        {scene.last_error && <div className="error small" title={scene.last_error}>⚠ {scene.last_error.slice(0, 160)}</div>}
        {act.error && <div className="error small">{act.error}</div>}
        <div className="row wrap">
          {dirty && editable && <button className="btn primary small" disabled={act.busy} onClick={saveText}>Save text</button>}
          <span className="spacer" />
          <button className="btn small" disabled={!editable || generating || act.busy} onClick={() => setFixOpen(true)}
                  title="Image not right? Describe the problem and generate a new one.">Fix image…</button>
        </div>
      </div>
      <CorrectionDialog open={fixOpen} busy={act.busy} title={`Fix scene ${scene.number}'s image`}
                        onCancel={() => setFixOpen(false)} onSubmit={(c) => regenerate(c)} />
    </div>
  )
}
