import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getBook, useStore } from '../store'
import Markdown from '../components/Markdown'
import type { BookPart, BookView } from '../types'

const STATE: Record<string, string> = {
  learned: 'pill pill-ok', mastered: 'pill pill-ok', learning: 'pill pill-warn', rusty: 'pill pill-warn',
}
const PART: Record<BookPart['status'], string> = { todo: '', studying: 'pill pill-warn', done: 'pill pill-ok' }

/** One book study (SPEC §28): the book's parts, chapter by chapter, with their ideas. A minimal page; the UI comes later. */
export default function Book() {
  const { id = '' } = useParams()
  const { s, dispatch } = useStore()
  const navigate = useNavigate()
  const [v, setV] = useState<BookView | null>(null)
  const [missing, setMissing] = useState(false)
  const [open, setOpen] = useState<Record<number, boolean>>({})
  const [going, setGoing] = useState<{ kind: 'session' | 'practice'; last: string | null } | null>(null)

  useEffect(() => { getBook(id).then(setV, () => setMissing(true)) }, [id, s])
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

  if (missing) return <div className="page"><p>Book not found. <Link to="/study">Back to Study</Link></p></div>
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
  const ideas = v.parts.reduce((n, p) => n + p.ideas.length, 0)
  const done = v.parts.filter(p => p.status === 'done').length
  const next = v.parts.find(p => p.id === v.next)

  return (
    <div className="page book">
      <div className="row row-between">
        <div><div className="eyebrow">Book study</div><h1>{v.title}</h1></div>
        <div className="row">
          <button className="link small" onClick={() => navigate('/map', { state: { focus: `book:${v.id}` } })}>This book on the map</button>
          <button className="link small" onClick={async () => {
            if (window.confirm('Remove this book study? Ideas you answered questions on stay in your graph.')) {
              await dispatch({ type: 'deleteBook', bookId: v.id }); navigate('/study')
            }
          }}>Remove</button>
        </div>
      </div>
      <p className="muted small">{v.parts.length} parts in {v.chapters} chapters · {ideas} ideas · {done} parts done</p>

      {v.status !== 'ready' && (
        <div className={`card ${v.status === 'failed' && !v.busy ? 'card-warn' : ''}`}>
          {v.busy
            ? <p>Reading the book and mapping its ideas: chapter {Math.min(v.chaptersDone + 1, v.chapters)} of {v.chapters}.
                <span className="muted small"> {v.progress}</span> You can study the chapters that are already mapped.</p>
            : <><p className="small">Mapping stopped at chapter {v.chaptersDone + 1}: {v.error ?? 'unknown error'}</p>
                <button className="btn" onClick={() => dispatch({ type: 'bookRetry', bookId: v.id })}>Continue mapping</button></>}
        </div>
      )}

      {next && (
        <div className="card card-accent book-next">
          <div className="eyebrow">Next</div>
          <strong>{next.title}</strong> <span className="muted small">pp. {next.pages[0]}–{next.pages[1]} · {next.ideas.length} ideas</span>
          {next.summary && <p className="small">{next.summary}</p>}
          <button className="btn btn-primary" onClick={() => study(next)}>{next.sessionId ? 'Continue' : 'Study this part'}</button>
        </div>
      )}

      {chapters.map(ch => (
        <section key={ch.n} className="book-chapter">
          <h2>{ch.title}</h2>
          <ul className="book-parts">
            {ch.parts.map(p => (
              <li key={p.id} className={`book-part book-part-${p.status}`}>
                <div className="row row-between">
                  <button className="link book-part-title" onClick={() => setOpen(o => ({ ...o, [p.id]: !o[p.id] }))}
                    aria-expanded={!!open[p.id]}>
                    {p.title} <span className="muted small">pp. {p.pages[0]}–{p.pages[1]} · {p.ideas.length} ideas</span>
                  </button>
                  <span className="row">
                    {p.status !== 'todo' && <span className={PART[p.status]}>{p.status === 'done' ? 'done' : 'studying'}</span>}
                    {p.ideas.length > 0 && <button className="btn btn-small" onClick={() => study(p)}>
                      {p.sessionId ? 'Open' : 'Study'}</button>}
                    {p.status === 'done' && <button className="btn btn-small" onClick={() => homework(p)}
                      title="Recall practice on this part's ideas">Homework</button>}
                  </span>
                </div>
                {open[p.id] && (
                  <div className="book-part-body">
                    {p.summary && <p className="small">{p.summary}</p>}
                    <ul className="book-ideas">
                      {p.ideas.map(i => (
                        <li key={i.id}>
                          <strong><Markdown inline>{i.title}</Markdown></strong>
                          <span className={STATE[i.state] ?? 'pill'}>{i.state}</span>
                          {i.fromGraph && <span className="pill small" title="Already in your graph before this book">in your graph</span>}
                          {i.otherBooks.length > 0 && <span className="pill small">also in {i.otherBooks.length} other book(s)</span>}
                          {i.pages && <span className="muted small"> p. {i.pages}</span>}
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
  )
}
