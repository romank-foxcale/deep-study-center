import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useStore } from '../store'
import StateBadge, { MasteryBar } from '../components/StateBadge'

const OP_LABEL = { insert: 'Insert', compress: 'Compress', deepen: 'Deepen' }

export default function Roadmap() {
  const { s, dispatch } = useStore()
  const firstReady = s.modules.find(m => m.research === 'ready')?.id
  const [open, setOpen] = useState<Record<string, boolean>>(firstReady ? { [firstReady]: true } : {})
  if (!s.goal) return <div className="page"><p>No goal yet. <Link to="/goal/new">Set one</Link>.</p></div>
  const pending = s.diffs.filter(d => d.status === 'pending')
  const history = s.diffs.filter(d => d.status !== 'pending')
  const stale = new Set(s.renditions.filter(r => r.stale).map(r => r.conceptId))
  const reviewing = s.jobs.some(j => j.kind === 'roadmap_review' && (j.status === 'queued' || j.status === 'running'))

  return (
    <div className="page">
      <h1>Roadmap</h1>
      <p className="lead">{s.goal.title}. Tracks → modules → concepts. It changes as you learn, but only with your approval.</p>

      {s.placement && !s.placement.finished && (
        <div className="card card-accent row row-between">
          <span>Already know some of this? A short placement quiz finds where you should start.</span>
          <Link className="btn btn-primary" to="/placement">Take placement</Link>
        </div>
      )}
      {reviewing && <div className="card card-warn"><p className="muted">Reviewing your feedback; a proposed change will appear here.</p></div>}
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

      {s.tracks.map((t, ti) => (
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
                    {m.known && <span className="pill pill-ok" title="Placement showed you know this">known</span>}
                    <span className={`pill ${m.research === 'ready' ? 'pill-ok' : m.research === 'researching' ? 'pill-warn' : ''}`}>{m.research}</span>
                    <span className="muted small">{cs.length ? `${done}/${cs.length} learned` : `~${m.plannedConcepts} concepts planned`}</span>
                  </button>
                  {open[m.id] && (
                    <>
                      {m.summary && <p className="muted small module-empty">{m.summary}</p>}
                      {cs.length > 0 && (
                        <ol className="concepts">
                          {cs.map(c => {
                            const body = (
                              <>
                                <span className="concept-title">{c.title}</span>
                                {stale.has(c.id) && <span className="pill pill-warn" title="Will be re-rendered with your latest playbook">re-render</span>}
                                <MasteryBar value={c.mastery} />
                                <StateBadge state={c.state} />
                              </>
                            )
                            return <li key={c.id}>{c.state === 'locked' ? <div className="concept locked">{body}</div> : <Link to={`/lesson/${c.id}`} className="concept">{body}</Link>}</li>
                          })}
                        </ol>
                      )}
                      {m.research === 'outline' && !m.known && (
                        <div className="module-empty row">
                          <span className="muted">Outline only. Concepts and source cards are researched when you're about one module away.</span>
                          <button className="btn btn-small" onClick={() => dispatch({ type: 'researchModule', moduleId: m.id })}>Research now</button>
                        </div>
                      )}
                      {m.research === 'researching' && <p className="muted module-empty">Researching: several perspectives, then only the best sources are kept. This can take a few minutes.</p>}
                    </>
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
