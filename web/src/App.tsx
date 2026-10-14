import { useEffect } from 'react'
import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { useStore } from './store'
import Home from './pages/Home'
import GoalSetup from './pages/GoalSetup'
import Roadmap from './pages/Roadmap'
import Lesson from './pages/Lesson'
import Me from './pages/Me'
import Library from './pages/Library'
import Settings from './pages/Settings'

const NAV = [
  { to: '/', label: 'Home', end: true },
  { to: '/roadmap', label: 'Roadmap' },
  { to: '/library', label: 'Source library' },
  { to: '/me', label: 'Me & playbook' },
  { to: '/settings', label: 'Settings' },
]

export default function App() {
  const { s } = useStore()
  const { pathname } = useLocation()
  useEffect(() => { window.scrollTo(0, 0) }, [pathname])
  const pending = s.diffs.filter(d => d.status === 'pending').length
  return (
    <div className="shell">
      <nav className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden>◆</span> Deep Study Center
        </div>
        <div className="sidebar-goal" title={s.goal.title}>{s.goal.title}</div>
        {NAV.map(n => (
          <NavLink key={n.to} to={n.to} end={n.end} className="nav-link">
            {n.label}
            {n.to === '/roadmap' && pending > 0 && <span className="pill pill-warn">{pending}</span>}
          </NavLink>
        ))}
        <NavLink to="/goal/new" className="nav-link nav-new">+ New goal</NavLink>
        <div className="sidebar-foot">
          <span className="muted">Playbook v{s.playbook.version}</span>
          <span className="muted">Prototype · mock data</span>
        </div>
      </nav>
      <main className="main">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/goal/new" element={<GoalSetup />} />
          <Route path="/roadmap" element={<Roadmap />} />
          <Route path="/lesson/:id" element={<Lesson />} />
          <Route path="/me" element={<Me />} />
          <Route path="/library" element={<Library />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  )
}
