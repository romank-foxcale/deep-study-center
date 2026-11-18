import { useState } from 'react'
import { FEEDBACK_TAGS, WORKED_PARTS } from '../store'
import type { FeedbackKind, FeedbackRef } from '../types'
import { KindPicker, RefQuote } from './FeedbackItems'

interface Props {
  target: string
  /** The chosen part (selected text, a formula, a graph); without it the feedback is about the target as a whole. */
  reference?: FeedbackRef
  /** kind undefined = let the agent propose it (you can correct it later in the log). apply = also apply it now. */
  onSubmit: (tags: string[], text: string, kind: FeedbackKind, apply: boolean, worked: string[]) => void
  onClose: () => void
}

export default function FeedbackDialog({ target, reference, onSubmit, onClose }: Props) {
  const [tags, setTags] = useState<string[]>([])
  const [text, setText] = useState('')
  const [kind, setKind] = useState<FeedbackKind>('lesson')
  const [worked, setWorked] = useState<string[]>([])
  const [confirm, setConfirm] = useState(false)
  const toggle = (id: string) => setTags(t => t.includes(id) ? t.filter(x => x !== id) : [...t, id])
  const empty = !tags.length && !text.trim()
  const submit = (apply: boolean) => onSubmit(tags, text, kind, apply, tags.includes('loved-it') ? worked : [])
  const scope = reference
    ? 'When you apply it, it changes this part. Other parts change only if they have the same problem.'
    : target === 'the whole lesson'
      ? 'When you apply it, it can change any part of the lesson.'
      : 'When you apply it, it changes this section. Other sections change only if they have the same problem.'

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-label="Feedback" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Feedback on {target}</h3>
          {!confirm && <p className="muted">{scope}</p>}
        </div>
        {reference && <RefQuote r={reference} />}
        {confirm ? (
          <>
            <p><strong>Apply this feedback now?</strong></p>
            <p className="muted">An agent writes a new version of this lesson from this feedback only. The current version is
              kept: you can compare the two in the Change log and go back.
              {kind === 'fact' && ' A possible error in the material does not change your lesson: it goes to the fact check of the source card.'}</p>
            <p className="muted small">To apply several pieces of feedback together, click “Add feedback” for each one, then apply
              them from the Feedback log.</p>
            <div className="row row-end">
              <button className="btn" onClick={() => setConfirm(false)}>Back</button>
              <button className="btn btn-primary" onClick={() => submit(true)}>Yes, apply it</button>
            </div>
          </>
        ) : (
          <>
            <div className="chips">
              {FEEDBACK_TAGS.map(t => (
                <button key={t.id} className={`chip ${tags.includes(t.id) ? 'on' : ''}`} onClick={() => toggle(t.id)}>{t.label}</button>
              ))}
            </div>
            {tags.includes('loved-it') && (
              <div className="worked">
                <span className="small"><strong>What worked?</strong> <span className="muted">With “All my future lessons”, this becomes a lesson guideline.</span></span>
                <div className="chips">
                  {WORKED_PARTS.map(w => (
                    <button key={w} className={`chip ${worked.includes(w) ? 'on' : ''}`}
                      onClick={() => setWorked(x => x.includes(w) ? x.filter(y => y !== w) : [...x, w])}>{w}</button>
                  ))}
                </div>
              </div>
            )}
            <textarea className="input" rows={4} placeholder="In your words (optional): what worked, what didn't, what you wish it did…"
              value={text} onChange={e => setText(e.target.value)} />
            <KindPicker value={kind} onChange={setKind} />
            <div className="row row-end">
              <button className="btn" onClick={onClose}>Cancel</button>
              <button className="btn" disabled={empty} onClick={() => submit(false)}
                title="Save it in the Feedback log. Apply it later, alone or with other feedback.">Add feedback</button>
              <button className="btn btn-primary" disabled={empty} onClick={() => setConfirm(true)}
                title="Save it and write a new version of the lesson from it now">Add and apply</button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
