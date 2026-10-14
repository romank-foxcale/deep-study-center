import { useEffect } from 'react'
import { NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { useStore } from './store'
import Home from './pages/Home'
import GoalSetup from './pages/GoalSetup'
import Roadmap from './pages/Roadmap'
import Lesson from './pages/Lesson'
import Me from './pages/Me'
import Library from './pages/Library'
import Settings from './pages/Settings'
import Review from './pages/Review'
import Placement from './pages/Placement'
import Search from './pages/Search'

const NAV = [
  { to: '/', label: 'Home', end: true },
  { to: '/roadmap', label: 'Roadmap' },
  { to: '/review', label: 'Reviews' },
  { to: '/library', label: 'Source library' },
  { to: '/me', label: 'Me & playbook' },
  { to: '/settings', label: 'Settings' },
]

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
      <nav className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden>◆</span> Deep Study Center
        </div>
        {s.goals.length > 1 ? (
          <select className="input input-small sidebar-goal-select" value={s.goal?.id ?? ''} aria-label="Active goal"
            onChange={e => dispatch({ type: 'setGoal', id: e.target.value })}>
            {s.goals.map(g => <option key={g.id} value={g.id}>{g.title}</option>)}
          </select>
        ) : <div className="sidebar-goal" title={s.goal?.title}>{s.goal?.title ?? 'No goal yet'}</div>}
        <form className="sidebar-search" role="search" onSubmit={e => {
          e.preventDefault()
          const q = new FormData(e.currentTarget).get('q')?.toString().trim()
          if (q) navigate(`/search?q=${encodeURIComponent(q)}`)
        }}>
          <input name="q" type="search" className="input input-small" placeholder="Search notes & lessons" aria-label="Search" />
        </form>
        {NAV.map(n => (
          <NavLink key={n.to} to={n.to} end={n.end} className="nav-link">
            {n.label}
            {n.to === '/roadmap' && pending > 0 && <span className="pill pill-warn">{pending}</span>}
            {n.to === '/review' && due > 0 && <span className="pill pill-warn">{due}</span>}
          </NavLink>
        ))}
        <NavLink to="/goal/new" className="nav-link nav-new">+ New goal</NavLink>
        <div className="sidebar-foot">
          {running > 0 && <span className="muted">{running} agent job{running > 1 ? 's' : ''} running…</span>}
          <span className="muted">Playbook v{s.playbook.version}</span>
        </div>
      </nav>
      <main className="main">
        {error && <div className="banner banner-bad app-error"><span>{error}</span><button className="btn btn-small" onClick={clearError}>Dismiss</button></div>}
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/goal/new" element={<GoalSetup />} />
          <Route path="/roadmap" element={<Roadmap />} />
          <Route path="/review" element={<Review />} />
          <Route path="/placement" element={<Placement />} />
          <Route path="/search" element={<Search />} />
          <Route path="/lesson/:id" element={<Lesson />} />
          <Route path="/me" element={<Me />} />
          <Route path="/library" element={<Library />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  )
}
