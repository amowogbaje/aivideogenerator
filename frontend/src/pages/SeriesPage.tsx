import { FormEvent, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { AssetCard } from '../components/AssetCard'
import { StatusPill } from '../components/Stepper'
import { VoicePicker } from '../components/VoicePicker'
import { useAction, useConfig, useLoader } from '../hooks'
import type { Asset, AssetKind } from '../types'

type Tab = 'episodes' | 'bible'
const KINDS: { kind: AssetKind; label: string }[] = [
  { kind: 'character', label: 'Characters' }, { kind: 'environment', label: 'Environments' }, { kind: 'prop', label: 'Props' },
]

export default function SeriesPage() {
  const id = Number(useParams().id)
  const nav = useNavigate()
  const cfg = useConfig()
  const series = useLoader(() => api.getSeries(id))
  const episodes = useLoader(() => api.listEpisodes(id), (list) => list.some((e) => ['analyzing', 'planning', 'imaging', 'rendering'].includes(e.status)), 2000)
  const assets = useLoader(() => api.listAssets(id), (list) => list.some((a) => a.image_status === 'generating'))
  const [tab, setTab] = useState<Tab>('episodes')
  const act = useAction()

  const [title, setTitle] = useState('')
  const [script, setScript] = useState('')

  const addEpisode = (e: FormEvent) => {
    e.preventDefault()
    void act.run(async () => {
      const ep = await api.createEpisode(id, { title, script })
      nav(`/episodes/${ep.id}`)
    })
  }

  const s = series.data
  if (series.error) return <div className="error">{series.error}</div>
  if (!s) return <p className="muted">Loading…</p>

  const refreshAll = () => { void series.reload(); void assets.reload(); void episodes.reload() }
  const remove = () => {
    if (!confirm(`Delete "${s.title}" and everything in it?`)) return
    void act.run(async () => { await api.deleteSeries(id); nav('/') })
  }
  const unlocked = (a: Asset) => !(episodes.data ?? []).some((ep) => ['planning', 'imaging', 'rendering', 'analyzing'].includes(ep.status)) && !!a

  return (
    <>
      <p><Link to="/">← All series</Link></p>
      <div className="row wrap">
        <div className="grow">
          <h1>{s.title}</h1>
          <p className="muted">{s.premise}</p>
          <div className="chips"><span className="chip">{s.aspect_ratio}</span><span className="chip">🎨 {s.art_style}</span></div>
        </div>
        <div>
          <label className="small muted">Narrator</label>
          {cfg && <VoicePicker voices={cfg.voices} value={s.narrator_voice}
            onChange={(v) => void api.updateSeries(id, { narrator_voice: v }).then(() => series.reload())} />}
          <button className="btn small danger" onClick={remove} style={{ marginTop: 8 }}>Delete series</button>
        </div>
      </div>

      <div className="tabs">
        <button className={tab === 'episodes' ? 'active' : ''} onClick={() => setTab('episodes')}>Episodes ({episodes.data?.length ?? 0})</button>
        <button className={tab === 'bible' ? 'active' : ''} onClick={() => setTab('bible')}>
          Story bible ({assets.data?.filter((a) => a.approved).length ?? 0}/{assets.data?.length ?? 0} approved)
        </button>
      </div>

      {tab === 'episodes' && (
        <>
          <div className="list">
            {episodes.data?.map((ep) => (
              <Link key={ep.id} to={`/episodes/${ep.id}`} className="card row link-card pad">
                <strong>Ep {ep.number}</strong>
                <span className="grow">{ep.title}</span>
                {ep.status === 'review' && <span className="chip">{ep.asset_approved}/{ep.asset_total} approved</span>}
                <StatusPill status={ep.status} />
              </Link>
            ))}
            {episodes.data?.length === 0 && <p className="muted">No episodes yet. Paste your first script below.</p>}
          </div>
          <form className="card form" onSubmit={addEpisode}>
            <div className="body">
              <h2>Add an episode</h2>
              <label htmlFor="ep-title">Title</label>
              <input id="ep-title" required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Episode 1 — The Storm" />
              <label htmlFor="ep-script">Script <span className="muted">(the story text; dialogue in "quotes" is voiced by the character)</span></label>
              <textarea id="ep-script" required rows={9} value={script} onChange={(e) => setScript(e.target.value)}
                        placeholder={'Ada walked into the old lighthouse at dawn. She carried a brass lantern.\n"We are late," said Ada.'} />
              {act.error && <div className="error">{act.error}</div>}
              <button className="btn primary" disabled={act.busy || script.trim().length < 10 || !title.trim()}>
                {act.busy ? 'Creating…' : 'Add episode & analyze'}
              </button>
              <span className="muted small"> Then you'll review the cast, places and props before any scene images are made.</span>
            </div>
          </form>
        </>
      )}

      {tab === 'bible' && cfg && (
        <>
          <p className="muted">Everything here is shared by every episode, so characters look and sound the same throughout the series.</p>
          {KINDS.map(({ kind, label }) => {
            const list = assets.data?.filter((a) => a.kind === kind) ?? []
            return (
              <section key={kind}>
                <h2>{label} <span className="muted">({list.length})</span></h2>
                <div className="grid cols-3">
                  {list.map((a) => <AssetCard key={a.id} asset={a} voices={cfg.voices} locked={!unlocked(a)} onChanged={refreshAll} />)}
                </div>
                {list.length === 0 && <p className="muted">None yet — they're extracted when you add an episode.</p>}
              </section>
            )
          })}
        </>
      )}
    </>
  )
}
