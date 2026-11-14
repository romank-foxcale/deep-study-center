import { useState } from 'react'
import { FEEDBACK_TAGS } from '../store'
import type { FeedbackKind } from '../types'
import { KindPicker } from './FeedbackItems'

interface Props {
  target: string
  /** kind undefined = let the agent propose it (you can correct it later in the log). */
  onSubmit: (tags: string[], text: string, kind?: FeedbackKind) => void
  onClose: () => void
}

export default function FeedbackDialog({ target, onSubmit, onClose }: Props) {
  const [tags, setTags] = useState<string[]>([])
  const [text, setText] = useState('')
  const [kind, setKind] = useState<FeedbackKind | 'auto'>('auto')
  const toggle = (id: string) => setTags(t => t.includes(id) ? t.filter(x => x !== id) : [...t, id])
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-label="Feedback" onClick={e => e.stopPropagation()}>
        <h3>Feedback on {target}</h3>
        <p className="muted">Anything goes. It's logged, and you can apply it to this lesson right away from the Feedback log, then compare versions or go back.</p>
        <div className="chips">
          {FEEDBACK_TAGS.map(t => (
            <button key={t.id} className={`chip ${tags.includes(t.id) ? 'on' : ''}`} onClick={() => toggle(t.id)}>{t.label}</button>
          ))}
        </div>
        <textarea className="input" rows={4} placeholder="In your words (optional): what worked, what didn't, what you wish it did…"
          value={text} onChange={e => setText(e.target.value)} />
        <KindPicker value={kind} onChange={setKind} allowAuto={setKind} />
        <div className="row row-end">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={!tags.length && !text.trim()} onClick={() => onSubmit(tags, text, kind === 'auto' ? undefined : kind)}>Send feedback</button>
        </div>
      </div>
    </div>
  )
}
