import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getGraph, useStore } from '../store'
import Markdown from '../components/Markdown'
import { ancestors, layout } from '../components/graphLayout'
import type { GraphNode, GraphView } from '../types'

const R = 13
const LIT = new Set(['learned', 'mastered'])
const STATE_LABEL: Record<string, string> = {
  mastered: 'strong', learned: 'known', learning: 'learning', rusty: 'rusty', ready: 'ready to learn', locked: 'needs others first', pending: 'not started',
}
const LEGEND = ['mastered', 'learned', 'learning', 'ready', 'locked']

/** Two short lines for a node label; the full title is in the tooltip. */
function labelLines(title: string): string[] {
  const words = title.replace(/\$[^$]*\$/g, m => m.replace(/[\\{}$]/g, '')).split(/\s+/)
  const lines: string[] = ['']
  for (const w of words) {
    const cur = lines[lines.length - 1]
    if ((cur + ' ' + w).trim().length <= 18) lines[lines.length - 1] = (cur + ' ' + w).trim()
    else if (lines.length < 2) lines.push(w)
    else { lines[1] = (lines[1] + '…').replace(/…+$/, '…'); break }
  }
  return lines.map(l => (l.length > 20 ? l.slice(0, 19) + '…' : l))
}

/** The knowledge map (SPEC §23): every idea you know or need, as one skill tree. Basics at the bottom. */
export default function KnowledgeMap() {
  const { s } = useStore()
  const [g, setG] = useState<GraphView | null>(null)
  const [error, setError] = useState('')
  const [focus, setFocus] = useState<string>(() => (s.goal ? `goal:${s.goal.id}` : 'all'))
  const [selected, setSelected] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [hideNew, setHideNew] = useState(false)
  const [view, setView] = useState({ x: 0, y: 0, k: 1 })
  const box = useRef<HTMLDivElement>(null)
  const drag = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null)

  useEffect(() => { getGraph().then(setG, e => setError((e as Error).message)) }, [s])

  const nodes = useMemo(() => g?.nodes ?? [], [g])
  const byId = useMemo(() => new Map(nodes.map(n => [n.id, n])), [nodes])
  const members = useMemo(() => {
    if (focus === 'all') return null
    const [kind, id] = focus.split(':')
    return new Set(nodes.filter(n => (kind === 'goal' ? n.goals : n.sessions).includes(id)).map(n => n.id))
  }, [focus, nodes])
  const inFocus = useMemo(() => {
    if (!members || !g) return null
    const set = new Set(members)
    ancestors(members, g.links).forEach(a => set.add(a))
    return set
  }, [members, g])
  const targets = useMemo(() => {
    if (!members || !g) return new Set<string>()
    const hasNext = new Set(g.links.filter(l => members.has(l.src) && members.has(l.dst)).map(l => l.src))
    return new Set([...members].filter(id => !hasNext.has(id)))
  }, [members, g])

  const shown = useMemo(() => nodes.filter(n => {
    if (inFocus) return inFocus.has(n.id)
    return !hideNew || !['pending', 'locked'].includes(n.state)
  }), [nodes, inFocus, hideNew])
  const shownIds = useMemo(() => new Set(shown.map(n => n.id)), [shown])
  const links = useMemo(() => (g?.links ?? []).filter(l => shownIds.has(l.src) && shownIds.has(l.dst)), [g, shownIds])
  const pos = useMemo(() => layout(shown.map(n => n.id), links,
    id => byId.get(id)?.goals[0] ?? byId.get(id)?.sessions[0] ?? ''), [shown, links, byId])
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q.length < 2 ? new Set<string>() : new Set(shown.filter(n => `${n.title} ${n.statement}`.toLowerCase().includes(q)).map(n => n.id))
  }, [query, shown])

  const fit = useCallback(() => {
    const el = box.current
    if (!el || pos.size === 0) return
    const xs = [...pos.values()].map(p => p.x), ys = [...pos.values()].map(p => p.y)
    const minX = Math.min(...xs) - 90, maxX = Math.max(...xs) + 90, minY = Math.min(...ys) - 40, maxY = Math.max(...ys) + 70
    const k = Math.min(1.4, el.clientWidth / (maxX - minX), el.clientHeight / (maxY - minY))
    setView({ k, x: el.clientWidth / 2 - ((minX + maxX) / 2) * k, y: el.clientHeight / 2 - ((minY + maxY) / 2) * k })
  }, [pos])
  useEffect(() => { fit() }, [fit])

  const centerOn = (id: string) => {
    const p = pos.get(id), el = box.current
    if (!p || !el) return
    setView(v => ({ ...v, x: el.clientWidth / 2 - p.x * v.k, y: el.clientHeight / 2 - p.y * v.k }))
  }

  // wheel zoom around the cursor (a non-passive listener, so the page does not scroll)
  useEffect(() => {
    const el = box.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const r = el.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top
      setView(v => {
        const k = Math.min(3, Math.max(0.15, v.k * Math.exp(-e.deltaY * 0.0015)))
        return { k, x: mx - ((mx - v.x) / v.k) * k, y: my - ((my - v.y) / v.k) * k }
      })
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [])
  const zoom = (f: number) => {
    const el = box.current
    if (!el) return
    const mx = el.clientWidth / 2, my = el.clientHeight / 2
    setView(v => { const k = Math.min(3, Math.max(0.15, v.k * f)); return { k, x: mx - ((mx - v.x) / v.k) * k, y: my - ((my - v.y) / v.k) * k } })
  }
  const onDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    if ((e.target as Element).closest('.km-node')) return
    drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const d = drag.current
    if (d) setView(v => ({ ...v, x: d.vx + e.clientX - d.x, y: d.vy + e.clientY - d.y }))
  }

  if (error) return <div className="page"><p className="error">{error}</p></div>
  if (!g) return <div className="page"><p className="muted">Loading the map…</p></div>
  const sel = selected ? byId.get(selected) : undefined
  const counts = { lit: nodes.filter(n => LIT.has(n.state)).length, learning: nodes.filter(n => ['learning', 'rusty'].includes(n.state)).length }
  const needed = members ? [...members].filter(id => !LIT.has(byId.get(id)?.state ?? '')).length : 0

  return (
    <div className="km">
      <div className="km-bar">
        <h1 className="km-title">Knowledge map</h1>
        <select className="input input-small" value={focus} onChange={e => { setFocus(e.target.value); setSelected(null) }} aria-label="Show">
          <option value="all">Everything ({nodes.length} ideas)</option>
          {g.goals.length > 0 && <optgroup label="Goals">{g.goals.map(x => <option key={x.id} value={`goal:${x.id}`}>{x.title}</option>)}</optgroup>}
          {g.sessions.length > 0 && <optgroup label="Study sessions">{g.sessions.map(x => <option key={x.id} value={`session:${x.id}`}>{x.title}</option>)}</optgroup>}
        </select>
        <input className="input input-small km-search" type="search" placeholder="Find an idea" value={query} aria-label="Find an idea"
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && matches.size) { const id = [...matches][0]; setSelected(id); centerOn(id) } }} />
        {focus === 'all' && <label className="small row"><input type="checkbox" checked={hideNew} onChange={e => setHideNew(e.target.checked)} /> Hide ideas not started</label>}
        <span className="spacer" />
        <span className="muted small">{members ? `${members.size - needed} of ${members.size} known · ${needed} still needed`
          : `${counts.lit} known · ${counts.learning} learning · ${nodes.length - counts.lit - counts.learning} to learn`}</span>
        <div className="km-zoom">
          <button className="btn btn-small" onClick={() => zoom(1.25)} aria-label="Zoom in">+</button>
          <button className="btn btn-small" onClick={() => zoom(0.8)} aria-label="Zoom out">−</button>
          <button className="btn btn-small" onClick={fit}>Fit</button>
        </div>
      </div>
      <div className="km-legend small muted">
        {LEGEND.map(st => <span key={st} className="km-legend-item"><svg width="14" height="14"><circle cx="7" cy="7" r="5.5" className={`km-dot km-${st}`} /></svg>{STATE_LABEL[st]}</span>)}
        <span className="km-legend-item">Basics at the bottom; an arrow points to the idea it helps you reason toward.</span>
      </div>

      <div className="km-canvas" ref={box}>
        {nodes.length === 0 && <p className="muted km-empty">No ideas yet. Research a goal or <Link to="/study">study something</Link>.</p>}
        <svg width="100%" height="100%" onPointerDown={onDown} onPointerMove={onMove} onPointerUp={() => { drag.current = null }}
          onClick={e => { if (!(e.target as Element).closest('.km-node')) setSelected(null) }}>
          <defs>
            <marker id="km-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" className="km-arrowhead" />
            </marker>
          </defs>
          <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
            {links.map(l => {
              const a = pos.get(l.src)!, b = pos.get(l.dst)!
              const lit = LIT.has(byId.get(l.src)!.state) && LIT.has(byId.get(l.dst)!.state)
              const hot = selected && (l.src === selected || l.dst === selected)
              const dy = Math.max(30, (a.y - b.y) / 2)
              return <path key={`${l.src}>${l.dst}`} className={`km-link ${lit ? 'lit' : ''} ${hot ? 'hot' : ''}`} markerEnd="url(#km-arrow)"
                d={`M ${a.x} ${a.y - R} C ${a.x} ${a.y - R - dy}, ${b.x} ${b.y + R + dy}, ${b.x} ${b.y + R + 3}`} />
            })}
            {shown.map(n => {
              const p = pos.get(n.id)!
              const cls = ['km-node', `km-${n.state}`]
              if (targets.has(n.id)) cls.push('target')
              if (members && !members.has(n.id)) cls.push('support')
              if (matches.has(n.id)) cls.push('match')
              if (selected === n.id) cls.push('selected')
              return (
                <g key={n.id} className={cls.join(' ')} transform={`translate(${p.x},${p.y})`}
                  onClick={() => setSelected(n.id === selected ? null : n.id)}>
                  <title>{`${n.title} (${STATE_LABEL[n.state] ?? n.state})`}</title>
                  {targets.has(n.id) && <circle r={R + 7} className="km-halo" />}
                  <circle r={R} className={`km-dot km-${n.state}`} />
                  {['learning', 'rusty'].includes(n.state) && (
                    <circle r={R - 4} className="km-progress" pathLength={100} strokeDasharray={`${Math.round(n.mastery * 100)} 100`}
                      transform="rotate(-90)" />
                  )}
                  {labelLines(n.title).map((t, i) => <text key={i} y={R + 14 + i * 13} textAnchor="middle" className="km-label">{t}</text>)}
                </g>
              )
            })}
          </g>
        </svg>
        {sel && <NodePanel n={sel} g={g} onPick={id => { setSelected(id); centerOn(id) }} onClose={() => setSelected(null)} />}
      </div>
    </div>
  )
}

function NodePanel({ n, g, onPick, onClose }: { n: GraphNode; g: GraphView; onPick: (id: string) => void; onClose: () => void }) {
  const { s, dispatch } = useStore()
  const navigate = useNavigate()
  const title = (id: string) => g.nodes.find(x => x.id === id)?.title ?? id
  const before = g.links.filter(l => l.dst === n.id).map(l => l.src)
  const after = g.links.filter(l => l.src === n.id).map(l => l.dst)
  const goalTitle = (id: string) => g.goals.find(x => x.id === id)?.title ?? id
  const openLesson = async (lessonId: string, goalId: string) => {
    if (s.goal?.id !== goalId && !await dispatch({ type: 'setGoal', id: goalId })) return
    navigate(`/lesson/${lessonId}`)
  }
  return (
    <aside className="km-panel card">
      <div className="row row-between">
        <span className={`pill km-pill-${n.state}`}>{STATE_LABEL[n.state] ?? n.state}{['learning', 'rusty'].includes(n.state) ? ` · ${Math.round(n.mastery * 100)}%` : ''}</span>
        <button className="link small" onClick={onClose} aria-label="Close">Close</button>
      </div>
      <h2 className="h-small"><Markdown inline>{n.title}</Markdown></h2>
      {n.statement && <div className="small"><Markdown>{n.statement}</Markdown></div>}
      {before.length > 0 && <><div className="eyebrow">Builds on</div>
        <ul className="km-list">{before.map(id => <li key={id}><button className="link" onClick={() => onPick(id)}><Markdown inline>{title(id)}</Markdown></button></li>)}</ul></>}
      {after.length > 0 && <><div className="eyebrow">Leads to</div>
        <ul className="km-list">{after.map(id => <li key={id}><button className="link" onClick={() => onPick(id)}><Markdown inline>{title(id)}</Markdown></button></li>)}</ul></>}
      {n.lessons.length > 0 && <><div className="eyebrow">Lessons</div>
        <ul className="km-list">{n.lessons.map(l => (
          <li key={l.id}><button className="link" onClick={() => openLesson(l.id, l.goalId)}>{l.title}</button>
            <span className="muted small"> · {goalTitle(l.goalId)}</span></li>
        ))}</ul></>}
      {n.sessions.length > 0 && <><div className="eyebrow">Study sessions</div>
        <ul className="km-list">{n.sessions.map(id => <li key={id}><Link to={`/study/${id}`}>{g.sessions.find(x => x.id === id)?.title ?? id}</Link></li>)}</ul></>}
      {!LIT.has(n.state) && (
        <button className="btn btn-primary btn-small" onClick={() => navigate('/study', { state: { topic: `Teach me: ${n.title}. ${n.statement}`.slice(0, 400) } })}>
          Teach me this</button>
      )}
    </aside>
  )
}
