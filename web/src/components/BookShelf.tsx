import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useStore } from '../store'
import { areaColor } from '../areaColors'
import { DeleteSource, TrashIcon, kindLabel, matches, sourceUrl, type SourceQuery } from './Sources'
import type { SourceDoc, StudyBookSummary } from '../types'

/** The shelf (SPEC §30, §40): books being studied (a spine in the book's map color, a ring of known and strong ideas),
 *  PDFs not studied yet ("Teach me this book"), links, and "Custom" study topics ("teach me X" with no document).
 *  ``q`` filters the cards; every card has a trash can. */
export default function BookShelf({ limit, withNew = true, q }: { limit?: number; withNew?: boolean; q?: SourceQuery }) {
  const { s, dispatch } = useStore()
  const navigate = useNavigate()
  const [waiting, setWaiting] = useState<string | null | undefined>(undefined)
  useEffect(() => {
    if (waiting !== undefined && s.lastBook && s.lastBook !== waiting) navigate(`/book/${s.lastBook}`)
  }, [s.lastBook, waiting, navigate])
  const srcOf = new Map(s.sources.map(x => [x.id, x]))
  const ok = (kind: string, ...f: string[]) => !q || matches(q, kind, ...f)
  const studied = new Set(s.studyBooks.map(b => b.sourceId))
  const books = s.studyBooks.filter(b => ok(b.kind, b.title, b.author, srcOf.get(b.sourceId)?.filename ?? ''))
  const fresh = withNew ? s.sources.filter(x => !x.url && x.status === 'ready' && !studied.has(x.id) && ok(x.kind, x.title, x.author, x.filename)) : []
  const links = withNew ? s.sources.filter(x => x.url && ok(x.kind, x.title, x.author, x.url)) : []
  const custom = withNew ? s.sessions.filter(x => ok('custom', x.title, x.topic)) : []
  const teach = async (sourceId: string) => {
    setWaiting(s.lastBook)
    if (!await dispatch({ type: 'studyBook', sourceId })) setWaiting(undefined)
  }
  const shown = limit ? books.slice(0, limit) : books
  if (!shown.length && !fresh.length && !links.length && !custom.length) {
    return q && (q.text || q.kinds.length) ? <p className="muted">Nothing matches the search.</p> : null
  }
  return (
    <div className="shelf">
      {shown.map(b => <BookCard key={b.id} b={b} src={srcOf.get(b.sourceId)} />)}
      {fresh.slice(0, limit ? Math.max(0, limit - shown.length) : undefined).map(x => (
        <div key={x.id} className="card shelf-card shelf-new">
          <div className="row shelf-head">
            <div className="eyebrow">{kindLabel(x.kind)} · not studied yet</div>
            <DeleteSource src={x} icon />
          </div>
          <h3>{x.title}</h3>
          <p className="small muted">{x.author ? `${x.author} · ` : ''}{x.pages} pages · DSC maps it chapter by chapter in about 10 minutes.</p>
          <button className="btn btn-small btn-primary" disabled={waiting !== undefined} onClick={() => teach(x.id)}>
            {waiting !== undefined ? 'Starting…' : 'Teach me this book'}</button>
        </div>
      ))}
      {links.map(x => <LinkCard key={x.id} x={x} />)}
      {custom.map(x => (
        <Link key={x.id} to={`/study/${x.id}`} className="card shelf-card" style={{ ['--spine' as string]: areaColor(-1) }}>
          <div className="row shelf-head">
            <div className="eyebrow">Custom · teach me</div>
            <button className="icon-btn" aria-label={`Delete ${x.title}`} title="Delete" onClick={e => {
              e.preventDefault(); e.stopPropagation()
              if (window.confirm(`Delete the study topic “${x.title}”? What you learned stays on the map.`)) dispatch({ type: 'deleteSession', sessionId: x.id })
            }}><TrashIcon /></button>
          </div>
          <h3>{x.title}</h3>
          <div className="small muted">{x.status === 'done' ? 'Done' : 'In progress'} · started {new Date(x.createdAt).toLocaleDateString()}</div>
        </Link>
      ))}
    </div>
  )
}

function LinkCard({ x }: { x: SourceDoc }) {
  return (
    <a href={sourceUrl(x)} target="_blank" rel="noreferrer" className="card shelf-card" style={{ ['--spine' as string]: areaColor(-1) }}>
      <div className="row shelf-head">
        <div className="eyebrow">{kindLabel(x.kind)}</div>
        <DeleteSource src={x} icon />
      </div>
      <h3>{x.title}</h3>
      <div className="small muted src-sub">{x.url}</div>
    </a>
  )
}

function BookCard({ b, src }: { b: StudyBookSummary; src?: SourceDoc }) {
  const known = b.ideas ? Math.round((b.known / b.ideas) * 100) : 0
  const strong = b.ideas ? Math.round((b.strong / b.ideas) * 100) : 0
  return (
    <Link to={`/book/${b.id}`} className="card shelf-card" style={{ ['--spine' as string]: areaColor(b.color) }}>
      <div className="row shelf-head">
        <div className="shelf-title">
          <div className="eyebrow">{[kindLabel(b.kind), b.author].filter(Boolean).join(' · ')}</div>
          <h3>{b.title}</h3>
        </div>
        <div className="shelf-side">
          <span className="ring" style={{ ['--known' as string]: known, ['--strong' as string]: strong }} aria-label={`${known}% known`}>
            <span>{known}%</span></span>
          {src && <DeleteSource src={src} icon />}
        </div>
      </div>
      {b.status === 'ready'
        ? <div className="row small muted"><span>{b.partsDone}/{b.parts} parts</span><span>{b.known}/{b.ideas} ideas</span>
            <span className="row-tight"><i className="state-dot state-mastered" /> {b.strong} strong</span></div>
        : <div className="small muted">{b.status === 'mapping' ? `Mapping: chapter ${Math.min(b.chaptersDone + 1, b.chapters)} of ${b.chapters}…`
            : `Mapping stopped at chapter ${b.chaptersDone + 1}`}</div>}
    </Link>
  )
}
