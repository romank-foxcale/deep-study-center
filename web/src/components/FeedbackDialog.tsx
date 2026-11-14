import { useState } from 'react'
import { FEEDBACK_TAGS } from '../store'
import type { FeedbackKind, FeedbackRef } from '../types'
import { KindPicker, RefQuote } from './FeedbackItems'

interface Props {
  target: string
  /** The chosen part (selected text, a formula, a graph); without it the feedback is about the target as a whole. */
  reference?: FeedbackRef
  /** kind undefined = let the agent propose it (you can correct it later in the log). */
  onSubmit: (tags: string[], text: string, kind?: FeedbackKind) => void
  onClose: () => void
}

export default function FeedbackDialog({ target, reference, onSubmit, onClose }: Props) {
  const [tags, setTags] = useState<string[]>([])
  const [text, setText] = useState('')
  const [kind, setKind] = useState<FeedbackKind | 'auto'>('auto')
  const toggle = (id: string) => setTags(t => t.includes(id) ? t.filter(x => x !== id) : [...t, id])
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-label="Feedback" onClick={e => e.stopPropagation()}>
        <h3>Feedback on {target}</h3>
        {reference && <RefQuote r={reference} />}
        <p className="muted">
          {reference
            ? 'Applying it changes this part, and other parts only where they are directly relevant or have the same issue.'
            : target === 'this lesson'
              ? 'About the whole lesson: applying it may change any part.'
              : 'About this section: applying it changes this section, and other parts only where they have the same issue.'}
          {' '}You apply it from the Feedback log, then compare versions or go back.</p>
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
