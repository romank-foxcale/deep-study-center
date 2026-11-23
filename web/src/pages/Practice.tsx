import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { getPractice, getPracticeDue, getPracticeTargets, useStore } from '../store'
import Markdown from '../components/Markdown'
import { DictationArea } from '../components/ThinkingInput'
import type { PracticeDue, PracticeItem, PracticeTargets, PracticeView } from '../types'

const VERDICT: Record<string, { label: string; cls: string }> = {
  solved: { label: 'Solved', cls: 'ok' }, progress: { label: 'On track', cls: 'ok' },
  stuck: { label: 'Stuck', cls: 'bad' }, wrong: { label: 'Not this way', cls: 'bad' },
}
const MODE: Record<string, string> = { recall: 'Recall', tell_apart: 'Tell apart', combine: 'Combine' }
type Tab = 'book' | 'field' | 'weak' | 'own'

/** Practice (SPEC §24, §44): problems that make what you understand usable. */
export default function Practice() {
  const { id } = useParams()
  return id ? <PracticeRun id={id} /> : <StartPractice />
}

/** Pick what to practise: lessons and their parts, formulas by field, the weakest ideas, or your own problem. */
function StartPractice() {
  const { s, dispatch } = useStore()
  const navigate = useNavigate()
  const location = useLocation()
  const preset = (location.state as { nodeIds?: string[]; title?: string } | null) ?? null
  const [due, setDue] = useState<PracticeDue | null>(null)
  const [t, setT] = useState<PracticeTargets | null>(null)
  const [tab, setTab] = useState<Tab>('book')
  const [ideas, setIdeas] = useState<Set<string>>(() => new Set(preset?.nodeIds ?? []))
  const [parts, setParts] = useState<Record<string, string[]>>({})
  const [formulas, setFormulas] = useState<Set<string>>(new Set())
  const [count, setCount] = useState(5)
  const [surface, setSurface] = useState('mixed')
  const [own, setOwn] = useState('')
  const [src, setSrc] = useState({ id: '', page: '' })
  const [starting, setStarting] = useState<string | null | undefined>(undefined)
  useEffect(() => { getPracticeDue().then(setDue, () => setDue(null)) }, [s])
  useEffect(() => { getPracticeTargets().then(setT, () => setT({ books: [], fields: [], weakest: [] })) }, [])
  useEffect(() => {
    if (starting !== undefined && s.lastPractice && s.lastPractice !== starting) navigate(`/practice/${s.lastPractice}`)
  }, [s.lastPractice, starting, navigate])
  const start = async (a: Omit<Extract<Parameters<typeof dispatch>[0], { type: 'startPractice' }>, 'type'>) => {
    setStarting(s.lastPractice)
    if (!await dispatch({ type: 'startPractice', ...a })) setStarting(undefined)
  }
  const titleOf = useMemo(() => {
    const m = new Map<string, string>()
    t?.books.forEach(b => b.chapters.forEach(c => c.lessons.forEach(l => m.set(l.nodeId, l.title))))
    t?.weakest.forEach(w => m.set(w.nodeId, w.title))
    return m
  }, [t])
  const toggle = (set: Set<string>, ids: string[], on: boolean) => {
    const n = new Set(set)
    ids.forEach(i => (on ? n.add(i) : n.delete(i)))
    return n
  }
  const setLessons = (ids: string[], on: boolean) => {
    setIdeas(x => toggle(x, ids, on))
    if (!on) setParts(p => Object.fromEntries(Object.entries(p).filter(([k]) => !ids.includes(k))))
  }
  const togglePart = (nid: string, part: string) => {
    setParts(p => {
      const cur = new Set(p[nid] ?? [])
      if (cur.has(part)) cur.delete(part)
      else cur.add(part)
      return { ...p, [nid]: [...cur] }
    })
    setIdeas(x => toggle(x, [nid], true))
  }
  const nParts = Object.values(parts).reduce((n, v) => n + v.length, 0)
  const empty = ideas.size === 0 && formulas.size === 0
  const ready = s.sources.filter(x => x.status === 'ready')
  const title = [...ideas].slice(0, 3).map(i => titleOf.get(i) ?? i).join(', ') + (ideas.size > 3 ? ` and ${ideas.size - 3} more` : '')
    || (formulas.size ? `${formulas.size} formula${formulas.size > 1 ? 's' : ''}` : '')

  return (
    <div className="page page-wide">
      <div className="row row-between">
        <div><div className="eyebrow">Recall</div><h1>Practice</h1></div>
        {due && due.dueCount > 0 && <button className="pill" disabled={starting !== undefined} onClick={() => start({})}
          title="Practise what is due now"><i className="state-dot state-rusty" /> {due.dueCount} idea{due.dueCount === 1 ? '' : 's'} due · practise them</button>}
      </div>
      <p className="lead">Pick what to practise. Each problem makes you find the idea yourself: think out loud, ask for a hint
        one step at a time, and read the solution before you go on. Missed problems come back at the end.</p>

      <div className="practice-grid">
        <div className="card practice-picker">
          <div className="tabs" role="tablist">
            {([['book', 'By book'], ['field', 'By field'], ['weak', 'My weakest'], ['own', 'My own problem']] as [Tab, string][]).map(([k, l]) => (
              <button key={k} role="tab" aria-selected={tab === k} className={`tab${tab === k ? ' on' : ''}`} onClick={() => setTab(k)}>{l}</button>
            ))}
          </div>
          {!t && <p className="muted">Loading…</p>}
          {t && tab === 'book' && (t.books.length === 0 ? <p className="muted">No books yet. <Link to="/books">Add a book</Link>.</p> : (
            <ul className="pk-tree">
              {t.books.map(b => {
                const all = b.chapters.flatMap(c => c.lessons.map(l => l.nodeId))
                return (
                  <li key={b.id}>
                    <details open={b.chapters.some(c => c.lessons.some(l => ideas.has(l.nodeId)))}>
                      <summary><Check on={all.every(i => ideas.has(i))} some={all.some(i => ideas.has(i))} onChange={on => setLessons(all, on)} />
                        <strong>{b.title}</strong></summary>
                      <ul>
                        {b.chapters.map(c => {
                          const ids = c.lessons.map(l => l.nodeId)
                          return (
                            <li key={c.chapter}>
                              <details open={ids.some(i => ideas.has(i))}>
                                <summary><Check on={ids.every(i => ideas.has(i))} some={ids.some(i => ideas.has(i))} onChange={on => setLessons(ids, on)} />
                                  {c.title} <span className="muted small">· {c.lessons.filter(l => l.studied).length}/{c.lessons.length} studied</span></summary>
                                <ul>
                                  {c.lessons.map(l => (
                                    <li key={l.conceptId}>
                                      <details>
                                        <summary className={l.studied ? '' : 'muted'}>
                                          <Check on={ideas.has(l.nodeId)} onChange={on => setLessons([l.nodeId], on)} />
                                          <i className={`state-dot state-${l.state}`} /> <Markdown inline>{l.title}</Markdown>
                                          {!l.studied && <span className="small"> · not studied yet</span>}
                                          {(parts[l.nodeId]?.length ?? 0) > 0 && <span className="pill small">{parts[l.nodeId].length} part{parts[l.nodeId].length > 1 ? 's' : ''}</span>}
                                        </summary>
                                        {l.parts.length > 0 ? (
                                          <ul className="pk-parts">{l.parts.map(p => (
                                            <li key={p}><label><input type="checkbox" checked={!!parts[l.nodeId]?.includes(p)} onChange={() => togglePart(l.nodeId, p)} />
                                              <Markdown inline>{p}</Markdown></label></li>
                                          ))}</ul>
                                        ) : <p className="muted small pk-parts">Not written yet: the whole idea is practised.</p>}
                                      </details>
                                    </li>
                                  ))}
                                </ul>
                              </details>
                            </li>
                          )
                        })}
                      </ul>
                    </details>
                  </li>
                )
              })}
            </ul>
          ))}
          {t && tab === 'field' && (t.fields.length === 0 ? <p className="muted">No formulas sorted into fields yet. Open the map once to sort them.</p> : (
            <ul className="pk-tree">
              {t.fields.map(f => {
                const keys = f.formulas.map(x => x.key)
                return (
                  <li key={f.id}>
                    <details open={keys.some(k => formulas.has(k))}>
                      <summary><Check on={keys.every(k => formulas.has(k))} some={keys.some(k => formulas.has(k))} onChange={on => setFormulas(x => toggle(x, keys, on))} />
                        <strong>{f.title}</strong> <span className="muted small">· {f.formulas.length} formula{f.formulas.length > 1 ? 's' : ''}</span></summary>
                      <ul className="pk-parts">{f.formulas.map(x => (
                        <li key={x.key}><label><input type="checkbox" checked={formulas.has(x.key)} onChange={e => setFormulas(s0 => toggle(s0, [x.key], e.target.checked))} />
                          <span>{x.name}</span> <span className="pk-tex"><Markdown inline>{`$${x.tex}$`}</Markdown></span></label></li>
                      ))}</ul>
                    </details>
                  </li>
                )
              })}
            </ul>
          ))}
          {t && tab === 'weak' && (t.weakest.length === 0 ? <p className="muted">Nothing weak yet: answer some checks first.</p> : (
            <>
              <p className="muted small">Ideas that hold least: low mastery, recent misses, or rusty.</p>
              <ul className="pk-parts">{t.weakest.map(w => (
                <li key={w.nodeId}><label><input type="checkbox" checked={ideas.has(w.nodeId)} onChange={e => setLessons([w.nodeId], e.target.checked)} />
                  <i className={`state-dot state-${w.state}`} /> <Markdown inline>{w.title}</Markdown>
                  <span className="muted small"> · {Math.round(w.mastery * 100)}%{w.misses ? ` · ${w.misses} miss${w.misses > 1 ? 'es' : ''}` : ''}</span></label></li>
              ))}</ul>
              <button className="link small" onClick={() => setLessons(t.weakest.slice(0, 6).map(w => w.nodeId), true)}>Pick the six weakest</button>
            </>
          ))}
          {tab === 'own' && (
            <div className="pk-own">
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
          )}
        </div>

        <div className="practice-side">
          <div className="card practice-session">
            <div className="eyebrow">Your session</div>
            {empty ? <p className="muted small">Nothing picked yet. Tick lessons, parts, formulas or weak ideas.</p> : (
              <p><strong>{ideas.size}</strong> idea{ideas.size === 1 ? '' : 's'}{nParts ? <>, <strong>{nParts}</strong> part{nParts === 1 ? '' : 's'}</> : null}
                {formulas.size ? <>, <strong>{formulas.size}</strong> formula{formulas.size === 1 ? '' : 's'}</> : null}</p>
            )}
            <div className="small muted">Problems</div>
            <div className="row">{[5, 10, 20].map(n => <button key={n} className={`chip${count === n ? ' on' : ''}`} onClick={() => setCount(n)}>{n}</button>)}</div>
            <div className="small muted">Style</div>
            <div className="row">{[['applied', 'Applied'], ['formal', 'Formal'], ['mixed', 'Mixed']].map(([k, l]) => (
              <button key={k} className={`chip${surface === k ? ' on' : ''}`} onClick={() => setSurface(k)}>{l}</button>))}</div>
            <p className="muted small">The first problems are easy, to warm up. Ideas switch from problem to problem. Missed ones come back at the end in a new form.</p>
            <button className="btn btn-primary" disabled={empty || starting !== undefined}
              onClick={() => start({ nodeIds: [...ideas], focus: parts, formulas: [...formulas], count, surface, title })}>
              {starting !== undefined ? 'Starting…' : 'Start practice'}</button>
          </div>
          {s.practices.length > 0 && (
            <div className="card">
              <div className="eyebrow">Earlier practice</div>
              <ul className="plain practice-earlier">{s.practices.slice(0, 8).map(p => (
                <li key={p.id} className="row row-between"><Link to={`/practice/${p.id}`}>{p.title}</Link>
                  <span className="muted small">{p.status === 'done' ? 'done' : p.status} · {new Date(p.createdAt).toLocaleDateString()}</span></li>
              ))}</ul>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/** A checkbox that can show "some" (indeterminate). */
function Check({ on, some = false, onChange }: { on: boolean; some?: boolean; onChange: (on: boolean) => void }) {
  return <input type="checkbox" checked={on} ref={el => { if (el) el.indeterminate = !on && some }}
    onClick={e => e.stopPropagation()} onChange={e => onChange(e.target.checked)} />
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
  const waiting = v.items.find(i => i.status === 'waiting')
  const closed = v.items.filter(i => !['open', 'waiting'].includes(i.status))
  const last = closed[closed.length - 1]
  const done = v.status === 'done'
  const shown = v.items.filter(i => i.status !== 'waiting').length
  return (
    <div className="page page-wide practice">
      <div className="row row-between">
        <div><div className="eyebrow"><Link to="/practice">Practice</Link> · problem {Math.max(1, Math.min(shown, v.count))} of {v.count}
          {v.retests > 0 && ` (${v.retests} retest${v.retests > 1 ? 's' : ''})`}</div><h1>{v.title}</h1></div>
        {!done && <button className="link small" onClick={() => act({ type: 'practiceStop', practiceId: v.id })}>Stop</button>}
      </div>
      <div className="practice-grid">
      <div className="practice-main">
      {v.error && (
        <div className="card card-warn"><p className="small">The last step failed: {v.error}</p>
          <button className="btn" onClick={() => act({ type: 'practiceRetry', practiceId: v.id })}>Try again</button></div>
      )}
      {open && <ProblemCard key={open.id} it={open} busy={v.busy} rungs={v.rungs} act={act} />}
      {!open && !done && last && (
        <>
          <ProblemCard key={last.id} it={last} busy={false} rungs={v.rungs} act={act} />
          <div className="practice-next row">
            <span className="muted small">Read the solution, ask the tutor about it, then go on.</span>
            <span className="spacer" />
            {v.wantNext
              ? <span className="muted small">The next problem opens as soon as it is written…</span>
              : <button className="btn btn-primary" onClick={() => act({ type: 'practiceNext', practiceId: v.id })}>
                  {waiting ? 'Next problem' : v.busy ? 'Next problem (being written)' : 'Next problem'}</button>}
          </div>
        </>
      )}
      {!open && !last && v.busy && <p className="muted">Writing the first problem…</p>}
      {done && (
        <div className="card card-accent">
          <div className="eyebrow">Done</div>
          <p>{closed.filter(i => i.status === 'solved').length} of {closed.length} solved
            {closed.some(i => i.hints > 0) && `, ${closed.reduce((n, i) => n + i.hints, 0)} hint(s)`}
            {v.retests > 0 && `, ${v.retests} retest${v.retests > 1 ? 's' : ''}`}. Each idea is scheduled
            again: sooner when it was hard, later when it was easy.</p>
          <div className="row"><Link className="btn btn-primary" to="/practice">More practice</Link><Link className="btn" to="/map">Knowledge map</Link></div>
        </div>
      )}
      {closed.length > (open || done ? 0 : 1) && <h2>Solved and closed</h2>}
      {[...closed].reverse().filter(it => open || done || it !== last).map(it => <ProblemCard key={it.id} it={it} busy={false} rungs={v.rungs} act={act} />)}
      </div>
      <aside className="card practice-side practice-panel">
        <div className="eyebrow">This run</div>
        <div className="practice-steps" aria-label={`Problem ${shown} of ${v.count}`}>
          {Array.from({ length: v.count }, (_, n) => {
            const it = v.items.filter(i => i.status !== 'waiting')[n]
            const cls = !it ? '' : it.status === 'open' ? 'now' : it.status === 'solved' ? 'ok' : 'bad'
            return <i key={n} className={cls} />
          })}
        </div>
        <div><div className="eyebrow">Level {v.level} of 4</div>
          <div className="practice-level">{[1, 2, 3, 4].map(l => <i key={l} className={l <= v.level ? 'on' : ''} />)}</div>
          <p className="muted small">{v.levelText}. It goes up after a clean solve and down after a hard one.</p></div>
        {(Object.keys(v.focus).length > 0 || v.formulas.length > 0) && <div><div className="eyebrow">Your focus</div>
          <ul className="plain small">
            {Object.values(v.focus).flat().map(p => <li key={p}><Markdown inline>{p}</Markdown></li>)}
            {v.formulas.map(f => <li key={f.tex}>{f.name}</li>)}
          </ul></div>}
        <p className="muted small">Hints go one step at a time, from "look again" to the worked step. A solved problem moves the next
          review of its ideas further out.</p>
      </aside>
      </div>
    </div>
  )
}

function ProblemCard({ it, busy, rungs, act }: {
  it: PracticeItem; busy: boolean; rungs: string[]; act: (a: Parameters<ReturnType<typeof useStore>['dispatch']>[0]) => Promise<void>
}) {
  const [text, setText] = useState('')
  const [showSolution, setShowSolution] = useState(it.status === 'given_up' || it.status === 'solved')
  const open = it.status === 'open'
  const waiting = busy && open
  const send = async (hint: boolean) => { await act({ type: 'practiceSubmit', itemId: it.id, text, hint }); setText('') }
  const top = Math.max(-1, ...it.chunks.map(c => (c.hint ? c.rung ?? 0 : -1)))
  return (
    <div className={`card practice-problem ${it.status}`}>
      <div className="row row-between">
        <div className="row"><span className="eyebrow">{it.title}</span>
          <span className="pill small">{MODE[it.mode] ?? 'Recall'}</span>{it.retest && <span className="pill pill-warn small">Retest</span>}</div>
        {!open && <span className={it.status === 'solved' ? 'pill pill-ok' : 'pill pill-warn'}>
          {it.status === 'solved' ? `solved${it.hints ? `, ${it.hints} hint${it.hints > 1 ? 's' : ''}` : ''}` : it.status === 'given_up' ? 'gave up' : 'skipped'}</span>}
      </div>
      <div className="reader"><Markdown>{it.prompt}</Markdown></div>
      {it.chunks.map((c, i) => (
        <div key={i} className="practice-chunk">
          {c.text && <div className="practice-thinking"><span className="muted small">Your thinking</span><p>{c.text}</p></div>}
          {!c.text && c.askedHint && <p className="muted small">You asked for a hint.</p>}
          {c.verdict && (
            <div className={`check-result ${VERDICT[c.verdict]?.cls ?? ''}`}>
              <strong>{VERDICT[c.verdict]?.label}.</strong> <Markdown inline>{c.feedback ?? ''}</Markdown>
              {c.hint && <div className="practice-hint"><span className="eyebrow">Hint{c.rung != null ? ` · step ${c.rung + 1} of ${rungs.length}: ${rungs[c.rung] ?? ''}` : ''}</span>{' '}
                <Markdown inline>{c.hint}</Markdown></div>}
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
            <button className="btn" disabled={waiting} onClick={() => send(true)}>Give me a hint</button>
            <span className="spacer" />
            <button className="link small" disabled={waiting} onClick={() => {
              if (window.confirm('Give up and see the solution? It counts as not solved, so the idea comes back sooner.')) act({ type: 'practiceGiveUp', itemId: it.id })
            }}>Give up and show the solution</button>
          </div>
          <div className="hint-ladder" title="How much the hints have told you">
            {rungs.map((r, i) => <span key={r} className={i <= top ? 'used' : ''} title={r} />)}
          </div>
        </>
      )}
      {!open && it.solution && (
        <details open={showSolution} onToggle={e => setShowSolution((e.target as HTMLDetailsElement).open)}>
          <summary className="small">Worked solution</summary>
          <Markdown>{it.solution}</Markdown>
        </details>
      )}
      {!open && it.ideas.length > 0 && <p className="muted small">Ideas: {it.ideas.map(x => x.title).join(', ')}</p>}
    </div>
  )
}
