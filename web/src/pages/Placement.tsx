import { useState } from 'react'
import { Link } from 'react-router-dom'
import { jobActive, useStore } from '../store'
import Markdown from '../components/Markdown'

/** Placement diagnostic: a few quick questions over the roadmap outline to find where to start. */
export default function Placement() {
  const { s, dispatch } = useStore()
  const [choice, setChoice] = useState<number | null>(null)
  const p = s.placement
  if (!s.goal || !p) return <div className="page"><p>No goal yet. <Link to="/goal/new">Set one</Link>.</p></div>
  const writing = jobActive(s, 'placement_bank')
  const total = p.counts.known + p.counts.gap + p.counts.uncertain

  const answer = (c: number | null) => {
    if (!p.question) return
    dispatch({ type: 'placementAnswer', moduleId: p.question.moduleId, choice: c })
    setChoice(null)
  }

  return (
    <div className="page page-narrow">
      <h1>Placement</h1>
      <p className="lead">A few quick questions to find where you should start. “I don't know” is a great answer: it's better than guessing,
        and nothing you already know will be skipped without your approval.</p>

      {p.finished && (
        <div className="card">
          <p>Placement is done: {p.counts.known} of {total} modules look known.
            {p.counts.known > 0 ? ' The roadmap has a proposal for you to review.' : ''}</p>
          <div className="row">
            <Link className="btn btn-primary" to="/roadmap">Open the roadmap</Link>
            <button className="btn" onClick={() => dispatch({ type: 'resetPlacement' })}>Retake placement</button>
          </div>
        </div>
      )}

      {!p.finished && !p.available && (
        <div className="card">
          {writing
            ? <p className="muted">Writing your placement questions (one per module)…</p>
            : <button className="btn btn-primary" onClick={() => dispatch({ type: 'startPlacement' })}>Start placement</button>}
        </div>
      )}

      {!p.finished && p.available && p.question && (
        <div className="card">
          <div className="row row-between">
            <span className="eyebrow">Question {p.asked + 1} · {p.question.module}</span>
            <span className="muted small">{p.counts.uncertain} module{p.counts.uncertain === 1 ? '' : 's'} still uncertain</span>
          </div>
          <Markdown>{p.question.prompt}</Markdown>
          <div className="check-options" role="radiogroup">
            {p.question.options.map((o, i) => (
              <button key={i} className={`check-option ${choice === i ? 'selected' : ''}`} role="radio" aria-checked={choice === i} onClick={() => setChoice(i)}>
                <Markdown inline>{o}</Markdown>
              </button>
            ))}
          </div>
          <div className="row">
            <button className="btn btn-primary" disabled={choice === null} onClick={() => answer(choice)}>Answer</button>
            <button className="btn" onClick={() => answer(null)}>I don't know</button>
          </div>
        </div>
      )}

      {!p.finished && p.available && p.done && (
        <div className="card">
          <p>That's enough to place you: {p.counts.known} known, {p.counts.gap} to learn.</p>
          <button className="btn btn-primary" onClick={() => dispatch({ type: 'finishPlacement' })}>See my starting point</button>
        </div>
      )}
    </div>
  )
}
