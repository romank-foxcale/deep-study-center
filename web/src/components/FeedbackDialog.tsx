import { useState } from 'react'
import { FEEDBACK_TAGS } from '../store'

interface Props {
  target: string
  onSubmit: (tags: string[], text: string) => void
  onClose: () => void
}

export default function FeedbackDialog({ target, onSubmit, onClose }: Props) {
  const [tags, setTags] = useState<string[]>([])
  const [text, setText] = useState('')
  const toggle = (id: string) => setTags(t => t.includes(id) ? t.filter(x => x !== id) : [...t, id])
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-label="Feedback" onClick={e => e.stopPropagation()}>
        <h3>Feedback on {target}</h3>
        <p className="muted">Anything goes: it's logged, changes how future (and past) lessons are written for you, and can reshape the roadmap.</p>
        <div className="chips">
          {FEEDBACK_TAGS.map(t => (
            <button key={t.id} className={`chip ${tags.includes(t.id) ? 'on' : ''}`} onClick={() => toggle(t.id)}>{t.label}</button>
          ))}
        </div>
        <textarea className="input" rows={4} placeholder="In your words (optional): what worked, what didn't, what you wish it did…"
          value={text} onChange={e => setText(e.target.value)} />
        <div className="row row-end">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={!tags.length && !text.trim()} onClick={() => onSubmit(tags, text)}>Send feedback</button>
        </div>
      </div>
    </div>
  )
}
