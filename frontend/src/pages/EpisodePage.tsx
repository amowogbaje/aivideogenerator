import { FormEvent, useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import { AssetCard } from '../components/AssetCard'
import { SceneCard } from '../components/SceneCard'
import { Stepper, StatusPill } from '../components/Stepper'
import { useAction, useConfig, useLoader } from '../hooks'
import type { AssetKind, Episode } from '../types'

const BUSY = ['analyzing', 'planning', 'imaging', 'rendering']
const KINDS: { kind: AssetKind; label: string; hint: string }[] = [
  { kind: 'character', label: 'Characters', hint: 'Check the look and listen to the voice.' },
  { kind: 'environment', label: 'Environments', hint: 'The places your scenes happen in.' },
  { kind: 'prop', label: 'Props', hint: 'Objects that matter visually.' },
]

export default function EpisodePage() {
  const id = Number(useParams().id)
  const nav = useNavigate()
  const cfg = useConfig()
  const keepPolling = useCallback(
    (e: Episode) => BUSY.includes(e.status) || !!e.assets?.some((a) => a.image_status === 'generating') || !!e.scenes?.some((s) => s.image_status === 'generating'),
    [],
  )
  const { data: ep, error, reload } = useLoader(() => api.getEpisode(id), keepPolling)
  const act = useAction()
  const [script, setScript] = useState('')
  const [newKind, setNewKind] = useState<AssetKind>('character')
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => { if (ep?.script !== undefined) setScript(ep.script) }, [ep?.script])

  if (error && !ep) return <div className="error">{error}</div>
  if (!ep || !cfg) return <p className="muted">Loading…</p>

  const a = ep.actions
  const assets = ep.assets ?? []
  const scenes = ep.scenes ?? []
  const busy = BUSY.includes(ep.status)
  const hasScenes = scenes.length > 0
  const characters = assets.filter((x) => x.kind === 'character')

  const call = (fn: () => Promise<unknown>) => act.run(async () => { setNotice(null); await fn(); await reload() })

  const saveScript = () => call(() => api.updateEpisode(id, { script }))
  const reanalyze = () => call(async () => { if (script !== ep.script) await api.updateEpisode(id, { script }); await api.analyze(id) })
  const approveAll = () => call(async () => {
    const r = await api.approveAll(id)
    if (r.skipped_without_image.length) setNotice(`Not approved (no image yet): ${r.skipped_without_image.join(', ')}`)
  })
  const produce = () => act.run(async () => {
    try { setNotice(null); await api.produce(id); await reload() } catch (e) {
      // The server is the source of truth for the gate; show exactly what it is waiting on.
      if (e instanceof ApiError && Array.isArray((e.detail as { unapproved?: unknown[] })?.unapproved)) {
        const names = ((e.detail as { unapproved: { name: string }[] }).unapproved).map((u) => u.name).join(', ')
        setNotice(`Still waiting for your approval: ${names}`); await reload()
      } else throw e
    }
  })
  const addAsset = (e: FormEvent) => {
    e.preventDefault()
    void call(async () => {
      await api.createAsset(ep.series_id, { kind: newKind, name: newName, description: newDesc, episode_id: id })
      setNewName(''); setNewDesc('')
    })
  }
  const remove = () => {
    if (!confirm('Delete this episode?')) return
    void act.run(async () => { await api.deleteEpisode(id); nav(`/series/${ep.series_id}`) })
  }

  const pendingNames = ep.blocking_assets

  return (
    <>
      <p><Link to={`/series/${ep.series_id}`}>← Back to series</Link></p>
      <div className="row wrap">
        <h1 className="grow">Ep {ep.number}: {ep.title}</h1>
        <StatusPill status={ep.status} />
      </div>
      <Stepper status={ep.status} failedStage={ep.failed_stage} />

      {busy && (
        <div className="banner busy"><div className="spinner small" /> {ep.progress_note ?? 'Working…'}</div>
      )}
      {ep.status === 'failed' && (
        <div className="banner error-banner">
          <strong>Something went wrong{ep.failed_stage ? ` during ${ep.failed_stage}` : ''}.</strong>
          <div className="small pre">{ep.error}</div>
          <div className="row">
            {a.retry && <button className="btn primary small" disabled={act.busy} onClick={() => call(() => api.retry(id))}>Retry (keeps finished work)</button>}
            {a.reset && <button className="btn small" disabled={act.busy} onClick={() => call(() => api.reset(id))}>Reset scenes</button>}
          </div>
        </div>
      )}
      {act.error && <div className="error">{act.error}</div>}
      {notice && <div className="banner">{notice}</div>}

      {/* 1 ───────────── script */}
      <section>
        <h2>1 · Script</h2>
        <textarea rows={8} value={script} disabled={!a.edit_script} onChange={(e) => setScript(e.target.value)} />
        <div className="row">
          {a.edit_script && script !== ep.script && <button className="btn small" disabled={act.busy} onClick={saveScript}>Save script</button>}
          {a.analyze && (
            <button className="btn small" disabled={act.busy} onClick={reanalyze}>
              {ep.status === 'draft' ? 'Analyze script' : 'Re-analyze script'}
            </button>
          )}
          {!a.edit_script && hasScenes && <span className="muted small">Scenes exist — use “Reset scenes” to change the script.</span>}
          <span className="spacer" />
          {!busy && <button className="btn small danger" onClick={remove}>Delete episode</button>}
        </div>
      </section>

      {/* 2 ───────────── review gate */}
      {(assets.length > 0 || ep.status === 'review') && (
        <section>
          <div className="row wrap">
            <h2 className="grow">2 · Review cast, places & props</h2>
            <span className="chip">{ep.asset_approved}/{ep.asset_total} approved</span>
            {!hasScenes && pendingNames.length > 0 && !busy && (
              <button className="btn small" disabled={act.busy} onClick={approveAll}>Approve all</button>
            )}
          </div>
          <p className="muted">
            Nothing is turned into scene images until you approve every item. Edit a description, fix a bad image, change a character's voice — approving locks in exactly what you see.
          </p>
          {KINDS.map(({ kind, label, hint }) => {
            const list = assets.filter((x) => x.kind === kind)
            if (!list.length) return null
            return (
              <div key={kind}>
                <h3>{label} <span className="muted small">{hint}</span></h3>
                <div className="grid cols-3">
                  {list.map((x) => <AssetCard key={x.id} asset={x} voices={cfg.voices} locked={busy || hasScenes} onChanged={reload} />)}
                </div>
              </div>
            )
          })}
          {!hasScenes && !busy && (
            <form className="card form inline" onSubmit={addAsset}>
              <div className="body">
                <strong>Missing something?</strong>
                <div className="row wrap">
                  <select value={newKind} onChange={(e) => setNewKind(e.target.value as AssetKind)}>
                    <option value="character">Character</option><option value="environment">Environment</option><option value="prop">Prop</option>
                  </select>
                  <input required placeholder="Name" value={newName} onChange={(e) => setNewName(e.target.value)} />
                  <input className="grow" placeholder="How does it look?" value={newDesc} onChange={(e) => setNewDesc(e.target.value)} />
                  <button className="btn small" disabled={act.busy || !newName.trim()}>Add & generate image</button>
                </div>
              </div>
            </form>
          )}
          {!hasScenes && ep.status === 'review' && (
            <div className="cta">
              <button className="btn primary big" disabled={act.busy || !a.produce} onClick={produce}>
                Generate scene images →
              </button>
              {!a.produce && pendingNames.length > 0 && <span className="muted"> Approve {pendingNames.length} more: {pendingNames.join(', ')}</span>}
            </div>
          )}
        </section>
      )}

      {/* 3 ───────────── scenes */}
      {hasScenes && (
        <section>
          <div className="row wrap">
            <h2 className="grow">3 · Scene images</h2>
            {a.reset && <button className="btn small" disabled={act.busy} onClick={() => confirm('Discard all scenes, audio and the video?') && call(() => api.reset(id))}>Reset scenes</button>}
          </div>
          <p className="muted">Anything off? Use “Fix image…” on a scene and describe the problem. You can also edit what a scene says and who says it.</p>
          <div className="grid cols-4">
            {scenes.map((s) => (
              <SceneCard key={s.id} scene={s} characters={characters} aspect={ep.aspect_ratio}
                         editable={a.edit_scenes} onChanged={reload} />
            ))}
          </div>
        </section>
      )}

      {/* 4 ───────────── render */}
      {(ep.status === 'scenes_ready' || ep.status === 'rendering' || ep.status === 'completed' || (ep.status === 'failed' && ep.failed_stage === 'rendering')) && (
        <section>
          <h2>4 · Voice, captions & video</h2>
          {ep.status !== 'completed' && (
            <div className="cta">
              <button className="btn primary big" disabled={act.busy || !a.render} onClick={() => call(() => api.render(id))}>
                Render video →
              </button>
              {ep.status === 'scenes_ready' && !a.render && <span className="muted"> Waiting for scene images to finish.</span>}
            </div>
          )}
          {ep.video_url && (
            <div className="player">
              <video src={ep.video_url} controls style={{ maxHeight: '70vh', maxWidth: '100%' }} />
              <div className="row">
                <a className="btn primary small" href={ep.video_url} download={`episode-${ep.number}.mp4`}>Download MP4</a>
                {ep.duration_seconds && <span className="muted small">{Math.round(ep.duration_seconds)}s</span>}
                <span className="muted small">Changed your mind about a scene? Fix it above and render again.</span>
              </div>
            </div>
          )}
        </section>
      )}
    </>
  )
}
