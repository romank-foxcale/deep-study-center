import { useState } from 'react'
import { Link } from 'react-router-dom'
import { jobActive, useStore } from '../store'
import Markdown from './Markdown'
import InlineCheck from './InlineCheck'
import ExplainBack from './ExplainBack'
import Viz from './viz/Viz'
import type { LessonSectionView, StepsView } from '../types'

// A step lesson (SPEC §43): the approved plan taught one step at a time. Each step: a prediction first (open), the step
// in its form, then "Check your understanding" (closed until you open it). A wrong check shows a short repair. The next
// step opens when the check has an answer; it is written while you read this one.

const KIND: Record<string, string> = { foundation: 'Foundation', step: 'Step', formula: 'Formula', goal: 'Goal' }

interface Props {
  conceptId: string
  sections: LessonSectionView[]
  steps: StepsView
  onFeedback: (sec: LessonSectionView) => void
}

export default function StepLesson({ conceptId, sections, steps, onFeedback }: Props) {
  const upto = Math.min(steps.current, sections.length - 1)
  const finished = steps.current >= steps.total
  return (
    <div className="steps-lesson">
      <nav className="steps-bar" aria-label="The plan of this lesson">
        <span className="eyebrow">{finished ? `All ${steps.total} steps done` : `Step ${steps.current + 1} of ${steps.total}`}</span>
        <ol className="steps-chips">
          {steps.nodes.map((n, i) => (
            <li key={n.id} className={`steps-chip${n.done ? ' done' : ''}${i === steps.current ? ' current' : ''}`} title={`${KIND[n.kind] ?? n.kind}: ${n.title}`}>
              {i <= upto || n.done
                ? <a href={`#step-${n.id}`} onClick={e => { e.preventDefault(); document.getElementById(`step-${n.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }}>
                    {n.done ? '✓ ' : ''}<Markdown inline>{n.title}</Markdown></a>
                : <span><Markdown inline>{n.title}</Markdown></span>}
            </li>
          ))}
        </ol>
        {steps.held.length > 0 && <p className="small muted">Builds on what you hold: {steps.held.join(', ')}.</p>}
      </nav>
      {sections.slice(0, upto + 1).map((sec, i) => (
        <Step key={sec.id} conceptId={conceptId} sec={sec} index={i} steps={steps} current={i === steps.current} onFeedback={onFeedback} />
      ))}
      {finished && (
        <div className="card steps-done">
          <strong>You finished the lesson.</strong>
          <span className="muted small"> Your answers count as practice for this idea. Open any step again from the plan above.</span>
          <div className="row" style={{ marginTop: 8 }}>
            <Link className="btn btn-small btn-primary" to="/practice"
              state={{ nodeIds: [conceptId], title: sections[sections.length - 1]?.heading }}>Practise this lesson</Link>
          </div>
        </div>
      )}
    </div>
  )
}

function Step({ conceptId, sec, index, steps, current, onFeedback }: {
  conceptId: string; sec: LessonSectionView; index: number; steps: StepsView; current: boolean; onFeedback: (sec: LessonSectionView) => void
}) {
  const { s, dispatch } = useStore()
  const node = steps.nodes[index]
  const pred = steps.predictions[sec.id]
  const [skipPredict, setSkipPredict] = useState(false)
  const [checkOpen, setCheckOpen] = useState(false)
  const [noteOpen, setNoteOpen] = useState(false)
  const [note, setNote] = useState('')
  const answered = sec.check ? s.answers[`${conceptId}:${sec.check.id}`] : undefined
  const writing = node?.writing || sec.pending
  const gated = !!sec.predict && !pred && !skipPredict && !node?.done
  const rewrite = async (text: string) => {
    if (await dispatch({ type: 'rewriteStep', conceptId, sectionId: sec.id, note: text })) { setNoteOpen(false); setNote('') }
  }

  return (
    <section id={`step-${sec.id}`} className={`step-card${current ? ' current' : ''}`} data-section-id={sec.id}>
      <div className="section-head">
        <div>
          <div className="eyebrow">Step {index + 1} · {KIND[sec.kind ?? ''] ?? 'Step'}{sec.book?.pages ? ` · p. ${sec.book.pages}` : ''}</div>
          <h2><Markdown inline>{sec.heading}</Markdown></h2>
        </div>
        {sec.body && <div className="section-tools">
          <button className="btn btn-small" disabled={writing} onClick={() => setNoteOpen(o => !o)}>Explain differently</button>
          <button className="btn btn-small" onClick={() => onFeedback(sec)}>Feedback</button>
        </div>}
      </div>
      {noteOpen && (
        <div className="step-note row">
          <input className="input" value={note} placeholder="How? For example: more numbers, a picture, shorter (or leave it empty)"
            onChange={e => setNote(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') rewrite(note) }} />
          <button className="btn btn-small btn-primary" onClick={() => rewrite(note)}>Write it again</button>
        </div>
      )}

      {!sec.body
        ? <div className="skeleton" aria-busy={writing}>{writing ? 'Writing this step for you…' : 'This step is written when you reach it.'}</div>
        : <>
          {sec.predict && (pred || !node?.done) && (
            <div className="step-predict">
              <InlineCheck key={`${sec.predict.id}-${pred ? 'done' : 'open'}`} check={sec.predict} label="Predict first"
                previous={pred ? { choice: pred.choice, correct: pred.correct, answer: pred.answer, explanation: pred.explanation, thinking: pred.thinking } : undefined}
                onAnswer={(choice, r) => dispatch({ type: 'predictStep', conceptId, sectionId: sec.id, choice, thinking: r.thinking, confidence: r.confidence })} />
              {gated && <button className="link small" onClick={() => setSkipPredict(true)}>Skip the prediction</button>}
            </div>
          )}
          {gated
            ? <div className="step-veiled muted small">Make your prediction first: the step shows the answer.</div>
            : <>
              <div className={writing ? 'rendering' : ''}><Markdown runnable={conceptId}>{sec.body}</Markdown></div>
              {sec.viz && <div className="viz-block"><Viz key={`${sec.id}-viz`} spec={sec.viz} /></div>}
              {sec.check && (answered || checkOpen
                ? <InlineCheck key={sec.check.id} check={sec.check} previous={answered} label="Check your understanding"
                    onAnswer={(choice, r) => dispatch({ type: 'answer', conceptId, checkId: sec.check!.id, angle: sec.angle, choice, ...r })}
                    onUndo={() => dispatch({ type: 'undoAnswer', conceptId, itemId: sec.check!.id })}
                    onReadReasoning={() => dispatch({ type: 'reviewReasoning', conceptId, itemId: sec.check!.id })} />
                : <button className="check-open" onClick={() => setCheckOpen(true)}>▸ Check your understanding</button>)}
              {answered && !answered.correct && sec.repair && (
                <div className="step-repair">
                  <div className="eyebrow">Fix the idea</div>
                  <Markdown>{sec.repair}</Markdown>
                </div>
              )}
              {sec.explain && (!sec.check || answered) && (
                <ExplainBack key={sec.explain.id} item={sec.explain} grading={s.gradings[`${conceptId}:${sec.explain.id}`]}
                  inProgress={jobActive(s, 'grade', { concept_id: conceptId })}
                  onSubmit={(answer, confidence, drawing) => dispatch({ type: 'explain', conceptId, itemId: sec.explain!.id, angle: sec.angle, answer, confidence, drawing })}
                  onUndo={() => dispatch({ type: 'undoAnswer', conceptId, itemId: sec.explain!.id })} />
              )}
            </>}
        </>}
    </section>
  )
}
