import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { getSession, useStore } from '../store'
import Markdown from '../components/Markdown'
import ThinkingInput, { DictationArea, NO_REASONING, ReasoningShown, type Reasoning } from '../components/ThinkingInput'
import ReasoningReview from '../components/ReasoningReview'
import { SourceStatus } from '../components/Sources'
import SessionPlanGraph, { LEVEL_LABEL, levelOf, type IdeaMark } from '../components/SessionPlanGraph'
import type { SessionExplain, SessionIdea, SessionItem, SessionQuestion, SessionView } from '../types'

const STEPS = [
  { id: 'sketching', label: 'Map the topic' }, { id: 'probing', label: 'What you know' }, { id: 'planning', label: 'Plan' },
  { id: 'teaching', label: 'Learn' }, { id: 'extracting', label: 'Add to your graph' }, { id: 'done', label: 'Done' },
]
const BUSY: Record<string, string> = {
  sketching: 'Mapping the topic and connecting it to what you already know…',
  probing: 'Choosing the next question…',
  teaching: 'Writing this idea for you…',
  extracting: 'Writing what you learned into your knowledge graph…',
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
        checks what you hold, and then teaches one idea at a time: a small example first, then the rule, then your turn. What you learn
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
          (joined to what you already know), and cuts it into lessons by topic that follow the book's own pages.</p>
        {ready.length === 0
          ? <p className="small">Add a PDF in the <Link to="/library">Sources</Link> first.</p>
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
  const [, setRead] = useState(0)
  useEffect(() => { const f = () => setRead(x => x + 1); window.addEventListener('study-read', f); return () => window.removeEventListener('study-read', f) }, [])
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

      {v.status === 'probing' && (() => {
        const answered = probeItems.filter(i => i.answered).length
        return (
          <div className="card study-probe">
            <div className="row row-between">
              <strong>Where you stand</strong>
              <span className="small muted">{openProbe ? `Question ${answered + 1} of at most ${v.probeMax}` : `${answered} answered`}</span>
            </div>
            <div className="study-bar" aria-hidden><i style={{ width: `${Math.min(100, (answered / v.probeMax) * 100)}%` }} /></div>
            <p className="small muted">Usually 4–8 quick questions. It stops early when it knows enough. "I don't know" is a good answer.</p>
            {lastProbe && <QuestionCard q={lastProbe} label="Last answer" />}
            {openProbe && <QuestionCard key={openProbe.id} q={openProbe} label={idea(openProbe.idea)?.title ?? ''}
              onAnswer={(c, r) => answer(openProbe, c, r)} allowDunno />}
            <div className="row row-between">
              <span />
              <button className="btn btn-small" disabled={v.busy && !openProbe} onClick={() => act({ type: 'sessionAssessNow', sessionId: v.id })}>
                Show my plan now</button>
            </div>
          </div>
        )
      })()}

      {v.status === 'planning' && <PlanView v={v} act={act} />}

      {['teaching', 'extracting', 'done'].includes(v.status) && (
        <div className="study-grid">
          <div className="study-main">
            {v.status === 'done' && !v.items.some(i => i.phase !== 'probe') && (
              <div className="card study-all-known">
                <p><strong>Nothing was taught in this session: you already knew every idea.</strong> Here they are. You can go
                  through them again: one quick problem per idea, and a short lesson where you miss.</p>
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
            {v.plan.slice(0, v.status === 'teaching' ? v.current : v.plan.length).length > 0 && (
              <details className="study-done-ideas">
                <summary className="small">Done: {v.plan.slice(0, v.status === 'teaching' ? v.current : v.plan.length).map(k => idea(k)?.title ?? k).join(' · ')}</summary>
                {v.plan.slice(0, v.status === 'teaching' ? v.current : v.plan.length).map(k => (
                  <IdeaLearn key={k} idea={idea(k)} items={v.items.filter(i => i.idea === k && i.phase !== 'probe')} sessionId={v.id} onAnswer={answer} />
                ))}
              </details>
            )}
            {v.status === 'teaching' && v.current < v.plan.length && (
              <IdeaLearn key={v.plan[v.current]} idea={idea(v.plan[v.current])} now
                items={v.items.filter(i => i.idea === v.plan[v.current] && i.phase !== 'probe')} sessionId={v.id} onAnswer={answer} />
            )}
          </div>
          <aside className="study-plan card">
            <div className="eyebrow">Plan · {v.plan.length} ideas · {Math.min(v.current, v.plan.length)} done</div>
            {v.status === 'teaching' && v.canChoose && v.open.length > 1 && (
              <div className="study-open">
                <p className="small muted">These are open now: everything they need is done. Pick the one you want first.</p>
                {v.open.map(k => (
                  <button key={k} className={`study-open-idea${k === v.plan[v.current] ? ' on' : ''}`}
                    onClick={() => k !== v.plan[v.current] && act({ type: 'sessionChoose', sessionId: v.id, ideaKey: k })}>
                    <Markdown inline>{idea(k)?.title ?? k}</Markdown>
                    <span className="small muted"> · {k === v.plan[v.current] ? 'now' : LEVEL_LABEL[levelOf(idea(k)!) === 'new' ? 'unknown' : levelOf(idea(k)!)]}</span>
                  </button>
                ))}
              </div>
            )}
            <SessionPlanGraph small ideas={v.ideas} marks={marksOf(v)} />
          </aside>
        </div>
      )}
    </div>
  )
}

/** What each idea is on the plan graph now. */
function marksOf(v: SessionView): Record<string, IdeaMark> {
  const m: Record<string, IdeaMark> = {}
  for (const i of v.ideas) m[i.key] = 'skip'
  v.plan.forEach((k, n) => {
    m[k] = v.status === 'planning' ? 'later' : n < v.current || v.status !== 'teaching' ? 'done' : n === v.current ? 'now' : v.open.includes(k) ? 'open' : 'later'
  })
  return m
}

function PlanView({ v, act }: { v: SessionView; act: (a: Parameters<ReturnType<typeof useStore>['dispatch']>[0]) => Promise<void> }) {
  const [sel, setSel] = useState<string | null>(() => v.plan[0] ?? v.ideas.find(i => i.target)?.key ?? null)
  const i = v.ideas.find(x => x.key === sel) ?? null
  const inPlan = i ? v.plan.includes(i.key) : false
  const mins = v.plan.reduce((t, k) => t + (levelOf(v.ideas.find(x => x.key === k)!) === 'new' ? 6 : 2), 0)
  return (
    <div className="study-planner">
      {v.book
        ? <p>The ideas of <strong>{v.book.part}</strong> (pp. {v.book.pages[0]}–{v.book.pages[1]}), and the ideas they build on.</p>
        : <p>The path from what you know to <strong>{v.ideas.find(x => x.target)?.title}</strong>. An arrow means "needed for".
            Ideas side by side can be learned in either order. Click a box to see it; skip what you know.</p>}
      {v.probeStart && <div className="study-probe-start"><div className="eyebrow">Where to start</div><Markdown>{v.probeStart}</Markdown></div>}
      <div className="study-plan-grid">
        <div className="card">
          <div className="lp-legend small muted">
            <span><i className="lp-swatch sp-new" />new to you</span><span><i className="lp-swatch sp-partial" />partly known: one problem first</span>
            <span><i className="lp-swatch sp-known" />you know it: skipped</span>
          </div>
          <SessionPlanGraph ideas={v.ideas} marks={marksOf(v)} selected={sel} onSelect={setSel} />
        </div>
        <aside className="card study-plan-side">
          {i ? <>
            <span className={`pill small sp-pill-${inPlan ? levelOf(i) : 'known'}`}>{inPlan ? LEVEL_LABEL[levelOf(i) === 'new' ? 'unknown' : levelOf(i)] : 'skipped'}</span>
            <h3><Markdown inline>{i.title}</Markdown>{i.target && ' ★'}</h3>
            <p className="small"><Markdown inline>{i.statement}</Markdown></p>
            {i.fromGraph && <p className="small muted">This idea is already in your knowledge graph ({i.nodeState}).</p>}
            {i.probe?.level === 'untested' && <p className="small muted">No placement question reached this idea.</p>}
            <ProbeNote p={i.probe} />
            {i.target
              ? <p className="small muted">★ The goal of this session. It is always in the plan.</p>
              : <div className="study-toggle">
                  <button className={`btn btn-small${inPlan ? ' btn-primary' : ''}`} onClick={() => !inPlan && act({ type: 'sessionKnown', sessionId: v.id, ideaKey: i.key, known: false })}>Learn it</button>
                  <button className={`btn btn-small${!inPlan ? ' btn-primary' : ''}`} onClick={() => inPlan && act({ type: 'sessionKnown', sessionId: v.id, ideaKey: i.key, known: true })}>Skip, I know it</button>
                </div>}
          </> : <p className="small muted">Click a box to see what it holds and what placement found.</p>}
        </aside>
      </div>
      {v.plan.length === 0 && (
        <div className="card study-all-known">
          <p><strong>You already know every idea here.</strong> You can still go through them again: one quick problem per idea,
            and a short lesson where you miss. Your answers count as practice.</p>
          <button className="btn btn-primary" onClick={() => act({ type: 'sessionLearnAgain', sessionId: v.id })}>Learn it again</button>
        </div>
      )}
      {v.plan.length > 0 && <div className="row">
        <button className="btn btn-primary" onClick={() => act({ type: 'sessionTeach', sessionId: v.id })}>
          Start learning ({v.plan.length} idea{v.plan.length === 1 ? '' : 's'} · about {mins} min)</button>
      </div>}
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

/** One idea on the Learn step (SPEC §54): its teaching in short parts (one per screen) and its problems, in order.
 *  Whatever comes after a teaching block shows once all its parts are read. */
function IdeaLearn({ idea, items, sessionId, onAnswer, now }: {
  idea?: SessionIdea; items: SessionItem[]; sessionId: string; now?: boolean
  onAnswer: (q: SessionQuestion, c: number | null, r: Reasoning) => void
}) {
  const shown: SessionItem[] = []
  for (const it of items) {  // stop after a teaching block that is still being read
    shown.push(it)
    if (it.phase === 'explain' && now && !items.slice(items.indexOf(it) + 1).some(x => x.phase !== 'explain' && x.answered)
        && readParts(it.id) < it.parts.length) break
  }
  const lv = idea ? levelOf(idea) : 'new'
  return (
    <section className={`study-idea${now ? ' study-idea-now' : ''}`}>
      <div className="row row-between">
        <h2><Markdown inline>{idea?.title ?? ''}</Markdown></h2>
        {now && <span className={`pill small sp-pill-${lv}`}>{LEVEL_LABEL[lv === 'new' ? 'unknown' : lv]}</span>}
      </div>
      {now && items.length > 0 && items[0].phase === 'try' && !items[0].answered && (
        <p className="small muted">Placement says you partly know this. Solve one problem first: if you get it, you move on; if not,
          you get a short lesson on just the part you missed.</p>
      )}
      {shown.map(it => it.phase === 'explain'
        ? <PartsReader key={it.id} it={it} sessionId={sessionId} live={!!now} />
        : <div key={it.id}>
            <QuestionCard q={it} label={it.phase === 'try' ? 'First, one problem' : it.phase === 'predict' ? 'Predict first' : 'Your turn'}
              onAnswer={(c, r) => onAnswer(it, c, r)} allowDunno={it.phase !== 'check'} />
            {it.phase === 'try' && it.answered && it.correct && !!it.summary?.length && (
              <div className="card card-accent study-summary">
                <div className="eyebrow">You hold this idea</div>
                <ul>{it.summary.map((x, n) => <li key={n}><Markdown inline>{x}</Markdown></li>)}</ul>
              </div>
            )}
          </div>)}
    </section>
  )
}

const READ = new Map<number, number>()  // teaching block id -> parts read (kept while the page is open)
function readParts(id: number): number { return READ.get(id) ?? 1 }

/** A teaching block, one part per screen: "Continue" shows the next part; all parts read shows what comes next. */
function PartsReader({ it, sessionId, live }: { it: SessionExplain; sessionId: string; live: boolean }) {
  const [n, setN] = useState(() => (live ? readParts(it.id) : it.parts.length))
  const more = n < it.parts.length
  const next = () => { const k = n + 1; READ.set(it.id, k); setN(k) }
  return (
    <div className={`study-explain reader study-parts${it.repair ? ' repair' : ''}`}>
      {it.kind === 'gap' && <div className="eyebrow">Just the part you missed</div>}
      {it.repair && <div className="eyebrow">Another way to see it</div>}
      {it.parts.slice(0, n).map((p, k) => <div key={k} className="study-part"><Markdown runnable={sessionId}>{p}</Markdown></div>)}
      {it.parts.length > 1 && (
        <div className="row row-between study-part-foot">
          <span className="study-dots" aria-label={`Part ${Math.min(n, it.parts.length)} of ${it.parts.length}`}>
            {it.parts.map((_, k) => <i key={k} className={k < n ? 'on' : ''} />)}</span>
          {more && live && <button className="btn btn-primary btn-small" onClick={() => { next(); window.dispatchEvent(new Event('study-read')) }}>Continue</button>}
        </div>
      )}
    </div>
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
          {q.review && q.thinking
            ? <ReasoningReview review={q.review} thinking={q.thinking} confidence={q.confidence} />
            : <ReasoningShown thinking={q.thinking} confidence={q.confidence} />}
        </div>
      )}
    </div>
  )
}
