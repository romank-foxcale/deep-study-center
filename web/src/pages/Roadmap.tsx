import { useState } from 'react'
import { Link } from 'react-router-dom'
import { isStale, useStore } from '../store'
import { tracks } from '../data/mock'
import StateBadge, { MasteryBar } from '../components/StateBadge'

const OP_LABEL = { insert: 'Insert', compress: 'Compress', deepen: 'Deepen' }

export default function Roadmap() {
  const { s, dispatch } = useStore()
  const [open, setOpen] = useState<Record<string, boolean>>({ 'm-la': true })
  const pending = s.diffs.filter(d => d.status === 'pending')
  const history = s.diffs.filter(d => d.status !== 'pending')

  return (
    <div className="page">
      <h1>Roadmap</h1>
      <p className="lead">{s.goal.title}. Tracks → modules → concepts. It changes as you learn, but only with your approval.</p>

      {pending.map(d => (
        <div key={d.id} className="card card-warn">
          <div className="eyebrow">Proposed change</div>
          <p>{d.reason}</p>
          <ul className="diff">
            {d.changes.map((c, i) => <li key={i} className={`diff-${c.op}`}><strong>{OP_LABEL[c.op]}</strong> {c.title}: <span className="muted">{c.detail}</span></li>)}
          </ul>
          <div className="row">
            <button className="btn btn-primary" onClick={() => dispatch({ type: 'decideDiff', id: d.id, approve: true })}>Approve</button>
            <button className="btn" onClick={() => dispatch({ type: 'decideDiff', id: d.id, approve: false })}>Reject</button>
          </div>
        </div>
      ))}

      {tracks.map((t, ti) => (
        <section key={t.id} className="track">
          <div className="track-head">
            <span className="track-num">{ti + 1}</span>
            <div><h2>{t.title}</h2><p className="muted">{t.summary}</p></div>
          </div>
          <div className="modules">
            {s.modules.filter(m => m.trackId === t.id).map(m => {
              const cs = m.conceptIds.map(id => s.concepts.find(c => c.id === id)!).filter(Boolean)
              const done = cs.filter(c => ['learned', 'mastered'].includes(c.state)).length
              return (
                <div key={m.id} className="module">
                  <button className="module-head" onClick={() => setOpen(o => ({ ...o, [m.id]: !o[m.id] }))} aria-expanded={!!open[m.id]}>
                    <span className="module-title">{m.title}</span>
                    <span className={`pill ${m.research === 'ready' ? 'pill-ok' : m.research === 'researching' ? 'pill-warn' : ''}`}>{m.research}</span>
                    <span className="muted small">{cs.length ? `${done}/${cs.length} learned` : `~${m.plannedConcepts} concepts planned`}</span>
                  </button>
                  {open[m.id] && (
                    cs.length ? (
                      <ol className="concepts">
                        {cs.map(c => {
                          const stale = isStale(s.renditions.find(r => r.conceptId === c.id), s)
                          const body = (
                            <>
                              <span className="concept-title">{c.title}</span>
                              {stale && <span className="pill pill-warn" title="Will be re-rendered with your latest playbook">re-render</span>}
                              <MasteryBar value={c.mastery} />
                              <StateBadge state={c.state} />
                            </>
                          )
                          return <li key={c.id}>{c.state === 'locked' ? <div className="concept locked">{body}</div> : <Link to={`/lesson/${c.id}`} className="concept">{body}</Link>}</li>
                        })}
                      </ol>
                    ) : <p className="muted module-empty">Outline only. Concepts and source cards are researched when you're about one module away.</p>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      ))}

      {history.length > 0 && (
        <section>
          <h2>Change history</h2>
          {history.map(d => (
            <div key={d.id} className="card">
              <div className="row row-between"><span>{d.reason}</span><span className={`pill ${d.status === 'approved' ? 'pill-ok' : ''}`}>{d.status}</span></div>
              <ul className="diff">{d.changes.map((c, i) => <li key={i}><strong>{OP_LABEL[c.op]}</strong> {c.title}: <span className="muted">{c.detail}</span></li>)}</ul>
            </div>
          ))}
        </section>
      )}
    </div>
  )
}
