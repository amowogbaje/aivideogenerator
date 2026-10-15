import { FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { VoicePicker } from '../components/VoicePicker'
import { useAction, useConfig, useLoader } from '../hooks'

export default function SeriesListPage() {
  const nav = useNavigate()
  const cfg = useConfig()
  const { data, error } = useLoader(api.listSeries)
  const act = useAction()
  const [title, setTitle] = useState('')
  const [premise, setPremise] = useState('')
  const [style, setStyle] = useState('Cinematic digital illustration, rich lighting')
  const [aspect, setAspect] = useState('9:16')
  const [narrator, setNarrator] = useState('narrator_male')

  const create = (e: FormEvent) => {
    e.preventDefault()
    void act.run(async () => {
      const s = await api.createSeries({ title, premise, art_style: style, aspect_ratio: aspect, narrator_voice: narrator })
      nav(`/series/${s.id}`)
    })
  }

  return (
    <>
      <h1>Your series</h1>
      {error && <div className="error">{error}</div>}
      <div className="grid cols-3">
        {data?.map((s) => (
          <Link key={s.id} to={`/series/${s.id}`} className="card link-card">
            <div className="body">
              <h3>{s.title}</h3>
              <p className="muted clamp">{s.premise || 'No premise yet'}</p>
              <div className="chips">
                <span className="chip">{s.episode_count ?? 0} episodes</span>
                <span className="chip">{s.asset_counts?.approved ?? 0}/{s.asset_counts?.total ?? 0} assets approved</span>
                <span className="chip">{s.aspect_ratio}</span>
              </div>
            </div>
          </Link>
        ))}
        {data?.length === 0 && <p className="muted">No series yet — create your first one below.</p>}
      </div>

      <form className="card form" onSubmit={create}>
        <div className="body">
          <h2>Start a new series</h2>
          <label htmlFor="s-title">Title</label>
          <input id="s-title" required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="The Lighthouse Keepers" />
          <label htmlFor="s-premise">Premise <span className="muted">(helps the AI describe your cast and places)</span></label>
          <textarea id="s-premise" rows={3} value={premise} onChange={(e) => setPremise(e.target.value)} placeholder="Two siblings inherit a lighthouse on the Lagos lagoon…" />
          <label htmlFor="s-style">Art style <span className="muted">(applied to every image in the series)</span></label>
          <input id="s-style" value={style} onChange={(e) => setStyle(e.target.value)} />
          <div className="row wrap">
            <div>
              <label htmlFor="s-aspect">Format</label>
              <select id="s-aspect" value={aspect} onChange={(e) => setAspect(e.target.value)}>
                {(cfg?.aspect_ratios ?? ['9:16', '16:9']).map((a) => <option key={a} value={a}>{a === '9:16' ? '9:16 vertical (Shorts / Reels / TikTok)' : '16:9 horizontal (YouTube)'}</option>)}
              </select>
            </div>
            <div className="grow">
              <label>Narrator voice</label>
              {cfg && <VoicePicker voices={cfg.voices} value={narrator} onChange={setNarrator} />}
            </div>
          </div>
          {act.error && <div className="error">{act.error}</div>}
          <button className="btn primary" disabled={act.busy || !title.trim()}>{act.busy ? 'Creating…' : 'Create series'}</button>
        </div>
      </form>
    </>
  )
}
