import { useEffect, useState } from 'react'

const MAX = 1000

/** "This image didn't come out right" — the note is optional (empty = plain regenerate) and applies to one render only. */
export function CorrectionDialog(props: {
  open: boolean
  title: string
  busy: boolean
  onCancel: () => void
  onSubmit: (correction: string) => void
}) {
  const [text, setText] = useState('')
  useEffect(() => { if (props.open) setText('') }, [props.open])
  if (!props.open) return null
  return (
    <div className="modal-backdrop" onClick={props.onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <h3>{props.title}</h3>
        <p className="muted">
          The current image is replaced by a new one. Say what was wrong so the model can fix it — or leave it empty to just try again.
        </p>
        <label htmlFor="fix-note">What needs fixing? (optional)</label>
        <textarea
          id="fix-note"
          autoFocus
          rows={4}
          maxLength={MAX}
          value={text}
          disabled={props.busy}
          placeholder="e.g. Her hands look distorted. There's an extra person in the background. Too dark — make it dawn light."
          onChange={(e) => setText(e.target.value)}
        />
        <div className="muted small right">{text.length}/{MAX}</div>
        <div className="row end">
          <button className="btn" onClick={props.onCancel} disabled={props.busy}>Cancel</button>
          <button className="btn primary" onClick={() => props.onSubmit(text)} disabled={props.busy}>
            {props.busy ? 'Working…' : 'Regenerate'}
          </button>
        </div>
      </div>
    </div>
  )
}
