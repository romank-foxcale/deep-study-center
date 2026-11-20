import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getSession, useStore } from '../store'
import Markdown from '../components/Markdown'
import ThinkingInput, { DictationArea, NO_REASONING, ReasoningShown, type Reasoning } from '../components/ThinkingInput'
import { SourceStatus } from '../components/Sources'
import type { SessionItem, SessionQuestion, SessionView } from '../types'

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
  const [topic, setTopic] = useState('')
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
        <div><div className="eyebrow">Study session</div><h1>{v.title}</h1></div>
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
          {openProbe && <QuestionCard key={openProbe.id} q={openProbe} label={`Quick question · ${idea(openProbe.idea)?.title ?? ''}`}
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
            {v.status === 'done' && (
              <div className="card card-accent">
                <div className="eyebrow">What you now understand</div>
                <Markdown>{v.summary}</Markdown>
                <p className="muted small">These ideas are now in your knowledge graph. Understanding becomes usable with recall
                  practice, so they show as “learning” until you practise them.</p>
              </div>
            )}
            {v.plan.slice(0, v.current + 1).map((k, n) => (
              <IdeaSteps key={k} n={n + 1} title={idea(k)?.title ?? k} items={v.items.filter(i => i.idea === k && i.phase !== 'probe')}
                sessionId={v.id} onAnswer={answer} />
            ))}
          </div>
          <aside className="study-plan card">
            <div className="eyebrow">Plan</div>
            <ol>
              {v.plan.map((k, n) => (
                <li key={k} className={n < v.current || v.status === 'done' ? 'done' : n === v.current ? 'now' : ''}>
                  <Markdown inline>{idea(k)?.title ?? k}</Markdown>{idea(k)?.target && <span className="pill small">goal</span>}</li>
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
      <p>The path from what you know to <strong>{v.ideas.find(i => i.target)?.title}</strong>. Untick what you already hold;
        each step is short.</p>
      <ul className="study-ideas">
        {order.map(k => {
          const i = v.ideas.find(x => x.key === k)!
          const known = !v.plan.includes(k)
          return (
            <li key={k} className={known ? 'known' : ''}>
              <label className="study-idea-row">
                <input type="checkbox" checked={!known} disabled={i.target || (i.level === 'known' && !i.skip)}
                  onChange={e => act({ type: 'sessionKnown', sessionId: v.id, ideaKey: k, known: !e.target.checked })} />
                <span><strong><Markdown inline>{i.title}</Markdown></strong>{i.target && <span className="pill small"> goal</span>}
                  <span className="muted small study-statement"><Markdown inline>{i.statement}</Markdown></span>
                  {known && <span className="pill pill-ok small">{i.fromGraph && i.level === 'known' ? 'in your graph' : 'you know this'}</span>}
                  {!known && i.level === 'partial' && <span className="pill pill-warn small">partly</span>}
                  {i.fromGraph && <span className={NODE_STATE[i.nodeState] ?? 'pill'} title="This idea is already in your knowledge graph"> graph: {i.nodeState}</span>}
                </span>
              </label>
            </li>
          )
        })}
      </ul>
      <button className="btn btn-primary" onClick={() => act({ type: 'sessionTeach', sessionId: v.id })}>
        Start learning ({v.plan.length} step{v.plan.length === 1 ? '' : 's'})</button>
    </div>
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
        ? <div key={it.id} className={`study-explain ${it.repair ? 'repair' : ''}`}>
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
