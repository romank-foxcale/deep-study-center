import { useState } from 'react'
import type { ExplainItem, Grading } from '../types'
import Markdown from './Markdown'

interface Props {
  item: ExplainItem
  grading?: Grading
  inProgress: boolean
  onSubmit: (answer: string) => void
}

const SCORE_LABEL: Record<string, string> = { '1': 'Solid', '0.5': 'Almost', '0': 'Not yet' }

/** Explain-back: the learner's own words, graded against a hidden rubric by an independent grader. */
export default function ExplainBack({ item, grading, inProgress, onSubmit }: Props) {
  const [text, setText] = useState('')
  const [retry, setRetry] = useState(false)
  const showForm = !grading || retry || grading.status === 'ungraded'
  const pending = inProgress || grading?.status === 'pending'

  return (
    <div className="check explain">
      <div className="check-label">Explain it back</div>
      <Markdown>{item.prompt}</Markdown>
      {grading && !retry && (
        <div className="explain-answer">
          <div className="muted small">Your answer</div>
          <p>{grading.answer}</p>
        </div>
      )}
      {pending && <p className="muted">Grading your explanation…</p>}
      {grading?.status === 'graded' && !retry && (
        <div className={`check-result ${grading.score === 1 ? 'ok' : 'bad'}`}>
          <strong>{SCORE_LABEL[String(grading.score)] ?? grading.score}.</strong> {grading.feedback}
          {grading.missing.length > 0 && <div className="small">Missing: {grading.missing.join('; ')}</div>}
          {grading.followup && <div className="small"><em>Think about:</em> {grading.followup}</div>}
        </div>
      )}
      {grading?.status === 'ungraded' && <p className="muted small">{grading.feedback}</p>}
      {grading?.status === 'graded' && !retry && grading.score !== 1 && (
        <button className="btn" onClick={() => { setRetry(true); setText(grading.answer) }}>Try again</button>
      )}
      {showForm && !pending && (
        <>
          <textarea className="input" rows={4} value={text} onChange={e => setText(e.target.value)}
            placeholder="In your own words, as if explaining to a colleague. Pictures-in-words and examples welcome." />
          <button className="btn btn-primary" disabled={text.trim().length < 15}
            onClick={() => { onSubmit(text); setRetry(false) }}>Submit for grading</button>
        </>
      )}
    </div>
  )
}
