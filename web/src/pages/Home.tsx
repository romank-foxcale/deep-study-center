import { Link } from 'react-router-dom'
import { isStale, useStore } from '../store'
import { tracks } from '../data/mock'
import { MasteryBar } from '../components/StateBadge'

export default function Home() {
  const { s } = useStore()
  const next = s.concepts.find(c => c.state === 'learning') ?? s.concepts.find(c => c.state === 'ready')
  const total = s.modules.reduce((n, m) => n + (m.conceptIds.length || m.plannedConcepts || 0), 0)
  const learned = s.concepts.filter(c => ['learned', 'mastered'].includes(c.state)).length
  const pending = s.diffs.filter(d => d.status === 'pending')
  const researching = s.modules.filter(m => m.research === 'researching')
  const stale = s.renditions.filter(r => isStale(r, s)).length

  return (
    <div className="page">
      <section className="hero">
        <div className="eyebrow">Your goal</div>
        <h1>{s.goal.title}</h1>
        <p className="lead">{s.goal.doneLooksLike}</p>
        <div className="row muted small">
          <span>{tracks.length} tracks</span>·<span>{s.modules.length} modules</span>·<span>~{total} concepts outlined so far</span>·
          <span>{s.goal.hoursPerWeek} h/week</span>
        </div>
      </section>

      <div className="grid-2">
        {next && (
          <Link to={`/lesson/${next.id}`} className="card card-link card-accent">
            <div className="eyebrow">Continue</div>
            <h2>{next.title}</h2>
            <p>{next.objective}</p>
            <div className="row"><MasteryBar value={next.mastery} /><span className="muted small">~{next.minutes} min</span></div>
          </Link>
        )}
        <div className="card">
          <div className="eyebrow">Today</div>
          <ul className="plain">
            <li>Spaced reviews due: <strong>0</strong> <span className="muted">(first ones appear a day after you learn something)</span></li>
            <li>Progress: <strong>{learned}</strong> of ~{total} concepts learned</li>
            <li>Lessons waiting to be re-rendered for you: <strong>{stale}</strong></li>
          </ul>
        </div>
      </div>

      {pending.length > 0 && (
        <Link to="/roadmap" className="card card-link card-warn">
          <div className="eyebrow">Roadmap change proposed</div>
          <p>{pending[0].reason}</p>
          <span className="link">Review it →</span>
        </Link>
      )}

      <div className="grid-2">
        <div className="card">
          <div className="eyebrow">Research pipeline</div>
          <p className="muted small">Deep research runs about one module ahead of you.</p>
          <ul className="plain">
            {s.modules.filter(m => m.research === 'ready').map(m => <li key={m.id}><span className="pill pill-ok">ready</span> {m.title}</li>)}
            {researching.map(m => <li key={m.id}><span className="pill pill-warn">researching</span> {m.title}</li>)}
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
