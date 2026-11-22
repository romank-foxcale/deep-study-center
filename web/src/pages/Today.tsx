import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getGraph, getToday, useStore } from '../store'
import BookShelf from '../components/BookShelf'
import MapCanvas from '../components/MapCanvas'
import ApiKeyCard from '../components/ApiKeyCard'
import Markdown from '../components/Markdown'
import type { GraphView, TodayView } from '../types'

const STATE_LABEL: Record<string, string> = {
  mastered: 'know strongly', learned: 'learned', learning: 'learning', rusty: 'due for review', ready: 'ready to learn', locked: 'needs others first', pending: 'not started',
}
const EMPTY = new Set<string>()

/** Today (SPEC §30): pick up where you stopped, recall what is due, see the week. */
export default function Today() {
  const { s, dispatch } = useStore()
  const navigate = useNavigate()
  const [t, setT] = useState<TodayView | null>(null)
  const [g, setG] = useState<GraphView | null>(null)
  const [going, setGoing] = useState<string | null | undefined>(undefined)
  useEffect(() => { getToday().then(setT, () => {}) }, [s])
  useEffect(() => { getGraph().then(setG, () => {}) }, [s.studyBooks.length, s.sessions.length])
  useEffect(() => {
    if (going !== undefined && s.lastSession && s.lastSession !== going) navigate(`/study/${s.lastSession}`)
  }, [s.lastSession, going, navigate])
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
          <div className="eyebrow">Continue{c.kind === 'session' && c.book ? ` · ${c.book.title}` : c.kind === 'part' ? ` · ${c.bookTitle}` : ''}</div>
          <h2><Markdown inline>{c.title}</Markdown></h2>
          {c.kind === 'session' && c.next && <p className="muted">Next idea: <strong className="text"><Markdown inline>{c.next}</Markdown></strong></p>}
          {c.kind === 'session' && !c.next && <p className="muted">{c.status === 'probing' ? 'A few quick questions find what you already know.' : 'Your plan is ready.'}</p>}
          {c.kind === 'part' && <p className="muted">pp. {c.pages[0]}–{c.pages[1]} · {c.total} ideas{c.summary ? ` · ${c.summary}` : ''}</p>}
          {c.total > 0 && <div className="bar"><span style={{ width: `${Math.round((c.done / c.total) * 100)}%` }} /></div>}
          <div className="row">
            {c.kind === 'session'
              ? <Link className="btn btn-primary" to={`/study/${c.sessionId}`}>Continue the session</Link>
              : <button className="btn btn-primary" disabled={going !== undefined} onClick={async () => {
                  setGoing(s.lastSession)
                  if (!await dispatch({ type: 'bookStudyPart', partId: c.partId })) setGoing(undefined)
                }}>{going !== undefined ? 'Starting…' : 'Study this part'}</button>}
            {(c.kind === 'part' || c.book) && <Link className="btn" to={`/book/${c.kind === 'part' ? c.bookId : c.book!.id}`}>Open the book</Link>}
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
          <div className="eyebrow">Due for recall</div>
          <div className="stat"><b>{t?.due.count ?? 0} {t?.due.count === 1 ? 'idea' : 'ideas'}</b>
            <span className="muted small">{t && t.due.count ? `about ${Math.max(5, t.due.count * 2)} minutes` : 'nothing is due'}</span></div>
          {t && t.due.items.length > 0 && (
            <div className="row chips">{t.due.items.slice(0, 4).map(d => (
              <span key={d.nodeId} className="pill"><i className={`state-dot state-${d.state}`} title={STATE_LABEL[d.state]} /> <Markdown inline>{d.title}</Markdown></span>
            ))}</div>
          )}
          <Link className="btn btn-small" to="/practice">Practise now</Link>
        </div>
        <div className="card">
          <div className="eyebrow">This week</div>
          <div className="row stats">
            <div className="stat"><b>+{t?.week.learned ?? 0}</b><span className="muted small">ideas learned</span></div>
            <div className="stat"><b>{t?.week.strong ?? 0}</b><span className="muted small">known strongly</span></div>
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
