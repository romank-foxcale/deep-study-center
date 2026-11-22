import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getBook, getGraph, useStore } from '../store'
import Markdown from '../components/Markdown'
import MapCanvas from '../components/MapCanvas'
import RemapChapter from '../components/RemapChapter'
import type { BookChapter, BookLesson, BookView, GraphView } from '../types'

export const STATE_LABEL: Record<string, string> = {
  mastered: 'know strongly', learned: 'learned', learning: 'learning', rusty: 'due for review', ready: 'ready to learn', locked: 'new', pending: 'new',
}
const LEGEND = ['mastered', 'learned', 'learning', 'rusty', 'ready']
export const KNOWN = new Set(['learned', 'mastered', 'rusty'])
const EMPTY = new Set<string>()

/** The book page (SPEC §31): chapters you can open and close, each with its summary and its lessons, the lesson to
 * continue with, and the book's own map. Every lesson stays open, whatever you already know. */
export default function Book() {
  const { id = '' } = useParams()
  const { s, dispatch } = useStore()
  const navigate = useNavigate()
  const [v, setV] = useState<BookView | null>(null)
  const [g, setG] = useState<GraphView | null>(null)
  const [missing, setMissing] = useState(false)
  const [open, setOpen] = useState<Record<number, boolean>>({})
  const [going, setGoing] = useState<string | null | undefined>(undefined)
  const [confirm, setConfirm] = useState(false)

  useEffect(() => { getBook(id).then(setV, () => setMissing(true)) }, [id, s])
  useEffect(() => { getGraph().then(setG, () => {}) }, [id, s.studyBooks])
  useEffect(() => {  // poll while the map is being made or a chapter is being written
    if (!v?.busy && !v?.chapters.some(c => c.writing)) return
    const t = setInterval(() => getBook(id).then(setV, () => {}), 3000)
    return () => clearInterval(t)
  }, [v?.busy, v?.chapters, id])
  useEffect(() => {
    if (going !== undefined && s.lastPractice && s.lastPractice !== going) navigate(`/practice/${s.lastPractice}`)
  }, [s.lastPractice, going, navigate])

  const mine = useMemo(() => (g ? g.nodes.filter(n => n.books.includes(id)).map(n => n.cluster === `book:${id}` ? n
    : { ...n, cluster: `book:${id}`, also: [n.cluster, ...n.also.filter(a => a !== `book:${id}`)] }) : []), [g, id])
  const mineIds = useMemo(() => new Set(mine.map(n => n.id)), [mine])
  const myLinks = useMemo(() => (g ? g.links.filter(l => mineIds.has(l.src) && mineIds.has(l.dst)) : []), [g, mineIds])
  const myClusters = useMemo(() => g?.clusters ?? [], [g])

  // the chapter of the next lesson starts open
  const nextChapter = v?.chapters.find(c => c.lessons.some(x => x.conceptId === v.next))?.chapter
  useEffect(() => {
    if (nextChapter !== undefined) setOpen(o => (Object.keys(o).length ? o : { [nextChapter]: true }))
  }, [nextChapter])

  if (missing) return <div className="page"><p>Book not found. <Link to="/books">Back to Books</Link></p></div>
  if (!v) return <div className="page"><p className="muted">Loading…</p></div>

  const homework = (ch: BookChapter) => {
    setGoing(s.lastPractice)
    void dispatch({ type: 'bookHomework', bookId: v.id, chapter: ch.chapter })
  }
  const all = v.chapters.flatMap(c => c.lessons)
  const count = (st: string) => all.filter(x => x.state === st).length
  const known = all.filter(x => KNOWN.has(x.state)).length
  const next = all.find(x => x.conceptId === v.next)
  const nextCh = v.chapters.find(c => c.chapter === nextChapter)
  const author = s.studyBooks.find(b => b.id === v.id)?.author

  if (v.version === 1) return (
    <div className="page">
      <div className="eyebrow"><Link to="/books">Books</Link></div>
      <h1>{v.title}</h1>
      <div className="card">
        <p>This book was mapped by an older version, as parts for study sessions. Map it again as chapters of saved lessons.
          Your sessions and what you know stay.</p>
        <button className="btn btn-primary" onClick={() => dispatch({ type: 'studyBook', sourceId: v.sourceId })}>Map it as lessons</button>
      </div>
    </div>
  )

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
            ? <span className="row small"><span className="muted">Remove this book study and its saved lessons? Ideas you answered questions on stay.</span>
                <button className="btn btn-small" onClick={async () => { await dispatch({ type: 'deleteBook', bookId: v.id }); navigate('/books') }}>Remove</button>
                <button className="link small" onClick={() => setConfirm(false)}>Keep</button></span>
            : <button className="link small" onClick={() => setConfirm(true)}>Remove</button>}
        </div>
      </div>
      <div className="row small muted book-stats">
        <span><b className="text">{known}</b> of {all.length} lessons known</span>
        <span className="row-tight"><i className="state-dot state-mastered" /> <b className="text">{count('mastered')}</b> strong</span>
        <span>{v.chapterCount} chapters</span>
      </div>
      <div className="bar bar-stack" aria-hidden>
        {['mastered', 'learned', 'rusty', 'learning'].map(st => <span key={st} className={`state-bg-${st}`} style={{ width: `${all.length ? (count(st) / all.length) * 100 : 0}%` }} />)}
      </div>

      {v.status !== 'ready' && (
        <div className={`card ${v.status === 'failed' && !v.busy ? 'card-warn' : ''}`}>
          {v.busy
            ? <p>Reading the book and cutting it into lessons: chapter {Math.min(v.chaptersDone + 1, v.chapterCount)} of {v.chapterCount}.
                <span className="muted small"> {v.progress}</span> You can open the chapters that are ready.</p>
            : <><p className="small">Mapping stopped at chapter {v.chaptersDone + 1}: {v.error ?? 'unknown error'}</p>
                <button className="btn" onClick={() => dispatch({ type: 'bookRetry', bookId: v.id })}>Continue mapping</button></>}
        </div>
      )}

      <div className="book-grid">
        <div className="book-left">
          {next && nextCh && (
            <div className="card continue-card">
              <div className="eyebrow">{next.started ? 'Continue' : 'Next'} · {nextCh.title}</div>
              <h2><Markdown inline>{next.title}</Markdown></h2>
              <p className="muted small">pp. {pageRange(next.pages)}{next.covers ? ` · ` : ''}<Markdown inline>{next.covers}</Markdown></p>
              <div className="row"><Link className="btn btn-primary" to={`/lesson/${next.conceptId}`}>{next.started ? 'Continue' : 'Start this lesson'}</Link>
                <Link className="btn" to={`/book/${v.id}/chapter/${nextCh.chapter}`}>The chapter</Link></div>
            </div>
          )}
          {v.chapters.map(ch => {
            const k = ch.lessons.filter(x => KNOWN.has(x.state)).length
            const isOpen = !!open[ch.chapter]
            return (
              <section key={ch.chapter} className={`book-ch${isOpen ? ' book-ch-open' : ''}${ch.kind === 'reference' ? ' book-ch-ref' : ''}`}>
                <button className="book-ch-head" onClick={() => setOpen(o => ({ ...o, [ch.chapter]: !o[ch.chapter] }))} aria-expanded={isOpen}>
                  <span className="book-ch-num">{String(ch.chapter).padStart(2, '0')}</span>
                  <span className="book-ch-title">{ch.title}</span>
                  <span className="book-dots">{ch.lessons.map(x => <i key={x.id} className={`state-dot state-${x.state}`} title={`${x.title} · ${STATE_LABEL[x.state] ?? x.state}`} />)}</span>
                  <span className="muted small book-ch-count">{!ch.mapped ? 'mapping…' : ch.kind === 'reference' ? 'reference' : `${k}/${ch.lessons.length}`}</span>
                  <span className="book-ch-caret" aria-hidden>{isOpen ? '▾' : '▸'}</span>
                </button>
                {isOpen && (
                  <div className="book-ch-body">
                    {ch.summary && <div className="book-ch-summary"><Markdown>{ch.summary}</Markdown></div>}
                    {ch.kind === 'reference' && <p className="small muted">Reference material (pp. {pageRange(ch.pages)}): looked up, not studied,
                      so it has no lessons. Lessons link the terms you meet elsewhere.</p>}
                    <LessonList lessons={ch.lessons} next={v.next} />
                    <div className="row small">
                      <Link className="btn btn-small" to={`/book/${v.id}/chapter/${ch.chapter}`}>Open the chapter</Link>
                      {k > 0 && <button className="btn btn-small" onClick={() => homework(ch)} title="Recall practice on this chapter's lessons">Homework</button>}
                      {ch.writing && <span className="muted">Writing this chapter's lessons from the book…</span>}
                      <span className="muted">pp. {pageRange(ch.pages)}</span>
                      <span className="spacer" />
                      <RemapChapter bookId={v.id} ch={ch} busy={v.busy || ch.writing} />
                    </div>
                  </div>
                )}
              </section>
            )
          })}
        </div>
        <aside className="book-right">
          <div className="book-map">
            {mine.length > 0
              ? <MapCanvas view="territory" nodes={mine} links={myLinks} clusters={myClusters} selected={null} matches={EMPTY} center={null} compact
                  onSelect={nid => navigate('/map', { state: { focus: `book:${v.id}`, select: nid } })} />
              : <p className="muted small book-map-empty">The book's lessons appear here once a chapter is mapped.</p>}
          </div>
          <div className="legend small">{LEGEND.map(st => <span key={st}><i className={`state-dot state-${st}`} /> {STATE_LABEL[st]}</span>)}</div>
          <p className="small muted">Each hex is one lesson. Lit hexes are what you know, gold is what you know strongly. A second-color edge
            marks a lesson that another book also teaches.</p>
        </aside>
      </div>
    </div>
  )
}

export function pageRange(p: [number, number]) {
  return p[0] === p[1] ? `${p[0]}` : `${p[0]}–${p[1]}`
}

/** A chapter's lessons: what each covers, its pages, its state, links to other books, and Open / Open again. */
export function LessonList({ lessons, next, full }: { lessons: BookLesson[]; next: string | null; full?: boolean }) {
  return (
    <ol className="book-lessons">
      {lessons.map((x, n) => {
        const known = KNOWN.has(x.state)
        return (
          <li key={x.id} className={`book-lesson${x.conceptId === next ? ' book-lesson-next' : ''}${known ? ' book-lesson-known' : ''}`}>
            <span className="book-lesson-num">{n + 1}</span>
            <div className="book-lesson-main">
              <Link className="book-lesson-title" to={`/lesson/${x.conceptId}`}><Markdown inline>{x.title}</Markdown></Link>
              <span className="muted small"> · pp. {pageRange(x.pages)}</span>
              {x.covers && <div className="small book-lesson-covers"><Markdown inline>{x.covers}</Markdown></div>}
              {full && x.ideas.length > 0 && <div className="small muted">{x.ideas.join(' · ')}</div>}
              {x.alsoIn.length > 0 && <div className="small book-lesson-also">Also in {x.alsoIn.map((b, i) => (
                <span key={b.id}>{i > 0 && ', '}<Link to={`/book/${b.id}`}>{b.title}</Link></span>))}</div>}
            </div>
            <span className="book-lesson-side">
              <span className={`pill small state-pill-${x.state}`}><i className={`state-dot state-${x.state}`} /> {STATE_LABEL[x.state] ?? x.state}</span>
              <Link className={`btn btn-small${x.conceptId === next ? ' btn-primary' : ''}`} to={`/lesson/${x.conceptId}`}
                title={x.written ? 'The lesson is saved: it opens as you left it' : 'Written from the book when you open it'}>
                {known ? 'Open again' : x.started ? 'Continue' : 'Open'}</Link>
            </span>
          </li>
        )
      })}
    </ol>
  )
}
