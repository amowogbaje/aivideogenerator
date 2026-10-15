import { Link, Route, Routes } from 'react-router-dom'
import { useConfig } from './hooks'
import EpisodePage from './pages/EpisodePage'
import SeriesListPage from './pages/SeriesListPage'
import SeriesPage from './pages/SeriesPage'

export default function App() {
  const cfg = useConfig()
  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand">🎬 AI Story Studio</Link>
        {cfg && (
          <span className="muted small" title="Providers currently in use">
            text: {cfg.providers.text} · images: {cfg.providers.image} · voice: {cfg.providers.voice}
          </span>
        )}
      </header>
      {cfg?.placeholder_mode && (
        <div className="banner">
          Demo providers are active (placeholder images / robotic offline voices / rule-based analysis). Add API keys to
          <code> backend/.env</code> for real output — the workflow is identical.
        </div>
      )}
      {cfg && !cfg.ffmpeg && <div className="banner error-banner">ffmpeg was not found on the server — videos can't be rendered.</div>}
      <main className="container">
        <Routes>
          <Route path="/" element={<SeriesListPage />} />
          <Route path="/series/:id" element={<SeriesPage />} />
          <Route path="/episodes/:id" element={<EpisodePage />} />
          <Route path="*" element={<p>Not found. <Link to="/">Home</Link></p>} />
        </Routes>
      </main>
    </>
  )
}
