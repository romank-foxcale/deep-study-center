import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useStore } from '../store'
import Markdown from '../components/Markdown'
import ThinkingInput, { NO_REASONING, ReasoningShown, type Reasoning } from '../components/ThinkingInput'
import type { ProbeAnswered } from '../types'

const LEVEL = { known: { label: 'known', cls: 'pill pill-ok' }, partial: { label: 'partly', cls: 'pill pill-warn' }, unknown: { label: 'new', cls: 'pill' } }

/** The probe: quick questions, one at a time, an agent picks from your answers and thinking, then where you stand. */
export default function Probe() {
  const { s, dispatch } = useStore()
  const [choice, setChoice] = useState<number | null>(null)
  const [reasoning, setReasoning] = useState<Reasoning>(NO_REASONING)
  const p = s.probe
  if (!s.goal || !p) return <div className="page"><p>No goal yet. <Link to="/goal/new">Set one</Link>.</p></div>
  const last = p.answered[p.answered.length - 1]

  const send = (c: number | null) => {
    if (!p.question) return
    dispatch({ type: 'probeAnswer', itemId: p.question.id, choice: c, ...reasoning })
    setChoice(null)
    setReasoning(NO_REASONING)
  }

  return (
    <div className="page page-narrow">
      <h1>Where you stand</h1>
      <p className="lead">Quick questions that find the edge of what you know for “{s.goal.title}”. Each question is chosen from your
        earlier answers. Think out loud, typed or dictated: your thinking tells the agent more than the answer. “I don't know” is a
        good answer; a guess is not.</p>

      {p.status !== 'done' && p.asked > 0 && (
        <div className="probe-progress">
          <div className="probe-bar"><span style={{ width: `${Math.min(100, (p.asked / p.maxQuestions) * 100)}%` }} /></div>
          <span className="muted small">{p.asked} answered · at most {p.maxQuestions}</span>
        </div>
      )}

      {p.status === 'idle' && (
        <div className="card">
          {p.error && <p className="error small">The last attempt failed: {p.error}</p>}
          <p>About 6–12 short questions, one at a time. It takes 5–10 minutes.</p>
          <button className="btn btn-primary" onClick={() => dispatch({ type: 'startProbe' })}>{p.error ? 'Try again' : 'Start'}</button>
        </div>
      )}

      {last && p.status !== 'done' && <LastAnswer a={last} />}

      {p.status === 'thinking' && (
        <div className="card"><p className="muted">{p.asked === 0 ? 'Choosing your first question…' : 'Reading your answer and choosing the next question…'}</p></div>
      )}

      {p.status === 'asking' && p.question && (
        <div className="card">
          <div className="eyebrow">Question {p.question.round} · {p.question.module}</div>
          <Markdown>{p.question.prompt}</Markdown>
          <div className="check-options" role="radiogroup">
            {p.question.options.map((o, i) => (
              <button key={i} className={`check-option ${choice === i ? 'selected' : ''}`} role="radio" aria-checked={choice === i} onClick={() => setChoice(i)}>
                <Markdown inline>{o}</Markdown>
              </button>
            ))}
          </div>
          <ThinkingInput value={reasoning} onChange={setReasoning} />
          <div className="row">
            <button className="btn btn-primary" disabled={choice === null} onClick={() => send(choice)}>Answer</button>
            <button className="btn" onClick={() => send(null)}>I don't know</button>
            <span className="spacer" />
            {p.asked >= 3 && <button className="link small" onClick={() => dispatch({ type: 'probeAssessNow' })}>Stop and see where I stand</button>}
          </div>
        </div>
      )}

      {p.status === 'done' && p.assessment && (
        <div className="card">
          <div className="eyebrow">After {p.asked} question{p.asked === 1 ? '' : 's'}</div>
          <p><strong>{p.assessment.summary}</strong></p>
          <p>{p.assessment.edge}</p>
          {p.assessment.misconceptions.length > 0 && (
            <>
              <div className="eyebrow">Ideas to fix</div>
              <ul>{p.assessment.misconceptions.map((m, i) => <li key={i}>{m}</li>)}</ul>
            </>
          )}
          {p.assessment.modules.length > 0 && (
            <ul className="probe-levels">
              {p.assessment.modules.map(m => (
                <li key={m.moduleId}><span className={LEVEL[m.level].cls}>{LEVEL[m.level].label}</span> <strong>{m.title}</strong>
                  {m.note && <span className="muted small"> · {m.note}</span>}</li>
              ))}
            </ul>
          )}
          <div className="row">
            {p.assessment.applied
              ? <><span className="pill pill-ok">used</span><Link className="btn btn-primary" to="/roadmap">Open the roadmap</Link></>
              : <button className="btn btn-primary" onClick={() => dispatch({ type: 'applyProbe' })}
                  title="Known steps become a roadmap proposal; the edge and the ideas to fix go into your goal profile, so research and lessons use them">
                  Use this for my roadmap and lessons</button>}
            <button className="btn" onClick={() => dispatch({ type: 'resetProbe' })}>Retake</button>
          </div>
        </div>
      )}

      {p.answered.length > 0 && (
        <details className="probe-history">
          <summary>Your answers ({p.answered.length})</summary>
          {p.answered.map(a => <LastAnswer key={a.id} a={a} compact />)}
        </details>
      )}
    </div>
  )
}

function LastAnswer({ a, compact }: { a: ProbeAnswered; compact?: boolean }) {
  const dunno = a.choice === null
  return (
    <div className={`check-result ${a.correct ? 'ok' : 'bad'} ${compact ? 'probe-compact' : ''}`}>
      {!compact && <div className="eyebrow">Last answer · {a.module}</div>}
      {compact && <div className="small"><Markdown inline>{a.prompt}</Markdown></div>}
      <strong>{a.correct ? 'Right.' : dunno ? 'You did not know.' : 'Not quite.'}</strong>{' '}
      {!a.correct && <span>Answer: <Markdown inline>{a.options[a.answer]}</Markdown>. </span>}
      <Markdown inline>{a.explanation}</Markdown>
      <ReasoningShown thinking={a.thinking} confidence={a.confidence} />
    </div>
  )
}
