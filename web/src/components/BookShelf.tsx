import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useStore } from '../store'
import type { StudyBookSummary } from '../types'

/** The shelf of book studies (SPEC §30): a colored spine per book, a ring of known (green) and strong (gold) ideas, and
 *  "Teach me this book" for ready PDFs that are not studied yet. */
export default function BookShelf({ limit, withNew = true }: { limit?: number; withNew?: boolean }) {
  const { s, dispatch } = useStore()
  const navigate = useNavigate()
  const [waiting, setWaiting] = useState<string | null | undefined>(undefined)
  useEffect(() => {
    if (waiting !== undefined && s.lastBook && s.lastBook !== waiting) navigate(`/book/${s.lastBook}`)
  }, [s.lastBook, waiting, navigate])
  const studied = new Set(s.studyBooks.map(b => b.sourceId))
  const fresh = withNew ? s.sources.filter(x => x.status === 'ready' && !studied.has(x.id)) : []
  const books = limit ? s.studyBooks.slice(0, limit) : s.studyBooks
  const teach = async (sourceId: string) => {
    setWaiting(s.lastBook)
    if (!await dispatch({ type: 'studyBook', sourceId })) setWaiting(undefined)
  }
  if (!books.length && !fresh.length) return null
  return (
    <div className="shelf">
      {books.map((b, i) => <BookCard key={b.id} b={b} i={i} />)}
      {fresh.slice(0, limit ? Math.max(0, limit - books.length) : undefined).map(x => (
        <div key={x.id} className="card shelf-card shelf-new">
          <div className="eyebrow">{x.author || 'Not studied yet'}</div>
          <h3>{x.title}</h3>
          <p className="small muted">{x.pages} pages · DSC maps it chapter by chapter in about 10 minutes.</p>
          <button className="btn btn-small btn-primary" disabled={waiting !== undefined} onClick={() => teach(x.id)}>
            {waiting !== undefined ? 'Starting…' : 'Teach me this book'}</button>
        </div>
      ))}
    </div>
  )
}

function BookCard({ b, i }: { b: StudyBookSummary; i: number }) {
  const known = b.ideas ? Math.round((b.known / b.ideas) * 100) : 0
  const strong = b.ideas ? Math.round((b.strong / b.ideas) * 100) : 0
  return (
    <Link to={`/book/${b.id}`} className="card shelf-card" style={{ ['--spine' as string]: `var(--c-${(i % 6) + 1})` }}>
      <div className="row shelf-head">
        <div className="shelf-title">
          <div className="eyebrow">{b.author || 'Book'}</div>
          <h3>{b.title}</h3>
        </div>
        <span className="ring" style={{ ['--known' as string]: known, ['--strong' as string]: strong }} aria-label={`${known}% known`}>
          <span>{known}%</span></span>
      </div>
      {b.status === 'ready'
        ? <div className="row small muted"><span>{b.partsDone}/{b.parts} parts</span><span>{b.known}/{b.ideas} ideas</span>
            <span className="row-tight"><i className="state-dot state-mastered" /> {b.strong} strong</span></div>
        : <div className="small muted">{b.status === 'mapping' ? `Mapping: chapter ${Math.min(b.chaptersDone + 1, b.chapters)} of ${b.chapters}…`
            : `Mapping stopped at chapter ${b.chaptersDone + 1}`}</div>}
    </Link>
  )
}
