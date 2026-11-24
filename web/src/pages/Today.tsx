import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getGraph, getToday, useStore } from '../store'
import BookShelf from '../components/BookShelf'
import MapCanvas from '../components/MapCanvas'
import ApiKeyCard from '../components/ApiKeyCard'
import Markdown from '../components/Markdown'
import type { GraphView, TodayView } from '../types'

const EMPTY = new Set<string>()

/** Today (SPEC §30): pick up where you stopped, see the week. No schedule (SPEC §48). */
export default function Today() {
  const { s } = useStore()
  const navigate = useNavigate()
  const [t, setT] = useState<TodayView | null>(null)
  const [g, setG] = useState<GraphView | null>(null)
  useEffect(() => { getToday().then(setT, () => {}) }, [s])
  useEffect(() => { getGraph().then(setG, () => {}) }, [s.studyBooks.length, s.sessions.length])
  const links = useMemo(() => g?.links ?? [], [g])
  const hour = new Date().getHours()
  const greet = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'
  const c = t?.continue ?? null
  const empty = !s.studyBooks.length && !s.sessions.length

  return (
    <div className="page page-wide today">
      <div>
        <div className="eyebrow">{new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}</div>
        <h1>{greet}. {c ? 'Pick up where you stopped.' : 'What do you want to understand today?'}</h1>
      </div>
      {!s.providers.some(p => p.detected) && !s.apiKey?.set && <ApiKeyCard compact />}

      {c && (
        <div className="card continue-card">
          <div className="eyebrow">Continue{c.kind === 'session' && c.book ? ` · ${c.book.title}` : c.kind === 'lesson' ? ` · ${c.bookTitle} · ${c.chapterTitle}` : ''}</div>
          <h2><Markdown inline>{c.title}</Markdown></h2>
          {c.kind === 'session' && c.next && <div className="muted">Next idea: <strong className="text"><Markdown inline>{c.next}</Markdown></strong></div>}
          {c.kind === 'session' && !c.next && <p className="muted">{c.status === 'probing' ? 'A few quick questions find what you already know.' : 'Your plan is ready.'}</p>}
          {c.kind === 'lesson' && <div className="muted">{c.pages[0] === c.pages[1] ? `p. ${c.pages[0]}` : `pp. ${c.pages[0]}–${c.pages[1]}`}{c.summary ? ' · ' : ''}<Markdown inline>{c.summary}</Markdown></div>}
          {c.kind === 'lesson' && <p className="muted small">{c.chapterTitle}: {c.done} of {c.total} lessons known</p>}
          {c.total > 0 && <div className="bar"><span style={{ width: `${Math.round((c.done / c.total) * 100)}%` }} /></div>}
          <div className="row">
            {c.kind === 'session'
              ? <Link className="btn btn-primary" to={`/study/${c.sessionId}`}>Continue the session</Link>
              : <Link className="btn btn-primary" to={`/lesson/${c.conceptId}`}>Open the lesson</Link>}
            {(c.kind === 'lesson' || c.book) && <Link className="btn" to={`/book/${c.kind === 'lesson' ? c.bookId : c.book!.id}`}>Open the book</Link>}
          </div>
        </div>
      )}

      {empty && (
        <div className="card continue-card">
          <h2>Start with a book or a topic</h2>
          <p className="muted">Pick a PDF and say “teach me this book”, or ask to learn anything. DSC finds what you already know and
            teaches the next idea one reasoning step at a time.</p>
          <div className="row"><Link className="btn btn-primary" to="/books">Choose a book</Link><Link className="btn" to="/study">Teach me a topic</Link></div>
        </div>
      )}

      <div className="today-grid">
        <div className="card">
          <div className="eyebrow">This week</div>
          <div className="row stats">
            <div className="stat"><b>+{t?.week.learned ?? 0}</b><span className="muted small">ideas learned</span></div>
            <div className="stat"><b>{t?.week.sessions ?? 0}</b><span className="muted small">sessions done</span></div>
          </div>
          <span className="muted small">{t?.week.answers ?? 0} answers this week</span>
        </div>
        <div className="card today-map">
          <div className="eyebrow">Your map</div>
          <div className="today-map-box">
            {g && g.nodes.length > 0
              ? <MapCanvas view="territory" nodes={g.nodes} links={links} clusters={g.clusters ?? []} selected={null} matches={EMPTY}
                  center={null} compact onSelect={id => navigate('/map', { state: { focus: 'all', select: id } })} />
              : <p className="muted small">Your ideas appear here as you learn.</p>}
          </div>
          <Link className="small" to="/map">Open the map →</Link>
        </div>
      </div>

      {s.studyBooks.length > 0 && <><div className="row row-between"><h2>Your books</h2><Link className="small" to="/books">All books →</Link></div>
        <BookShelf limit={3} withNew={false} /></>}

      {t && t.recent.length > 0 && <>
        <h2>Recent sessions</h2>
        <ul className="plain recent">{t.recent.map(r => (
          <li key={r.id} className="row row-between"><Link to={`/study/${r.id}`}><Markdown inline>{r.title}</Markdown></Link>
            <span className="muted small">{r.status === 'done' ? 'done' : r.status} · {new Date(r.updatedAt).toLocaleDateString()}</span></li>
        ))}</ul>
      </>}
    </div>
  )
}
