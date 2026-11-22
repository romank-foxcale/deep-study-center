import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getBook, getGraph, useStore } from '../store'
import Markdown from '../components/Markdown'
import MapCanvas from '../components/MapCanvas'
import type { BookPart, BookView, GraphView } from '../types'

const STATE_LABEL: Record<string, string> = {
  mastered: 'know strongly', learned: 'learned', learning: 'learning', rusty: 'due for review', ready: 'ready to learn', locked: 'needs others first', pending: 'not started',
}
const LEGEND = ['mastered', 'learned', 'learning', 'rusty', 'ready', 'locked']
const KNOWN = new Set(['learned', 'mastered', 'rusty'])
const EMPTY = new Set<string>()

/** One book study (SPEC §28, §30): the parts by chapter with their ideas, the next part, and the book's own map. */
export default function Book() {
  const { id = '' } = useParams()
  const { s, dispatch } = useStore()
  const navigate = useNavigate()
  const [v, setV] = useState<BookView | null>(null)
  const [g, setG] = useState<GraphView | null>(null)
  const [missing, setMissing] = useState(false)
  const [open, setOpen] = useState<Record<number, boolean>>({})
  const [going, setGoing] = useState<{ kind: 'session' | 'practice'; last: string | null } | null>(null)
  const [confirm, setConfirm] = useState(false)

  useEffect(() => { getBook(id).then(setV, () => setMissing(true)) }, [id, s])
  useEffect(() => { getGraph().then(setG, () => {}) }, [id, s.studyBooks])
  useEffect(() => {  // poll while the map is being made
    if (!v?.busy) return
    const t = setInterval(() => getBook(id).then(setV, () => {}), 3000)
    return () => clearInterval(t)
  }, [v?.busy, id])
  useEffect(() => {
    if (!going) return
    const now = going.kind === 'session' ? s.lastSession : s.lastPractice
    if (now && now !== going.last) navigate(going.kind === 'session' ? `/study/${now}` : `/practice/${now}`)
  }, [s.lastSession, s.lastPractice, going, navigate])

  // the book's own ideas, all in this book's country (an idea made by another book keeps that book as its second ring)
  const mine = useMemo(() => (g ? g.nodes.filter(n => n.books.includes(id)).map(n => n.cluster === `book:${id}` ? n
    : { ...n, cluster: `book:${id}`, also: [n.cluster, ...n.also.filter(a => a !== `book:${id}`)] }) : []), [g, id])
  const mineIds = useMemo(() => new Set(mine.map(n => n.id)), [mine])
  const myLinks = useMemo(() => (g ? g.links.filter(l => mineIds.has(l.src) && mineIds.has(l.dst)) : []), [g, mineIds])
  const myClusters = useMemo(() => g?.clusters ?? [], [g])  // all of them: the same colors as the big map, and second rings

  if (missing) return <div className="page"><p>Book not found. <Link to="/books">Back to Books</Link></p></div>
  if (!v) return <div className="page"><p className="muted">Loading…</p></div>

  const study = (p: BookPart) => {
    if (p.sessionId) { navigate(`/study/${p.sessionId}`); return }
    setGoing({ kind: 'session', last: s.lastSession })
    void dispatch({ type: 'bookStudyPart', partId: p.id })
  }
  const homework = (p: BookPart) => {
    setGoing({ kind: 'practice', last: s.lastPractice })
    void dispatch({ type: 'bookHomework', partId: p.id })
  }
  const chapters: { n: number; title: string; parts: BookPart[] }[] = []
  for (const p of v.parts) {
    const last = chapters[chapters.length - 1]
    if (last && last.n === p.chapter) last.parts.push(p)
    else chapters.push({ n: p.chapter, title: p.chapterTitle, parts: [p] })
  }
  const all = v.parts.flatMap(p => p.ideas)
  const count = (st: string) => all.filter(i => i.state === st).length
  const known = all.filter(i => KNOWN.has(i.state)).length
  const done = v.parts.filter(p => p.status === 'done').length
  const next = v.parts.find(p => p.id === v.next)
  const author = s.studyBooks.find(b => b.id === v.id)?.author

  return (
    <div className="page page-wide book">
      <div className="row row-between">
        <div>
          <div className="eyebrow"><Link to="/books">Books</Link>{author ? ` · ${author}` : ''}</div>
          <h1>{v.title}</h1>
        </div>
        <div className="row">
          <button className="btn" onClick={() => navigate('/map', { state: { focus: `book:${v.id}` } })}>On the map</button>
          {confirm
            ? <span className="row small"><span className="muted">Remove this book study? Ideas you answered questions on stay.</span>
                <button className="btn btn-small" onClick={async () => { await dispatch({ type: 'deleteBook', bookId: v.id }); navigate('/books') }}>Remove</button>
                <button className="link small" onClick={() => setConfirm(false)}>Keep</button></span>
            : <button className="link small" onClick={() => setConfirm(true)}>Remove</button>}
        </div>
      </div>
      <div className="row small muted book-stats">
        <span><b className="text">{done}</b> of {v.parts.length} parts done</span>
        <span><b className="text">{known}</b> of {all.length} ideas known</span>
        <span className="row-tight"><i className="state-dot state-mastered" /> <b className="text">{count('mastered')}</b> strong</span>
        <span>{v.chapters} chapters</span>
      </div>
      <div className="bar bar-stack" aria-hidden>
        {['mastered', 'learned', 'rusty', 'learning'].map(st => <span key={st} className={`state-bg-${st}`} style={{ width: `${all.length ? (count(st) / all.length) * 100 : 0}%` }} />)}
      </div>

      {v.status !== 'ready' && (
        <div className={`card ${v.status === 'failed' && !v.busy ? 'card-warn' : ''}`}>
          {v.busy
            ? <p>Reading the book and mapping its ideas: chapter {Math.min(v.chaptersDone + 1, v.chapters)} of {v.chapters}.
                <span className="muted small"> {v.progress}</span> You can study the chapters that are already mapped.</p>
            : <><p className="small">Mapping stopped at chapter {v.chaptersDone + 1}: {v.error ?? 'unknown error'}</p>
                <button className="btn" onClick={() => dispatch({ type: 'bookRetry', bookId: v.id })}>Continue mapping</button></>}
        </div>
      )}

      <div className="book-grid">
        <div className="book-left">
          {next && (
            <div className="card continue-card">
              <div className="eyebrow">{next.sessionId ? 'Continue' : 'Next'}</div>
              <h2><Markdown inline>{next.title}</Markdown></h2>
              <p className="muted small">pp. {next.pages[0]}–{next.pages[1]} · {next.ideas.length} ideas{next.summary ? ` · ${next.summary}` : ''}</p>
              <div className="row"><button className="btn btn-primary" onClick={() => study(next)}>{next.sessionId ? 'Continue' : 'Study this part'}</button></div>
            </div>
          )}
          {chapters.map(ch => (
            <section key={ch.n} className="book-chapter">
              <div className="book-chapter-title">{ch.title}</div>
              <ul className="book-parts">
                {ch.parts.map(p => (
                  <li key={p.id} className={`book-part book-part-${p.status}${p.id === v.next ? ' book-part-next' : ''}`}>
                    <span className="book-part-num">{String(p.ord + 1).padStart(2, '0')}</span>
                    <div className="book-part-main">
                      <button className="link book-part-title" onClick={() => setOpen(o => ({ ...o, [p.id]: !o[p.id] }))} aria-expanded={!!open[p.id]}>
                        <Markdown inline>{p.title}</Markdown></button>
                      <span className="muted small"> pp. {p.pages[0]}–{p.pages[1]} · {p.ideas.length} ideas</span>
                      <div className="book-dots">{p.ideas.map(i => <i key={i.id} className={`state-dot state-${i.state}`} title={`${i.title} · ${STATE_LABEL[i.state] ?? i.state}`} />)}</div>
                    </div>
                    <span className="row book-part-actions">
                      {p.status === 'done' && <span className="pill"><i className="state-dot state-learned" /> done</span>}
                      {p.status === 'studying' && <span className="pill pill-accent">studying</span>}
                      {p.ideas.length > 0 && p.status !== 'done' && <button className={`btn btn-small${p.id === v.next ? ' btn-primary' : ''}`} onClick={() => study(p)}>
                        {p.sessionId ? 'Continue' : 'Study'}</button>}
                      {p.status === 'done' && <><button className="btn btn-small" onClick={() => study(p)}>Open</button>
                        <button className="btn btn-small" onClick={() => homework(p)} title="Recall practice on this part's ideas">Homework</button></>}
                    </span>
                    {open[p.id] && (
                      <div className="book-part-body">
                        {p.summary && <p className="small">{p.summary}</p>}
                        <ul className="book-ideas">
                          {p.ideas.map(i => (
                            <li key={i.id}>
                              <i className={`state-dot state-${i.state}`} />
                              <strong><Markdown inline>{i.title}</Markdown></strong>
                              {i.fromGraph && <span className="pill small" title="Already in your graph before this book">in your graph</span>}
                              {i.otherBooks.length > 0 && <span className="pill small">also in {i.otherBooks.length} other book{i.otherBooks.length > 1 ? 's' : ''}</span>}
                              {i.pages && <span className="muted small">p. {i.pages}</span>}
                              <span className="muted small study-statement"><Markdown inline>{i.statement}</Markdown></span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
        <aside className="book-right">
          <div className="book-map">
            {mine.length > 0
              ? <MapCanvas view="territory" nodes={mine} links={myLinks} clusters={myClusters} selected={null} matches={EMPTY} center={null} compact
                  onSelect={nid => navigate('/map', { state: { focus: `book:${v.id}`, select: nid } })} />
              : <p className="muted small book-map-empty">The book's ideas appear here once a chapter is mapped.</p>}
          </div>
          <div className="legend small">{LEGEND.map(st => <span key={st}><i className={`state-dot state-${st}`} /> {STATE_LABEL[st]}</span>)}</div>
          <p className="small muted">This book's ideas as land: lit hexes are what you know, gold is what you know strongly. Basics sit in the
            middle; a second-color edge marks an idea shared with another book.</p>
        </aside>
      </div>
    </div>
  )
}
