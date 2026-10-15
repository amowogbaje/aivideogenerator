import { useEffect, useState } from 'react'
import { api } from '../api'
import { useAction } from '../hooks'
import type { Asset, Voice } from '../types'
import { CorrectionDialog } from './CorrectionDialog'
import { VoicePicker } from './VoicePicker'

const KIND_LABEL = { character: 'Character', environment: 'Environment', prop: 'Prop' } as const

/**
 * One reviewable thing: reference image, editable description, (for characters) voice, and Approve.
 * Editing anything un-approves it on the server — approval always refers to exactly what you're looking at.
 */
export function AssetCard({ asset, voices, locked, onChanged, onDeleted }: {
  asset: Asset
  voices: Voice[]
  locked: boolean            // true while the episode is being processed or already has scenes
  onChanged: () => void
  onDeleted?: () => void
}) {
  const [name, setName] = useState(asset.name)
  const [desc, setDesc] = useState(asset.description)
  const [fixOpen, setFixOpen] = useState(false)
  const act = useAction()

  // keep inputs in sync when the server copy changes (e.g. polling)
  useEffect(() => { setName(asset.name); setDesc(asset.description) }, [asset.name, asset.description])

  const dirty = name !== asset.name || desc !== asset.description
  const generating = asset.image_status === 'generating'
  const canApprove = asset.image_status === 'ready' && !dirty && !locked

  const save = () => act.run(async () => { await api.updateAsset(asset.id, { name, description: desc }); onChanged() })
  const setVoice = (v: string) => act.run(async () => { await api.updateAsset(asset.id, { voice_id: v }); onChanged() })
  const regenerate = (correction?: string) => act.run(async () => {
    await api.regenerateAsset(asset.id, correction); setFixOpen(false); onChanged()
  })
  const toggleApproval = () => act.run(async () => {
    await (asset.approved ? api.unapproveAsset(asset.id) : api.approveAsset(asset.id)); onChanged()
  })
  const remove = () => {
    if (!confirm(`Delete ${asset.name}?`)) return
    void act.run(async () => { await api.deleteAsset(asset.id); onDeleted?.(); onChanged() })
  }

  return (
    <div className={`card asset ${asset.approved ? 'approved' : ''}`}>
      <div className={`thumb ${asset.kind}`}>
        {asset.image_url && !generating && <img src={asset.image_url} alt={asset.name} />}
        {generating && <div className="spinner-box"><div className="spinner" /><span>Generating…</span></div>}
        {!asset.image_url && !generating && (
          <div className="spinner-box"><span>{asset.image_status === 'failed' ? 'Generation failed' : 'No image yet'}</span></div>
        )}
        <span className="badge kind">{KIND_LABEL[asset.kind]}</span>
        {asset.approved && <span className="badge ok">✓ Approved</span>}
      </div>

      <div className="body">
        <input value={name} disabled={locked} onChange={(e) => setName(e.target.value)} className="title-input" aria-label="Name" />
        <textarea
          rows={4}
          value={desc}
          disabled={locked}
          onChange={(e) => setDesc(e.target.value)}
          aria-label="Visual description"
          placeholder="Describe how it looks — this text is what keeps it consistent in every scene."
        />
        {asset.kind === 'character' && (
          <VoicePicker voices={voices} value={asset.voice_id} disabled={locked} onChange={setVoice}
                       sample={`Hello, I'm ${asset.name}. This is how I'll sound in the story.`} />
        )}
        {asset.last_error && <div className="error small" title={asset.last_error}>⚠ {asset.last_error.slice(0, 160)}</div>}
        {act.error && <div className="error small">{act.error}</div>}

        <div className="row wrap">
          {dirty && !locked && <button className="btn primary small" disabled={act.busy} onClick={save}>Save changes</button>}
          <button className="btn small" disabled={locked || generating || act.busy} onClick={() => setFixOpen(true)}
                  title="Not right? Say what to fix and generate a new image.">Fix image…</button>
          <button className="btn small" disabled={locked || generating || act.busy} onClick={() => regenerate()}>Regenerate</button>
          {!locked && <button className="btn small danger" disabled={act.busy} onClick={remove}>Delete</button>}
          <span className="spacer" />
          <button className={`btn small ${asset.approved ? '' : 'primary'}`} disabled={act.busy || (!asset.approved && !canApprove) || (asset.approved && locked)}
                  onClick={toggleApproval}
                  title={dirty ? 'Save your changes first' : generating ? 'Wait for the image' : undefined}>
            {asset.approved ? 'Unapprove' : 'Approve'}
          </button>
        </div>
      </div>

      <CorrectionDialog open={fixOpen} busy={act.busy} title={`Fix ${asset.name}'s image`}
                        onCancel={() => setFixOpen(false)} onSubmit={(c) => regenerate(c)} />
    </div>
  )
}
