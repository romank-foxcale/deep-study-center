import { useStore } from '../store'
import { FeedbackList } from '../components/SidePanel'
import type { Playbook } from '../types'

const ADJUST: { key: keyof Playbook['adjust']; label: string; low: string; high: string }[] = [
  { key: 'pace', label: 'Pace', low: 'smaller steps', high: 'faster' },
  { key: 'depth', label: 'Depth', low: 'essentials only', high: 'go deep' },
  { key: 'rigor', label: 'Rigor', low: 'intuition first', high: 'proofs first' },
]

export default function Me() {
  const { s, dispatch } = useStore()
  const { playbook } = s
  return (
    <div className="page">
      <h1>Me & playbook</h1>
      <p className="lead">Knowledge center #2: how lessons are written for you. It's built from what you say and how practice goes, shared by all your goals, and you can correct any line.</p>

      <div className="card">
        <div className="row row-between">
          <h2>Teaching playbook</h2>
          <span className="pill">v{playbook.version}</span>
        </div>
        <p className="muted small">Any change bumps the version. Lessons rendered from an older version are re-rendered when you open them, and studied ones offer a refresh.</p>
        <table className="table">
          <thead><tr><th>What</th><th>Verdict</th><th>Helps?</th><th>Why we think so</th><th /></tr></thead>
          <tbody>
            {playbook.entries.map(e => (
              <tr key={e.id}>
                <td><span className="muted small">{e.dimension}</span><br />{e.value}</td>
                <td><span className={`badge verdict-${e.verdict}`}>{e.verdict}</span></td>
                <td><span className="meter"><span style={{ width: `${e.score * 100}%` }} /></span> <span className="muted small">{e.score.toFixed(2)} · evidence {e.evidence.toFixed(1)}</span></td>
                <td className="small">{e.note}</td>
                <td>
                  <select className="input input-small" value="" aria-label={`Correct ${e.value}`}
                    onChange={ev => ev.target.value && dispatch({ type: 'correctEntry', id: e.id, verdict: ev.target.value as 'works' })}>
                    <option value="">Correct…</option>
                    <option value="works">It works for me</option>
                    <option value="avoid">Avoid it</option>
                    <option value="trying">Not sure yet</option>
                    <option value="remove">Remove</option>
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>Adjustments</h2>
        {ADJUST.map(a => (
          <label key={a.key} className="slider-row">
            <span className="slider-label">{a.label}</span>
            <span className="muted small">{a.low}</span>
            <input type="range" min={-3} max={3} step={1} value={playbook.adjust[a.key]}
              onChange={e => dispatch({ type: 'adjust', key: a.key, value: Number(e.target.value) })} />
            <span className="muted small">{a.high}</span>
            <span className="pill">{playbook.adjust[a.key] > 0 ? '+' : ''}{playbook.adjust[a.key]}</span>
          </label>
        ))}
      </div>

      <div className="card">
        <h2>Feedback log</h2>
        <p className="muted small">Every piece of feedback, and what it changed. A weekly reflection reads this to spot patterns.</p>
        {s.feedback.length ? <FeedbackList items={s.feedback} /> : <p className="muted">Nothing yet.</p>}
      </div>

      <div className="card">
        <h2>All notes</h2>
        {s.notes.length === 0 ? <p className="muted">No notes yet.</p> : (
          <ul className="plain">{s.notes.map(n => <li key={n.id}><span className="muted small">{s.concepts.find(c => c.id === n.conceptId)?.title}:</span> {n.text}</li>)}</ul>
        )}
      </div>
    </div>
  )
}
