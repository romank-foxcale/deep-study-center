import { Link } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { getPlan } from '../store'
import type { Plan } from '../types'
import { useStore } from '../store'
import { MasteryBar } from '../components/StateBadge'

export default function Home() {
  const { s, dispatch } = useStore()
  const [plan, setPlan] = useState<Plan | null>(null)
  useEffect(() => { getPlan().then(setPlan, () => setPlan(null)) }, [s])
  if (!s.goal) {
    return (
      <div className="page">
        <h1>Welcome</h1>
        <p className="lead">Start with a goal. A short conversation, then agents research it and build your roadmap.</p>
        <Link className="btn btn-primary" to="/goal/new">Set a goal</Link>
      </div>
    )
  }
  const next = s.concepts.find(c => c.state === 'learning') ?? s.concepts.find(c => c.state === 'ready')
  const total = s.modules.reduce((n, m) => n + (m.conceptIds.length || m.plannedConcepts || 0), 0)
  const learned = s.concepts.filter(c => ['learned', 'mastered'].includes(c.state)).length
  const pending = s.diffs.filter(d => d.status === 'pending')
  const due = s.reviews.filter(r => r.isDue)
  const stale = s.renditions.filter(r => r.stale).length
  const running = s.jobs.filter(j => j.status === 'queued' || j.status === 'running')

  return (
    <div className="page">
      <section className="hero">
        <div className="eyebrow">Your goal</div>
        <h1>{s.goal.title}</h1>
        <p className="lead">{s.goal.doneLooksLike}</p>
        <div className="row muted small">
          <span>{s.tracks.length} tracks</span>·<span>{s.modules.length} modules</span>·<span>~{total} concepts outlined so far</span>·
          <span>{s.goal.hoursPerWeek} h/week</span>
        </div>
      </section>

      <div className="grid-2">
        {next ? (
          <Link to={`/lesson/${next.id}`} className="card card-link card-accent">
            <div className="eyebrow">Continue</div>
            <h2>{next.title}</h2>
            <p>{next.objective}</p>
            <div className="row"><MasteryBar value={next.mastery} /><span className="muted small">~{next.minutes} min</span></div>
          </Link>
        ) : (
          <Link to="/roadmap" className="card card-link card-accent">
            <div className="eyebrow">Next</div>
            <p>No researched lesson is ready yet. Open the roadmap to research the next module.</p>
          </Link>
        )}
        <div className="card">
          <div className="eyebrow">Today</div>
          <ul className="plain">
            <li>Spaced reviews due: <strong>{due.length}</strong> {due.length > 0
              ? <Link to="/review" className="link">Start reviews →</Link>
              : <span className="muted">(the first one comes a day after you learn something)</span>}</li>
            <li>Progress: <strong>{learned}</strong> of ~{total} concepts learned</li>
            <li>Lessons waiting to be re-rendered for you: <strong>{stale}</strong></li>
          </ul>
        </div>
      </div>

      {plan && (() => {
        const today = plan.days[0]
        return (
          <div className="card">
            <div className="row row-between">
              <div className="eyebrow">Today's plan · {today.minutes} of {today.budget} min</div>
              <Link to="/week" className="link">This week →</Link>
            </div>
            {!today.study ? <p className="muted">Not a study day. Rest is part of learning.</p>
              : today.items.length === 0 ? <p className="muted">Nothing planned yet: research for your next module is still running.</p>
              : <ul className="plain">{today.items.map((it, i) => (
                  <li key={i}>
                    <span className={`pill ${it.kind === 'review' ? 'pill-warn' : ''}`}>{it.kind}</span>{' '}
                    <Link to={it.kind === 'review' ? '/review' : `/lesson/${it.conceptId}`}
                      onClick={() => { if (it.goalId !== s.goal?.id) dispatch({ type: 'setGoal', id: it.goalId }) }}>{it.title}</Link>
                    <span className="muted small"> · {it.minutes} min{it.note ? ` · ${it.note}` : ''}</span>
                  </li>))}</ul>}
          </div>
        )
      })()}

      {s.cardProposals.length > 0 && (
        <Link to="/library" className="card card-link card-warn">
          <div className="eyebrow">Source updates to review</div>
          <p>{s.cardProposals.length} card{s.cardProposals.length > 1 ? 's have' : ' has'} a proposed update: {s.cardProposals[0].summary}</p>
          <span className="link">Review →</span>
        </Link>
      )}

      {pending.length > 0 && (
        <Link to="/roadmap" className="card card-link card-warn">
          <div className="eyebrow">Roadmap change proposed</div>
          <p>{pending[0].reason}</p>
          <span className="link">Review it →</span>
        </Link>
      )}

      <div className="grid-2">
        <div className="card">
          <div className="eyebrow">Agents at work</div>
          {running.length === 0
            ? <p className="muted">Nothing running. Research runs about one module ahead of you.</p>
            : <ul className="plain">{running.map(j => <li key={j.id}><span className="pill pill-warn">{j.status}</span> {j.label}<div className="muted small">{j.progress.slice(-1)[0]}</div></li>)}</ul>}
          <ul className="plain">
            {s.modules.filter(m => m.research === 'ready').map(m => <li key={m.id}><span className="pill pill-ok">ready</span> {m.title}</li>)}
          </ul>
        </div>
        <div className="card">
          <div className="eyebrow">What your feedback changed</div>
          {s.feedback.length === 0
            ? <p className="muted">Nothing yet. Feedback on any lesson reshapes every lesson after it.</p>
            : <ul className="plain">{s.feedback.slice(0, 4).flatMap(f => f.effects.slice(0, 1)).map((e, i) => <li key={i}>{e}</li>)}</ul>}
          <Link to="/me" className="link">Open your playbook →</Link>
        </div>
      </div>
    </div>
  )
}
