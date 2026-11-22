import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { getSession, useStore } from '../store'
import Markdown from '../components/Markdown'
import ThinkingInput, { DictationArea, NO_REASONING, ReasoningShown, type Reasoning } from '../components/ThinkingInput'
import { SourceStatus } from '../components/Sources'
import type { SessionIdea, SessionItem, SessionQuestion, SessionView } from '../types'

const STEPS = [
  { id: 'sketching', label: 'Map the topic' }, { id: 'probing', label: 'What you know' }, { id: 'planning', label: 'Plan' },
  { id: 'teaching', label: 'Learn' }, { id: 'extracting', label: 'Add to your graph' }, { id: 'done', label: 'Done' },
]
const BUSY: Record<string, string> = {
  sketching: 'Mapping the topic and connecting it to what you already know…',
  probing: 'Reading your answers and choosing the next questions…',
  teaching: 'Writing the next step for you…',
  extracting: 'Writing what you learned into your knowledge graph…',
}
const NODE_STATE: Record<string, string> = {
  learned: 'pill pill-ok', mastered: 'pill pill-ok', learning: 'pill pill-warn', rusty: 'pill pill-warn',
}

/** "Teach me X": study anything, with or without a goal (SPEC §22). */
export default function Study() {
  const { id } = useParams()
  return id ? <SessionPage id={id} /> : <StartStudy />
}

function StartStudy() {
  const { s, dispatch } = useStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [topic, setTopic] = useState(() => (location.state as { topic?: string } | null)?.topic ?? '')
  const [picked, setPicked] = useState<string[]>([])
  const [starting, setStarting] = useState<string | null | undefined>(undefined)
  useEffect(() => {
    if (starting !== undefined && s.lastSession && s.lastSession !== starting) navigate(`/study/${s.lastSession}`)
  }, [s.lastSession, starting, navigate])
  const ready = s.sources.filter(x => x.status === 'ready')
  const start = async () => {
    setStarting(s.lastSession)
    if (!await dispatch({ type: 'startSession', topic, sourceIds: picked })) setStarting(undefined)
  }
  return (
    <div className="page page-narrow">
      <h1>Study</h1>
      <p className="lead">Learn anything, with or without a goal. DSC maps the topic, connects it to what you already know,
        checks what you hold, and then teaches one small step at a time: you predict, it explains, you check. What you learn
        goes into your knowledge graph.</p>
      <div className="card">
        <label className="field">
          <span className="small muted">What do you want to learn?</span>
          <DictationArea value={topic} onChange={setTopic} rows={2}
            placeholder="For example: how attention works in transformers, from the math up" />
        </label>
        {ready.length > 0 && (
          <details className="study-sources">
            <summary className="small">Use my sources ({picked.length} chosen)</summary>
            {ready.map(src => (
              <label key={src.id} className="row small">
                <input type="checkbox" checked={picked.includes(src.id)}
                  onChange={e => setPicked(p => e.target.checked ? [...p, src.id] : p.filter(x => x !== src.id))} />
                {src.title} <SourceStatus src={src} />
              </label>
            ))}
          </details>
        )}
        <button className="btn btn-primary" disabled={topic.trim().length < 3 || starting !== undefined} onClick={start}>
          {starting !== undefined ? 'Starting…' : 'Start'}</button>
      </div>
      <StudyBookCard />
      {s.sessions.length > 0 && (
        <>
          <h2>Your sessions</h2>
          <ul className="study-list">
            {s.sessions.map(x => (
              <li key={x.id}><Link to={`/study/${x.id}`}>{x.title}</Link>{' '}
                <span className={x.status === 'done' ? 'pill pill-ok' : 'pill'}>{STEPS.find(t => t.id === x.status)?.label ?? x.status}</span>
                <span className="muted small"> · {new Date(x.createdAt).toLocaleDateString()}</span></li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

/** "Teach me this book" (SPEC §28): pick one PDF; DSC maps it into ideas and teaches it part by part. */
function StudyBookCard() {
  const { s, dispatch } = useStore()
  const navigate = useNavigate()
  const [pick, setPick] = useState('')
  const [waiting, setWaiting] = useState<string | null | undefined>(undefined)
  useEffect(() => {
    if (waiting !== undefined && s.lastBook && s.lastBook !== waiting) navigate(`/book/${s.lastBook}`)
  }, [s.lastBook, waiting, navigate])
  const studied = new Map(s.studyBooks.map(b => [b.sourceId, b]))
  const ready = s.sources.filter(x => x.status === 'ready')
  const go = async () => {
    const old = studied.get(pick)
    if (old) { navigate(`/book/${old.id}`); return }
    setWaiting(s.lastBook)
    if (!await dispatch({ type: 'studyBook', sourceId: pick })) setWaiting(undefined)
  }
  return (
    <>
      <h2>Study a book</h2>
      <div className="card">
        <p className="small muted">Pick one of your PDFs. DSC reads it chapter by chapter, maps its ideas into your knowledge graph
          (joined to what you already know), and then teaches it one part at a time, with the book's own pages.</p>
        {ready.length === 0
          ? <p className="small">Add a PDF in the <Link to="/library">Source library</Link> first.</p>
          : <div className="row">
              <select className="input" value={pick} onChange={e => setPick(e.target.value)} aria-label="Book">
                <option value="">Choose a book…</option>
                {ready.map(x => <option key={x.id} value={x.id}>{x.title}{studied.has(x.id) ? ' (studying)' : ''}</option>)}
              </select>
              <button className="btn btn-primary" disabled={!pick || waiting !== undefined} onClick={go}>
                {studied.has(pick) ? 'Open' : waiting !== undefined ? 'Starting…' : 'Teach me this book'}</button>
            </div>}
        {s.studyBooks.length > 0 && (
          <ul className="study-list">
            {s.studyBooks.map(b => (
              <li key={b.id}><Link to={`/book/${b.id}`}>{b.title}</Link>{' '}
                <span className={b.status === 'ready' ? 'pill' : b.status === 'failed' ? 'pill pill-warn' : 'pill'}>
                  {b.status === 'mapping' ? `mapping ${b.chaptersDone}/${b.chapters}` : b.status === 'failed' ? 'mapping stopped'
                    : `${b.partsDone}/${b.parts} parts done`}</span></li>
            ))}
          </ul>
        )}
      </div>
    </>
  )
}

function SessionPage({ id }: { id: string }) {
  const { s, dispatch } = useStore()
  const navigate = useNavigate()
  const [v, setV] = useState<SessionView | null>(null)
  const [missing, setMissing] = useState(false)
  const [tick, setTick] = useState(0)
  // The store polls fast while jobs run; refetch the session whenever the state changes, or after an action.
  useEffect(() => { getSession(id).then(x => { setV(x); setMissing(false) }, () => setMissing(true)) }, [id, s, tick])
  if (missing) return <div className="page"><p>Session not found. <Link to="/study">Back to Study</Link></p></div>
  if (!v) return <div className="page"><p className="muted">Loading…</p></div>

  const act = async (a: Parameters<typeof dispatch>[0]) => { await dispatch(a); setTick(t => t + 1) }
  const answer = (q: SessionQuestion, choice: number | null, r: Reasoning) =>
    act({ type: 'sessionAnswer', sessionId: v.id, itemId: q.id, choice, ...r })
  const step = STEPS.findIndex(t => t.id === v.status)
  const idea = (k: string) => v.ideas.find(i => i.key === k)
  const probeItems = v.items.filter((i): i is SessionQuestion => i.phase === 'probe')
  const openProbe = probeItems.find(i => !i.answered)
  const lastProbe = [...probeItems].reverse().find(i => i.answered)

  return (
    <div className="page study">
      <div className="row row-between">
        <div>
          <div className="eyebrow">{v.book
            ? <><Link to={`/book/${v.book.id}`}>{v.book.title}</Link> · pp. {v.book.pages[0]}–{v.book.pages[1]}</>
            : 'Study session'}</div>
          <h1>{v.title}</h1>
        </div>
        <button className="link small" onClick={async () => {
          if (window.confirm('Delete this session? Ideas it added stay in your graph only if you answered questions on them.')) {
            await dispatch({ type: 'deleteSession', sessionId: v.id }); navigate('/study')
          }
        }}>Delete session</button>
      </div>
      <ol className="study-steps">
        {STEPS.map((t, n) => <li key={t.id} className={n < step ? 'done' : n === step ? 'now' : ''}>{t.label}</li>)}
      </ol>

      {v.error && (
        <div className="card card-warn">
          <p className="small">The last step failed: {v.error}</p>
          <button className="btn" onClick={() => act({ type: 'sessionRetry', sessionId: v.id })}>Try again</button>
        </div>
      )}
      {v.busy && BUSY[v.status] && <p className="muted study-busy">{BUSY[v.status]}</p>}

      {v.status === 'probing' && (
        <>
          {lastProbe && <QuestionCard q={lastProbe} label="Last answer" />}
          {openProbe && <QuestionCard key={openProbe.id} q={openProbe} label={`Question ${openProbe.round} of at most ${v.probeMax} · ${idea(openProbe.idea)?.title ?? ''}`}
            onAnswer={(c, r) => answer(openProbe, c, r)} allowDunno />}
          {probeItems.filter(i => i.answered).length >= 2 && !v.busy && (
            <button className="link small" onClick={() => act({ type: 'sessionAssessNow', sessionId: v.id })}>Stop asking and show the plan</button>
          )}
        </>
      )}

      {v.status === 'planning' && <PlanView v={v} act={act} />}

      {['teaching', 'extracting', 'done'].includes(v.status) && (
        <div className="study-grid">
          <div className="study-main">
            {v.status === 'done' && !v.items.some(i => i.phase !== 'probe') && (
              <div className="card study-all-known">
                <p><strong>Nothing was taught in this session: you already knew every idea.</strong> Here they are. You can go
                  through them again: you predict, read the explanation and check yourself.</p>
                <ul className="book-ideas">
                  {v.ideas.map(i => (
                    <li key={i.key}><i className={`state-dot state-${i.nodeState}`} />
                      <strong><Markdown inline>{i.title}</Markdown></strong>
                      <span className="muted small study-statement"><Markdown inline>{i.statement}</Markdown></span></li>
                  ))}
                </ul>
                <button className="btn btn-primary" onClick={() => act({ type: 'sessionLearnAgain', sessionId: v.id })}>Learn it again</button>
              </div>
            )}
            {v.status === 'done' && (
              <div className="card card-accent">
                <div className="eyebrow">What you now understand</div>
                <Markdown>{v.summary}</Markdown>
                <p className="muted small">These ideas are now in your knowledge graph. Understanding becomes usable with recall
                  practice, so they show as “learning” until you practise them.</p>
                {v.book && (
                  <div className="row">
                    <Link className="btn" to={`/book/${v.book.id}`}>Back to the book</Link>
                  </div>
                )}
              </div>
            )}
            {v.plan.slice(0, v.current + 1).map((k, n) => (
              <IdeaSteps key={k} n={n + 1} title={idea(k)?.title ?? k} items={v.items.filter(i => i.idea === k && i.phase !== 'probe')}
                sessionId={v.id} onAnswer={answer} />
            ))}
          </div>
          <aside className="study-plan card">
            <div className="eyebrow">Plan · {v.plan.length} ideas</div>
            <ol className="study-plan-list">
              {v.plan.map((k, n) => (
                <li key={k} className={n < v.current || v.status === 'done' ? 'done' : n === v.current ? 'now' : ''}>
                  <i className={`state-dot state-${idea(k)?.nodeState ?? 'ready'}`} /><Markdown inline>{idea(k)?.title ?? k}</Markdown>{idea(k)?.target && <span className="pill small">goal</span>}</li>
              ))}
            </ol>
            {v.ideas.some(i => !v.plan.includes(i.key)) && (
              <p className="muted small">You already hold: {v.ideas.filter(i => !v.plan.includes(i.key)).map(i => i.title).join(', ')}</p>
            )}
          </aside>
        </div>
      )}
    </div>
  )
}

function PlanView({ v, act }: { v: SessionView; act: (a: Parameters<ReturnType<typeof useStore>['dispatch']>[0]) => Promise<void> }) {
  const order = [...v.plan, ...v.ideas.map(i => i.key).filter(k => !v.plan.includes(k))]
  return (
    <div className="card">
      {v.book
        ? <p>The ideas of <strong>{v.book.part}</strong> (pp. {v.book.pages[0]}–{v.book.pages[1]}), and the ideas they build on.
            Untick what you already hold, tick what you want to learn again; each step is short.</p>
        : <p>The path from what you know to <strong>{v.ideas.find(i => i.target)?.title}</strong>. Untick what you already hold;
            each step is short.</p>}
      {v.probeStart && <div className="study-probe-start"><div className="eyebrow">Where to start</div><Markdown>{v.probeStart}</Markdown></div>}
      {v.plan.length === 0 && (
        <div className="study-all-known">
          <p><strong>You already know every idea here.</strong> You can still go through them again: you predict, read the
            explanation and check yourself, and your answers count as practice.</p>
          <button className="btn btn-primary" onClick={() => act({ type: 'sessionLearnAgain', sessionId: v.id })}>Learn it again</button>
        </div>
      )}
      <ul className="study-ideas">
        {order.map(k => {
          const i = v.ideas.find(x => x.key === k)!
          const known = !v.plan.includes(k)
          return (
            <li key={k} className={known ? 'known' : ''}>
              <label className="study-idea-row">
                <input type="checkbox" checked={!known} disabled={i.target}
                  title={known ? 'Tick to learn this idea again' : undefined}
                  onChange={e => act({ type: 'sessionKnown', sessionId: v.id, ideaKey: k, known: !e.target.checked })} />
                <span><strong><Markdown inline>{i.title}</Markdown></strong>{i.target && <span className="pill small"> goal</span>}
                  <span className="muted small study-statement"><Markdown inline>{i.statement}</Markdown></span>
                  {known && <span className="pill pill-ok small">{i.fromGraph && i.level === 'known' ? 'in your graph' : 'you know this'}</span>}
                  {!known && i.again && <span className="pill small">learning again</span>}
                  {!known && i.level === 'partial' && <span className="pill pill-warn small">partly</span>}
                  {i.fromGraph && <span className={NODE_STATE[i.nodeState] ?? 'pill'} title="This idea is already in your knowledge graph"> graph: {i.nodeState}</span>}
                  {i.probe?.level === 'untested' && <span className="pill small" title="No question reached this idea">not tested</span>}
                  <ProbeNote p={i.probe} />
                </span>
              </label>
            </li>
          )
        })}
      </ul>
      {v.plan.length > 0 && <button className="btn btn-primary" onClick={() => act({ type: 'sessionTeach', sessionId: v.id })}>
        Start learning ({v.plan.length} step{v.plan.length === 1 ? '' : 's'})</button>}
    </div>
  )
}

/** What the probe found on one idea: what you reason from, where your reasoning stopped, and wrong beliefs it saw. */
function ProbeNote({ p }: { p: SessionIdea['probe'] }) {
  if (!p || p.level === 'untested' || !(p.reasonsFrom || p.runsOut || p.misconceptions.length)) return null
  return (
    <span className="study-probe-note small">
      {p.reasonsFrom && <span><strong>You reason from:</strong> <Markdown inline>{p.reasonsFrom}</Markdown></span>}
      {p.runsOut && <span><strong>Your reasoning stopped at:</strong> <Markdown inline>{p.runsOut}</Markdown></span>}
      {p.misconceptions.map((m, n) => <span key={n} className="study-misconception"><strong>To fix:</strong> <Markdown inline>{m}</Markdown></span>)}
    </span>
  )
}

function IdeaSteps({ n, title, items, sessionId, onAnswer }: {
  n: number; title: string; items: SessionItem[]; sessionId: string
  onAnswer: (q: SessionQuestion, c: number | null, r: Reasoning) => void
}) {
  return (
    <section className="study-idea">
      <h2>{n}. <Markdown inline>{title}</Markdown></h2>
      {items.map(it => it.phase === 'explain'
        ? <div key={it.id} className={`study-explain reader ${it.repair ? 'repair' : ''}`}>
            {it.repair && <div className="eyebrow">Another way to see it</div>}
            <Markdown runnable={sessionId}>{it.body}</Markdown>
          </div>
        : <QuestionCard key={it.id} q={it} label={it.phase === 'predict' ? 'Predict first' : 'Check'}
            onAnswer={(c, r) => onAnswer(it, c, r)} allowDunno={it.phase === 'predict'} />)}
    </section>
  )
}

function QuestionCard({ q, label, onAnswer, allowDunno }: {
  q: SessionQuestion; label: string; onAnswer?: (choice: number | null, r: Reasoning) => void; allowDunno?: boolean
}) {
  const [choice, setChoice] = useState<number | null>(null)
  const [reasoning, setReasoning] = useState<Reasoning>(NO_REASONING)
  const done = q.answered
  return (
    <div className="check">
      <div className="check-label">{label}</div>
      <Markdown>{q.prompt}</Markdown>
      <div className="check-options" role="radiogroup">
        {q.options.map((o, i) => {
          const cls = ['check-option']
          if ((done ? q.choice : choice) === i) cls.push('selected')
          if (done && i === q.answer) cls.push('correct')
          if (done && q.choice === i && !q.correct) cls.push('wrong')
          return <button key={i} className={cls.join(' ')} disabled={done || !onAnswer} role="radio" aria-checked={choice === i}
            onClick={() => setChoice(i)}><Markdown inline>{o}</Markdown></button>
        })}
      </div>
      {!done && onAnswer && (
        <>
          <ThinkingInput value={reasoning} onChange={setReasoning} />
          <div className="row">
            <button className="btn btn-primary" disabled={choice === null} onClick={() => onAnswer(choice, reasoning)}>Answer</button>
            {allowDunno && <button className="btn" onClick={() => onAnswer(null, reasoning)}>I don't know</button>}
          </div>
        </>
      )}
      {done && (
        <div className={`check-result ${q.correct ? 'ok' : 'bad'}`}>
          <strong>{q.correct ? 'Right.' : q.choice === null ? 'You did not know.' : 'Not quite.'}</strong>{' '}
          {q.explanation && <Markdown inline>{q.explanation}</Markdown>}
          <ReasoningShown thinking={q.thinking} confidence={q.confidence} />
        </div>
      )}
    </div>
  )
}
