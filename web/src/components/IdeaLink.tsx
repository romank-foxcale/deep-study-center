import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getIdea } from '../store'
import type { IdeaDetail } from '../types'

// A link to an idea in the knowledge graph inside lesson text: `[softmax](#idea/<id>)` (SPEC §28). Hover (or tap) shows
// where you met the idea (books with pages, sessions, goal lessons) and how it connects. Details are fetched once.

const cache = new Map<string, Promise<IdeaDetail>>()
const load = (id: string) => {
  let p = cache.get(id)
  if (!p) {
    p = getIdea(id)
    p.catch(() => cache.delete(id))
    cache.set(id, p)
  }
  return p
}

const STATE: Record<string, string> = {
  learned: 'pill pill-ok', learning: 'pill pill-warn',
}

export const IDEA_HREF = /^#idea\/([\w-]+)$/

export default function IdeaLink({ id, children }: { id: string; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [pinned, setPinned] = useState(false)
  const [d, setD] = useState<IdeaDetail | null>(null)
  const [error, setError] = useState('')
  const box = useRef<HTMLSpanElement>(null)
  const timer = useRef<number | undefined>(undefined)
  const navigate = useNavigate()
  useEffect(() => {
    if (!open || d) return
    load(id).then(setD, e => setError((e as Error).message))
  }, [open, d, id])
  useEffect(() => {
    if (!pinned) return
    const close = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) { setPinned(false); setOpen(false) } }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [pinned])
  const show = () => { window.clearTimeout(timer.current); setOpen(true) }
  const hide = () => { if (!pinned) timer.current = window.setTimeout(() => setOpen(false), 150) }
  return (
    <span className="idea-link" ref={box} onMouseEnter={show} onMouseLeave={hide}>
      <a href={`#idea/${id}`} className="idea-ref" onClick={e => { e.preventDefault(); setPinned(p => !p); setOpen(true) }}
        aria-expanded={open}>{children}</a>
      {open && (
        <span className="idea-card" role="dialog">
          {!d && !error && <span className="muted small">Loading…</span>}
          {error && <span className="error small">{error}</span>}
          {d && <>
            <span className="row idea-card-head">
              <strong>{d.title}</strong>
              <span className={STATE[d.state] ?? 'pill'}>{d.state}</span>
            </span>
            <span className="idea-card-statement">{d.statement}</span>
            {d.books.length > 0 && <span className="idea-card-row"><span className="eyebrow">In books</span>
              {d.books.map(b => <Link key={b.id + b.part} to={b.conceptId ? `/lesson/${b.conceptId}` : `/book/${b.id}`}
                title={b.conceptId ? 'Open this lesson' : undefined}>{b.title}{b.pages ? `, p. ${b.pages}` : ''}
                <span className="muted"> · {b.part}</span></Link>)}</span>}
            {d.sessions.length > 0 && <span className="idea-card-row"><span className="eyebrow">Studied in</span>
              {d.sessions.slice(0, 4).map(x => <Link key={x.id} to={`/study/${x.id}`}>{x.title}</Link>)}</span>}
            {d.lessons.length > 0 && <span className="idea-card-row"><span className="eyebrow">Goal lessons</span>
              {d.lessons.slice(0, 3).map(x => <span key={x.id}>{x.title}</span>)}</span>}
            {d.buildsOn.length > 0 && <span className="idea-card-row"><span className="eyebrow">Builds on</span>
              <span>{d.buildsOn.map(x => x.title).join(', ')}</span></span>}
            {d.leadsTo.length > 0 && <span className="idea-card-row"><span className="eyebrow">Leads to</span>
              <span>{d.leadsTo.map(x => x.title).join(', ')}</span></span>}
            <button type="button" className="link small" onClick={() => navigate('/map', { state: { focus: 'all', select: d.id } })}>
              Show on the map</button>
          </>}
        </span>
      )}
    </span>
  )
}
