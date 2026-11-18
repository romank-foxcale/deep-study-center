import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useStore } from '../store'
import StateBadge, { MasteryBar } from '../components/StateBadge'
import OhtaniGrid, { useStepProgress, type GridPick, type StepProgress } from '../components/OhtaniGrid'

const OP_LABEL = { insert: 'Insert', compress: 'Compress', deepen: 'Deepen' }

export default function Roadmap() {
  const { s, dispatch } = useStore()
  const firstReady = s.modules.find(m => m.research === 'ready')?.id
  const [open, setOpen] = useState<Record<string, boolean>>(firstReady ? { [firstReady]: true } : {})
  const [pick, setPick] = useState<GridPick | null>({ kind: 'goal' })
  const prog = useStepProgress(s.modules, s.concepts)
  const showLessons = (id: string) => {
    setOpen(o => ({ ...o, [id]: true }))
    requestAnimationFrame(() => document.getElementById(`mod-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
  }
  if (!s.goal) return <div className="page"><p>No goal yet. <Link to="/goal/new">Set one</Link>.</p></div>
  const pending = s.diffs.filter(d => d.status === 'pending')
  const history = s.diffs.filter(d => d.status !== 'pending')
  const stale = new Set(s.renditions.filter(r => r.stale).map(r => r.conceptId))
  const reviewing = s.jobs.some(j => j.kind === 'roadmap_review' && (j.status === 'queued' || j.status === 'running'))

  return (
    <div className="page">
      <h1>Roadmap</h1>
      {s.goal.layout === 'ohtani'
        ? <p className="lead">{s.goal.title}. Your Ohtani table: 8 areas of 8 steps around the goal, and 8 merge steps that join
            neighbouring areas. A cell fills as you pass its lessons' checks.</p>
        : <p className="lead">{s.goal.title}. Tracks → modules → concepts. It changes as you learn, but only with your approval.</p>}

      {s.goal.layout === 'ohtani' && (
        <section className="og-wrap">
          <OhtaniGrid goalTitle={s.goal.title} tracks={s.tracks} modules={s.modules} concepts={s.concepts} pick={pick} onPick={setPick} />
          <div className="card og-detail">
            <GridDetail pick={pick} setPick={setPick} prog={prog} showLessons={showLessons} />
          </div>
        </section>
      )}

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
                <div key={m.id} id={`mod-${m.id}`} className="module">
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
                      {m.research === 'researching' && (
                        <p className="muted module-empty">Researching: several perspectives, then only the best sources are kept. This can take a few minutes.
                          {(() => {
                            const job = s.jobs.find(j => j.kind === 'research_module' && j.input.module_id === m.id && (j.status === 'running' || j.status === 'queued'))
                            const last = job?.progress.slice(-1)[0]
                            return last ? <><br /><span className="small">Now: {last}</span></> : null
                          })()}
                        </p>
                      )}
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

const pctOf = (x: number) => `${Math.round(x * 100)}%`

function GridDetail({ pick, setPick, prog, showLessons }: {
  pick: GridPick | null; setPick: (p: GridPick) => void; prog: Record<string, StepProgress>; showLessons: (id: string) => void
}) {
  const { s } = useStore()
  const goal = s.goal!
  if (!pick || pick.kind === 'goal') {
    const fills = s.modules.map(m => prog[m.id].fill)
    const full = fills.filter(f => f >= 1).length
    const now = s.concepts.find(c => ['ready', 'learning', 'rusty'].includes(c.state))
    const nowModule = now && s.modules.find(m => m.id === now.moduleId)
    return (
      <>
        <div className="eyebrow">Goal</div>
        <h2>{goal.title}</h2>
        {goal.doneLooksLike && <p><strong>Done when:</strong> {goal.doneLooksLike}</p>}
        <p className="muted">{full} of {s.modules.length} steps complete · {pctOf(fills.reduce((a, b) => a + b, 0) / Math.max(1, fills.length))} overall</p>
        {now && nowModule && <p>Now: <Link to={`/lesson/${now.id}`}>{now.title}</Link> <span className="muted">in {nowModule.title}</span></p>}
        <p className="muted small">Pick a cell to see its step.</p>
      </>
    )
  }
  if (pick.kind === 'area') {
    const t = s.tracks.find(x => x.id === pick.trackId)
    if (!t) return null
    return (
      <>
        <div className="eyebrow">Area</div>
        <h2>{t.title}</h2>
        <p className="muted">{t.summary}</p>
        <ol className="og-steps">
          {s.modules.filter(m => m.trackId === t.id).map(m => (
            <li key={m.id}><button className="link-btn" onClick={() => setPick({ kind: 'step', moduleId: m.id })}>{m.title}</button>
              <span className="muted small"> · {m.known ? 'known' : pctOf(prog[m.id].fill)}</span></li>
          ))}
        </ol>
      </>
    )
  }
  const m = s.modules.find(x => x.id === pick.moduleId)
  if (!m) return null
  const t = s.tracks.find(x => x.id === m.trackId)
  const p = prog[m.id]
  const locked = p.locked && p.fill < 1
  return (
    <>
      <div className="eyebrow">{t?.pos === 'C' ? 'Merge step' : `${t?.title} · step ${m.ord + 1} of 8`}</div>
      <h2>{m.title}</h2>
      {m.summary && <p className="muted">{m.summary}</p>}
      {m.doneWhen && <p><strong>Done when:</strong> {m.doneWhen}</p>}
      <p className="muted small">{m.known ? 'Placement showed you know this.'
        : p.total ? `${p.done}/${p.total} lessons learned` : `~${m.plannedConcepts} lessons planned; researched about one step ahead of you`}</p>
      {m.requires.length > 0 && (
        <>
          <p className="small"><strong>{locked ? 'Unlocks after' : 'Builds on'}:</strong></p>
          <ul className="og-steps">
            {m.requires.map(r => {
              const rm = s.modules.find(x => x.id === r)
              const rt = rm && s.tracks.find(x => x.id === rm.trackId)
              return rm && <li key={r}><button className="link-btn" onClick={() => setPick({ kind: 'step', moduleId: r })}>{rm.title}</button>
                <span className="muted small"> · {rt?.title} · {pctOf(prog[r].fill)}</span></li>
            })}
          </ul>
        </>
      )}
      <button className="btn btn-small" onClick={() => showLessons(m.id)}>Show lessons</button>
    </>
  )
}
