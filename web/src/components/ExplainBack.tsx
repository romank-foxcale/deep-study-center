import { useState } from 'react'
import type { ExplainItem, Grading } from '../types'
import Markdown from './Markdown'
import { ConfidenceSlider, DictationArea } from './ThinkingInput'
import DrawingBoard from './DrawingBoard'

interface Props {
  item: ExplainItem
  grading?: Grading
  inProgress: boolean
  onSubmit: (answer: string, confidence: number | null, drawing?: string) => void
  /** Remove a grade you disagree with (its evidence is voided) and answer again. */
  onUndo?: () => void
}

const SCORE_LABEL: Record<string, string> = { '1': 'Solid', '0.5': 'Almost', '0': 'Not yet' }

/** Explain-back: the learner's own words, graded against a hidden rubric by an independent grader. */
export default function ExplainBack({ item, grading, inProgress, onSubmit, onUndo }: Props) {
  const [text, setText] = useState('')
  const [retry, setRetry] = useState(false)
  const [confidence, setConfidence] = useState<number | null>(null)
  const [board, setBoard] = useState(!!item.work)
  const [png, setPng] = useState<string | null>(null)
  const ready = png ? text.trim().length >= 1 : text.trim().length >= 15
  const showForm = !grading || retry || grading.status === 'ungraded' || grading.status === 'voided'
  const pending = inProgress || grading?.status === 'pending'

  return (
    <div className="check explain">
      <div className="check-label">{item.work ? 'Work it out' : 'Explain it back'}</div>
      <Markdown>{item.prompt}</Markdown>
      {grading && !retry && grading.status !== 'voided' && (
        <div className="explain-answer">
          <div className="muted small">Your answer</div>
          <p>{grading.answer}</p>
          {grading.drawing && <img className="drawing-sent" src={`/api/drawing/${grading.drawing}`} alt="Your drawing board" />}
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
      {grading?.status === 'graded' && !retry && (
        <div className="row">
          {grading.score !== 1 && <button className="btn" onClick={() => { setRetry(true); setText(grading.answer) }}>Try again</button>}
          {onUndo && <button className="link small" onClick={onUndo}>I disagree with this grade: remove it</button>}
        </div>
      )}
      {showForm && !pending && (
        <>
          <DictationArea rows={4} value={text} onChange={setText}
            placeholder="In your own words, as if explaining to a colleague. Type or dictate. Pictures-in-words and examples welcome." />
          {board
            ? <DrawingBoard onChange={setPng} />
            : <button type="button" className="link small" onClick={() => setBoard(true)}>Use a drawing board for a calculation or a sketch</button>}
          <ConfidenceSlider value={confidence} onChange={setConfidence} />
          <button className="btn btn-primary" disabled={!ready}
            onClick={() => { onSubmit(text, confidence, png ?? undefined); setRetry(false); setPng(null) }}>Submit for grading</button>
          {png && !text.trim() && <span className="muted small"> Add a line that says what the board shows.</span>}
        </>
      )}
    </div>
  )
}
