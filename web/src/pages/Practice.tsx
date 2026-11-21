import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { getPractice, getPracticeDue, useStore } from '../store'
import Markdown from '../components/Markdown'
import { DictationArea } from '../components/ThinkingInput'
import type { PracticeDue, PracticeItem, PracticeView } from '../types'

const VERDICT: Record<string, { label: string; cls: string }> = {
  solved: { label: 'Solved', cls: 'ok' }, progress: { label: 'On track', cls: 'ok' },
  stuck: { label: 'Stuck', cls: 'bad' }, wrong: { label: 'Not this way', cls: 'bad' },
}

/** Recall practice (SPEC §24): problems that make what you understand usable. */
export default function Practice() {
  const { id } = useParams()
  return id ? <PracticeRun id={id} /> : <StartPractice />
}

function StartPractice() {
  const { s, dispatch } = useStore()
  const navigate = useNavigate()
  const location = useLocation()
  const preset = (location.state as { nodeIds?: string[]; title?: string } | null) ?? null
  const [due, setDue] = useState<PracticeDue | null>(null)
  const [own, setOwn] = useState('')
  const [src, setSrc] = useState({ id: '', page: '' })
  const [starting, setStarting] = useState<string | null | undefined>(undefined)
  useEffect(() => { getPracticeDue().then(setDue, () => setDue(null)) }, [s])
  useEffect(() => {
    if (starting !== undefined && s.lastPractice && s.lastPractice !== starting) navigate(`/practice/${s.lastPractice}`)
  }, [s.lastPractice, starting, navigate])
  const start = async (a: { nodeIds?: string[]; own?: string; source?: { id: string; page: number } }) => {
    setStarting(s.lastPractice)
    if (!await dispatch({ type: 'startPractice', ...a })) setStarting(undefined)
  }
  const ready = s.sources.filter(x => x.status === 'ready')
  return (
    <div className="page page-narrow">
      <h1>Practice</h1>
      <p className="lead">Understanding is not enough: you must be able to recall an idea when a problem calls for it. Each
        problem makes you find the idea yourself. Think out loud; you get small hints, never the answer. Each idea comes back
        when it is due.</p>

      {preset?.nodeIds?.length ? (
        <div className="card card-accent">
          <p>Practise <strong>{preset.title}</strong>.</p>
          <button className="btn btn-primary" disabled={starting !== undefined} onClick={() => start({ nodeIds: preset.nodeIds })}>Start</button>
        </div>
      ) : null}

      <div className="card">
        <div className="eyebrow">Due now</div>
        {!due ? <p className="muted">Loading…</p> : due.due.length === 0 ? (
          <p className="muted">Nothing to practise yet. Learn something in <Link to="/study">Study</Link> or a lesson first.
            {due.next && <> The next idea is due {new Date(due.next).toLocaleString()}.</>}</p>
        ) : (
          <>
            <p>{due.dueCount > 0 && <><strong>{due.dueCount}</strong> idea{due.dueCount === 1 ? ' is' : 's are'} due</>}
              {due.dueCount > 0 && due.newCount > 0 && ', and '}
              {due.newCount > 0 && <><strong>{due.newCount}</strong> idea{due.newCount === 1 ? '' : 's'} you learned recently {due.newCount === 1 ? 'has' : 'have'} never been practised</>}.</p>
            <ul className="practice-due">{due.due.slice(0, 8).map(d => (
              <li key={d.nodeId}><Markdown inline>{d.title}</Markdown> <span className={d.reason === 'due' ? 'pill pill-warn' : 'pill'}>{d.reason === 'due' ? 'due' : 'new'}</span></li>
            ))}</ul>
            <button className="btn btn-primary" disabled={starting !== undefined} onClick={() => start({})}>Practise 5 problems</button>
          </>
        )}
      </div>

      <div className="card">
        <div className="eyebrow">My own problem</div>
        <DictationArea value={own} onChange={setOwn} rows={3} placeholder="Paste or dictate a problem from your course, book or work" />
        {ready.length > 0 && (
          <div className="row small">
            <span className="muted">or a page of a source:</span>
            <select className="input input-small" value={src.id} onChange={e => setSrc({ ...src, id: e.target.value })}>
              <option value="">(none)</option>
              {ready.map(x => <option key={x.id} value={x.id}>{x.title}</option>)}
            </select>
            {src.id && <input className="input input-small practice-page" type="number" min={1} placeholder="page" value={src.page}
              onChange={e => setSrc({ ...src, page: e.target.value })} />}
          </div>
        )}
        <button className="btn" disabled={starting !== undefined || (own.trim().length < 10 && !(src.id && Number(src.page) > 0))}
          onClick={() => start({ own, source: src.id && Number(src.page) > 0 ? { id: src.id, page: Number(src.page) } : undefined })}>
          Practise this problem</button>
      </div>

      {s.practices.length > 0 && (
        <>
          <h2>Earlier practice</h2>
          <ul className="study-list">{s.practices.map(p => (
            <li key={p.id}><Link to={`/practice/${p.id}`}>{p.title}</Link> <span className={p.status === 'done' ? 'pill pill-ok' : 'pill'}>{p.status}</span>
              <span className="muted small"> · {new Date(p.createdAt).toLocaleDateString()}</span></li>
          ))}</ul>
        </>
      )}
    </div>
  )
}

function PracticeRun({ id }: { id: string }) {
  const { s, dispatch } = useStore()
  const [v, setV] = useState<PracticeView | null>(null)
  const [missing, setMissing] = useState(false)
  const [tick, setTick] = useState(0)
  useEffect(() => { getPractice(id).then(x => { setV(x); setMissing(false) }, () => setMissing(true)) }, [id, s, tick])
  if (missing) return <div className="page"><p>Practice not found. <Link to="/practice">Back</Link></p></div>
  if (!v) return <div className="page"><p className="muted">Loading…</p></div>
  const act = async (a: Parameters<typeof dispatch>[0]) => { await dispatch(a); setTick(t => t + 1) }
  const open = v.items.find(i => i.status === 'open')
  const closed = v.items.filter(i => i.status !== 'open')
  const done = v.status === 'done'
  return (
    <div className="page page-narrow practice">
      <div className="row row-between">
        <div><div className="eyebrow">Practice · problem {Math.min(v.items.length, v.count)} of {v.count}</div><h1>{v.title}</h1></div>
        {!done && <button className="link small" onClick={() => act({ type: 'practiceStop', practiceId: v.id })}>Stop</button>}
      </div>
      <p className="muted small">Level {v.level} of 4: {v.levelText}. It goes up after a clean solve and down after a hard one.</p>
      {v.error && (
        <div className="card card-warn"><p className="small">The last step failed: {v.error}</p>
          <button className="btn" onClick={() => act({ type: 'practiceRetry', practiceId: v.id })}>Try again</button></div>
      )}
      {open && <ProblemCard key={open.id} it={open} busy={v.busy} act={act} />}
      {!open && v.busy && <p className="muted">Writing the next problem…</p>}
      {done && (
        <div className="card card-accent">
          <div className="eyebrow">Done</div>
          <p>{closed.filter(i => i.status === 'solved').length} of {closed.length} solved
            {closed.some(i => i.hints > 0) && `, ${closed.reduce((n, i) => n + i.hints, 0)} hint(s)`}. Each idea is scheduled
            again: sooner when it was hard, later when it was easy.</p>
          <div className="row"><Link className="btn btn-primary" to="/practice">More practice</Link><Link className="btn" to="/map">Knowledge map</Link></div>
        </div>
      )}
      {closed.length > 0 && <h2>Solved and closed</h2>}
      {[...closed].reverse().map(it => <ProblemCard key={it.id} it={it} busy={false} act={act} />)}
    </div>
  )
}

function ProblemCard({ it, busy, act }: { it: PracticeItem; busy: boolean; act: (a: Parameters<ReturnType<typeof useStore>['dispatch']>[0]) => Promise<void> }) {
  const [text, setText] = useState('')
  const [showSolution, setShowSolution] = useState(it.status === 'given_up')
  const open = it.status === 'open'
  const waiting = busy && open
  const send = async (hint: boolean) => { await act({ type: 'practiceSubmit', itemId: it.id, text, hint }); setText('') }
  return (
    <div className={`card practice-problem ${it.status}`}>
      <div className="row row-between">
        <div className="eyebrow">{it.title}</div>
        {!open && <span className={it.status === 'solved' ? 'pill pill-ok' : 'pill pill-warn'}>
          {it.status === 'solved' ? `solved${it.hints ? `, ${it.hints} hint${it.hints > 1 ? 's' : ''}` : ''}` : it.status === 'given_up' ? 'gave up' : 'skipped'}</span>}
      </div>
      <Markdown>{it.prompt}</Markdown>
      {it.chunks.map((c, i) => (
        <div key={i} className="practice-chunk">
          {c.text && <div className="practice-thinking"><span className="muted small">Your thinking</span><p>{c.text}</p></div>}
          {!c.text && c.askedHint && <p className="muted small">You asked for a hint.</p>}
          {c.verdict && (
            <div className={`check-result ${VERDICT[c.verdict]?.cls ?? ''}`}>
              <strong>{VERDICT[c.verdict]?.label}.</strong> <Markdown inline>{c.feedback ?? ''}</Markdown>
              {c.hint && <div className="practice-hint"><span className="eyebrow">Hint</span> <Markdown inline>{c.hint}</Markdown></div>}
            </div>
          )}
        </div>
      ))}
      {open && (
        <>
          <DictationArea value={text} onChange={setText} rows={4} disabled={waiting}
            placeholder="Think out loud: which idea applies, and how? Write as you go; you can send more than once." />
          <div className="row">
            <button className="btn btn-primary" disabled={waiting || !text.trim()} onClick={() => send(false)}>
              {waiting ? 'Reading your thinking…' : 'Send my thinking'}</button>
            <button className="btn" disabled={waiting} onClick={() => send(true)}>I'm stuck: give me a hint</button>
            <span className="spacer" />
            <button className="link small" disabled={waiting} onClick={() => {
              if (window.confirm('Give up and see the solution? It counts as not solved, so the idea comes back sooner.')) act({ type: 'practiceGiveUp', itemId: it.id })
            }}>Give up and show the solution</button>
          </div>
        </>
      )}
      {!open && it.solution && (
        <details open={showSolution} onToggle={e => setShowSolution((e.target as HTMLDetailsElement).open)}>
          <summary className="small">Worked solution</summary>
          <Markdown>{it.solution}</Markdown>
        </details>
      )}
      {it.ideas.length > 0 && <p className="muted small">Ideas: {it.ideas.map(x => x.title).join(', ')}</p>}
    </div>
  )
}
