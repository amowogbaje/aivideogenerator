import type { EpisodeStatus } from '../types'

const STEPS = ['Script', 'Review cast & places', 'Scene images', 'Render video', 'Done']

function stepIndex(s: EpisodeStatus, failedStage: string | null): number {
  const key = s === 'failed' ? failedStage ?? 'draft' : s
  switch (key) {
    case 'draft': case 'analyzing': return 0
    case 'review': return 1
    case 'planning': case 'imaging': case 'scenes_ready': return 2
    case 'rendering': return 3
    case 'completed': return 4
    default: return 0
  }
}

const BUSY: EpisodeStatus[] = ['analyzing', 'planning', 'imaging', 'rendering']

export function Stepper({ status, failedStage }: { status: EpisodeStatus; failedStage: string | null }) {
  const cur = stepIndex(status, failedStage)
  return (
    <ol className="stepper">
      {STEPS.map((label, i) => {
        const state = i < cur || status === 'completed' ? 'done' : i === cur ? (status === 'failed' ? 'failed' : BUSY.includes(status) ? 'busy' : 'current') : 'todo'
        return <li key={label} className={state}><span className="dot">{state === 'done' ? '✓' : i + 1}</span>{label}</li>
      })}
    </ol>
  )
}

export function StatusPill({ status }: { status: EpisodeStatus }) {
  const label: Record<EpisodeStatus, string> = {
    draft: 'Draft', analyzing: 'Analyzing…', review: 'Needs review', planning: 'Planning…', imaging: 'Generating images…',
    scenes_ready: 'Scenes ready', rendering: 'Rendering…', completed: 'Completed', failed: 'Failed',
  }
  return <span className={`pill ${status}`}>{label[status]}</span>
}
