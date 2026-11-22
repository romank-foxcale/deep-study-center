import { useEffect } from 'react'
import { NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { useStore } from './store'
import Home from './pages/Home'
import Today from './pages/Today'
import Books from './pages/Books'
import GoalSetup from './pages/GoalSetup'
import BookGoal from './pages/BookGoal'
import Roadmap from './pages/Roadmap'
import Lesson from './pages/Lesson'
import Me from './pages/Me'
import Library from './pages/Library'
import Settings from './pages/Settings'
import Review from './pages/Review'
import Probe from './pages/Probe'
import Study from './pages/Study'
import Book from './pages/Book'
import Chapter from './pages/Chapter'
import KnowledgeMap from './pages/KnowledgeMap'
import Formulas from './pages/Formulas'
import Practice from './pages/Practice'
import Search from './pages/Search'
import Week from './pages/Week'

/** Small line icons for the sidebar (24 x 24, drawn with the current text color). */
const ICON: Record<string, string> = {
  today: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1',
  books: 'M4 4h5v16H4zM10 4h5v16h-5zM16 5l4 1-3 14-4-1z',
  learn: 'M3 9l9-5 9 5-9 5zM7 11v5c3 2 7 2 10 0v-5',
  practice: 'M4 12a8 8 0 1 0 3-6.2M4 4v4h4M12 8v4l3 2',
  map: 'M12 3l7.8 4.5v9L12 21l-7.8-4.5v-9zM12 12l7.8-4.5M12 12v9M12 12L4.2 7.5',
  me: 'M12 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM4 21c1.5-4 4.5-6 8-6s6.5 2 8 6',
  settings: 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1',
}
const Icon = ({ name }: { name: string }) => (
  <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d={ICON[name]} />
  </svg>
)
/** The main flow (SPEC §30): five entries. Big goals are on hold, in their own group. */
const NAV = [
  { to: '/', label: 'Today', icon: 'today', end: true },
  { to: '/books', label: 'Books', icon: 'books' },
  { to: '/study', label: 'Learn', icon: 'learn' },
  { to: '/practice', label: 'Practice', icon: 'practice' },
  { to: '/map', label: 'Map', icon: 'map' },
]
const GOALS = [
  { to: '/goal', label: 'Goal overview' },
  { to: '/roadmap', label: 'Roadmap' },
  { to: '/week', label: 'This week' },
  { to: '/review', label: 'Reviews' },
  { to: '/goal/new', label: '+ New goal' },
]
const GOAL_PATHS = ['/goal', '/roadmap', '/week', '/review', '/lesson', '/probe', '/placement']

export default function App() {
  const { s, dispatch, error, clearError } = useStore()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  useEffect(() => { window.scrollTo(0, 0) }, [pathname])
  const pending = s.diffs.filter(d => d.status === 'pending').length
  const due = s.reviews.filter(r => r.isDue).length
  const running = s.jobs.filter(j => j.status === 'queued' || j.status === 'running').length
  return (
    <div className="shell">
      <nav className="sidebar" aria-label="Main">
        <div className="brand"><span className="brand-mark" aria-hidden /> Deep Study Center</div>
        <form className="sidebar-search" role="search" onSubmit={e => {
          e.preventDefault()
          const q = new FormData(e.currentTarget).get('q')?.toString().trim()
          if (q) navigate(`/search?q=${encodeURIComponent(q)}`)
        }}>
          <input name="q" type="search" className="input input-small" placeholder="Search" aria-label="Search" />
        </form>
        <div className="nav-main">
          {NAV.map(n => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => `nav-link${isActive || (n.to === '/books' && pathname.startsWith('/book')) ? ' active' : ''}`}>
              <Icon name={n.icon} /><span>{n.label}</span>
              {n.to === '/practice' && s.practiceDue > 0 && <span className="nav-badge">{s.practiceDue}</span>}
            </NavLink>
          ))}
        </div>
        <details className="nav-group" open={GOAL_PATHS.some(p => pathname.startsWith(p)) || undefined}>
          <summary>Goals (on hold)</summary>
          {s.goals.length > 1 && (
            <select className="input input-small sidebar-goal-select" value={s.goal?.id ?? ''} aria-label="Active goal"
              onChange={e => dispatch({ type: 'setGoal', id: e.target.value })}>
              {s.goals.map(g => <option key={g.id} value={g.id}>{g.title}</option>)}
            </select>
          )}
          {GOALS.map(n => (
            <NavLink key={n.to} to={n.to} end className="nav-link nav-sub">
              <span>{n.label}</span>
              {n.to === '/roadmap' && pending > 0 && <span className="nav-badge">{pending}</span>}
              {n.to === '/review' && due > 0 && <span className="nav-badge">{due}</span>}
            </NavLink>
          ))}
        </details>
        <div className="sidebar-foot">
          {running > 0 && <span className="muted small">{running} agent job{running > 1 ? 's' : ''} running…</span>}
          <NavLink to="/library" className="nav-link nav-sub"><span>Source library</span>
            {s.cardProposals.length > 0 && <span className="nav-badge">{s.cardProposals.length}</span>}</NavLink>
          <NavLink to="/me" className="nav-link"><Icon name="me" /><span>Me</span></NavLink>
          <NavLink to="/settings" className="nav-link"><Icon name="settings" /><span>Settings</span></NavLink>
        </div>
      </nav>
      <main className="main">
        {error && <div className="banner banner-bad app-error"><span>{error}</span><button className="btn btn-small" onClick={clearError}>Dismiss</button></div>}
        <Routes>
          <Route path="/" element={<Today />} />
          <Route path="/books" element={<Books />} />
          <Route path="/goal" element={<Home />} />
          <Route path="/goal/new" element={<GoalSetup />} />
          <Route path="/goal/book" element={<BookGoal />} />
          <Route path="/roadmap" element={<Roadmap />} />
          <Route path="/review" element={<Review />} />
          <Route path="/probe" element={<Probe />} />
          <Route path="/study" element={<Study />} />
          <Route path="/map" element={<KnowledgeMap />} />
          <Route path="/formulas" element={<Formulas />} />
          <Route path="/practice" element={<Practice />} />
          <Route path="/practice/:id" element={<Practice />} />
          <Route path="/study/:id" element={<Study />} />
          <Route path="/book/:id" element={<Book />} />
          <Route path="/book/:id/chapter/:n" element={<Chapter />} />
          <Route path="/placement" element={<Probe />} />
          <Route path="/search" element={<Search />} />
          <Route path="/week" element={<Week />} />
          <Route path="/lesson/:id" element={<Lesson />} />
          <Route path="/me" element={<Me />} />
          <Route path="/library" element={<Library />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  )
}
