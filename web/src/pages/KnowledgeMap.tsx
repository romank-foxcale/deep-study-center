import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { getGraph, getIdea, useStore } from '../store'
import Markdown from '../components/Markdown'
import { ancestors, layout } from '../components/graphLayout'
import HexMap, { CELL_LABEL, cellState } from '../components/HexMap'
import type { GraphNode, GraphView, IdeaDetail, MapGap, MapGoal, MapViewId } from '../types'

const R = 13
const LIT = new Set(['learned'])
const STATE_LABEL: Record<string, string> = {
  learned: 'learned', learning: 'learning', ready: 'ready to learn', locked: 'needs others first', pending: 'not started',
}
const LEGEND = ['learned', 'learning', 'ready', 'locked']
/** The map views the learner can choose from (SPEC §29). */
const VIEWS: { id: MapViewId; label: string; hint: string }[] = [
  { id: 'hex', label: 'Map', hint: 'One hex per idea, from all your sources. Ideas that build on each other sit side by side.' },
  { id: 'tree', label: 'Tree', hint: 'Basics at the bottom; an arrow points to the idea it helps you reason toward.' },
]

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

/** True when two words differ by at most one letter (a spelling slip: "hoffman" finds "huffman"). */
function oneOff(a: string, b: string): boolean {
  if (Math.abs(a.length - b.length) > 1) return false
  let i = 0, j = 0, d = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { i++; j++; continue }
    if (++d > 1) return false
    if (a.length > b.length) i++
    else if (b.length > a.length) j++
    else { i++; j++ }
  }
  return d + (a.length - i) + (b.length - j) <= 1
}

/** How well a search fits a text: 2 for every word found as typed, 1 when a word matches with one wrong letter, 0 for no match. */
function searchScore(query: string, text: string): number {
  const t = text.toLowerCase(), words = t.split(/[^\p{L}\p{N}]+/u).filter(Boolean)
  let exact = true
  for (const w of query.toLowerCase().split(/\s+/).filter(Boolean)) {
    if (t.includes(w)) continue
    if (w.length >= 4 && words.some(x => oneOff(w, x) || (x.length > w.length && oneOff(w, x.slice(0, w.length))))) { exact = false; continue }
    return 0
  }
  return exact ? 2 : 1
}

/** The knowledge map (SPEC §23): every idea you know or need, as one skill tree. Basics at the bottom. */
export default function KnowledgeMap() {
  const { s, dispatch } = useStore()
  const mode: MapViewId = VIEWS.some(v => v.id === s.mapView) ? s.mapView : 'hex'  // the default; also for a removed view
  const [names, setNames] = useState(false)
  const [gapId, setGapId] = useState<string | null>(null)
  const [goalId, setGoalId] = useState<string | null>(null)
  const [added, setAdded] = useState<string | null>(null)  // the title of an idea just added from a gap: select it once it is on the map
  const [center, setCenter] = useState<{ id: string; n: number } | null>(null)
  const location = useLocation()
  const asked = location.state as { focus?: string; select?: string } | null
  const [g, setG] = useState<GraphView | null>(null)
  const [error, setError] = useState('')
  const [focus, setFocus] = useState<string>(() => asked?.focus ?? 'all')
  const [selected, setSelected] = useState<string | null>(asked?.select ?? null)
  const [query, setQuery] = useState('')
  const [listOpen, setListOpen] = useState(false)
  const [hideNew, setHideNew] = useState(false)
  const [view, setView] = useState({ x: 0, y: 0, k: 1 })
  const box = useRef<HTMLDivElement>(null)
  const drag = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null)

  useEffect(() => { getGraph().then(setG, e => setError((e as Error).message)) }, [s])

  const nodes = useMemo(() => g?.nodes ?? [], [g])
  useEffect(() => {
    if (!added || !g) return
    const n = g.nodes.find(x => x.title === added)
    if (n) { setSelected(n.id); setAdded(null) }
  }, [added, g])
  const byId = useMemo(() => new Map(nodes.map(n => [n.id, n])), [nodes])
  const members = useMemo(() => {
    if (focus === 'all') return null
    const [kind, id] = focus.split(':')
    return new Set(nodes.filter(n => (kind === 'goal' ? n.goals : kind === 'book' ? n.books : n.sessions).includes(id)).map(n => n.id))
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
    id => byId.get(id)?.books[0] ?? byId.get(id)?.goals[0] ?? byId.get(id)?.sessions[0] ?? ''), [shown, links, byId])
  // the search: the idea's title and text, then the titles of its sources (a book, a study session); one wrong letter is forgiven
  const found = useMemo(() => {
    const q = query.trim()
    if (q.length < 2 || !g) return []
    const src = new Map<string, string>([...g.books.map(b => [b.id, b.title] as [string, string]), ...g.sessions.map(x => [x.id, x.title] as [string, string])])
    return shown.map(n => {
      const own = searchScore(q, `${n.title} ${n.statement}`)
      const from = own ? 0 : searchScore(q, [...n.books, ...n.sessions].map(id => src.get(id) ?? '').join(' '))
      const titleHit = searchScore(q, n.title)
      return { n, rank: own ? 10 + own * 2 + titleHit : from }
    }).filter(x => x.rank > 0).sort((a, b) => b.rank - a.rank || a.n.title.localeCompare(b.n.title)).map(x => x.n)
  }, [query, shown, g])
  const matches = useMemo(() => new Set(found.map(n => n.id)), [found])
  const pick = (id: string) => { setSelected(id); centerOn(id); setListOpen(false) }

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
    if (mode !== 'tree') { setCenter(c => ({ id, n: (c?.n ?? 0) + 1 })); return }
    const p = pos.get(id), el = box.current
    if (!p || !el) return
    setView(v => ({ ...v, x: el.clientWidth / 2 - p.x * v.k, y: el.clientHeight / 2 - p.y * v.k }))
  }

  // wheel zoom around the cursor (a non-passive listener, so the page does not scroll). The tree's box exists only after
  // the map is loaded, so the listener is attached again then (it was missing before: the wheel did nothing).
  const loaded = g !== null
  useEffect(() => {
    const el = box.current
    if (!el || !loaded || mode !== 'tree') return
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
  }, [loaded, mode])
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
  const counts = { lit: nodes.filter(n => LIT.has(n.state)).length, learning: nodes.filter(n => n.state === 'learning').length }
  const needed = members ? [...members].filter(id => !LIT.has(byId.get(id)?.state ?? '')).length : 0

  return (
    <div className="km">
      <div className="km-bar">
        <h1 className="km-title">Knowledge map</h1>
        <Link className="link small" to="/formulas" title="Every formula lesson and the blocks it is built from">Formula tree</Link>
        <select className="input input-small" value={focus} onChange={e => { setFocus(e.target.value); setSelected(null) }} aria-label="Show" hidden={mode === 'hex'}>
          <option value="all">Everything ({nodes.filter(n => n.kind !== 'formula').length} ideas, {nodes.filter(n => n.kind === 'formula').length} formulas)</option>
          {g.goals.length > 0 && <optgroup label="Goals">{g.goals.map(x => <option key={x.id} value={`goal:${x.id}`}>{x.title}</option>)}</optgroup>}
          {g.books.length > 0 && <optgroup label="Books">{g.books.map(x => <option key={x.id} value={`book:${x.id}`}>{x.title}</option>)}</optgroup>}
          {g.sessions.length > 0 && <optgroup label="Study sessions">{g.sessions.map(x => <option key={x.id} value={`session:${x.id}`}>{x.title}</option>)}</optgroup>}
        </select>
        <div className="km-find">
          <input className="input input-small km-search" type="search" placeholder="Find an idea" value={query} aria-label="Find an idea"
            onChange={e => { setQuery(e.target.value); setListOpen(true) }} onFocus={() => setListOpen(true)}
            onBlur={() => setTimeout(() => setListOpen(false), 150)}
            onKeyDown={e => { if (e.key === 'Enter' && found.length) pick(found[0].id); if (e.key === 'Escape') setListOpen(false) }} />
          {listOpen && query.trim().length >= 2 && (
            <ul className="km-results" role="listbox" aria-label="Ideas found">
              {found.length === 0 && <li className="none">No idea matches "{query.trim()}"</li>}
              {found.slice(0, 8).map((n, i) => (
                <li key={n.id} role="option" aria-selected={i === 0} className={i === 0 ? 'on' : ''} onMouseDown={e => { e.preventDefault(); pick(n.id) }}>
                  {n.title} <span className="small muted">· {CELL_LABEL[cellState(n.state)] ?? n.state}</span>
                </li>))}
              {found.length > 8 && <li className="none small">{found.length - 8} more are lit on the map</li>}
            </ul>)}
        </div>
        {focus === 'all' && <label className="small row"><input type="checkbox" checked={hideNew} onChange={e => setHideNew(e.target.checked)} /> Hide ideas not started</label>}
        <label className="small row km-view">View
          <select className="input input-small" value={mode} aria-label="Map view"
            onChange={e => dispatch({ type: 'setMapView', view: e.target.value as MapViewId })}>
            {VIEWS.map(v => <option key={v.id} value={v.id}>{v.label}</option>)}
          </select>
        </label>
        <span className="spacer" />
        <span className="muted small">{members ? `${members.size - needed} of ${members.size} known · ${needed} still needed`
          : `${counts.lit} known · ${counts.learning} learning · ${nodes.length - counts.lit - counts.learning} to learn`}</span>
        {mode === 'tree' && <div className="km-zoom">
          <button className="btn btn-small" onClick={() => zoom(1.25)} aria-label="Zoom in">+</button>
          <button className="btn btn-small" onClick={() => zoom(0.8)} aria-label="Zoom out">−</button>
          <button className="btn btn-small" onClick={fit}>Fit</button>
        </div>}
      </div>
      <div className="km-legend small muted">
        {mode === 'hex'
          ? <>{(['learned', 'known', 'unexplored'] as const).map(st => <span key={st} className="km-legend-item"><i className={`hm-swatch hm-${st}`} />{CELL_LABEL[st]}</span>)}
              <span className="km-legend-item"><i className="hm-swatch hm-swatch-gap" />gap: something is missing here</span>
              <label className="km-legend-item"><input type="checkbox" checked={names} onChange={e => setNames(e.target.checked)} /> Show names</label>
              <FindGaps /><AddGoal /></>
          : LEGEND.map(st => <span key={st} className="km-legend-item"><i className={`km-swatch km-swatch-${st}`} />{STATE_LABEL[st]}</span>)}
        <span className="km-legend-item">{VIEWS.find(v => v.id === mode)?.hint}</span>
      </div>

      <div className="km-canvas" ref={box}>
        {nodes.length === 0 && <p className="muted km-empty">No ideas yet. Research a goal or <Link to="/study">study something</Link>.</p>}
        {mode === 'hex' && <HexMap nodes={shown} links={links} selected={selected} matches={matches} center={center} names={names}
          gaps={g.gaps ?? []} selectedGap={gapId} onGap={id => { setGapId(id); setSelected(null); setGoalId(null) }}
          goals={g.mapGoals ?? []} selectedGoal={goalId} onGoal={id => { setGoalId(id); setSelected(null); setGapId(null) }}
          onSelect={id => { setSelected(id); if (id) { setGapId(null); setGoalId(null) } }} />}
        {mode === 'hex' && goalId && (g.mapGoals ?? []).some(x => x.id === goalId) && (
          <GoalPanel goal={(g.mapGoals ?? []).find(x => x.id === goalId)!} g={g} onPick={id => { setGoalId(null); setSelected(id); centerOn(id) }}
            onAdded={t => { setGoalId(null); setAdded(t) }} onClose={() => setGoalId(null)} />)}
        {mode === 'hex' && gapId && (g.gaps ?? []).some(x => x.id === gapId) && (
          <GapPanel gap={(g.gaps ?? []).find(x => x.id === gapId)!} g={g} onPick={id => { setGapId(null); setSelected(id); centerOn(id) }}
            onAdded={t => { setGapId(null); setAdded(t) }} onClose={() => setGapId(null)} />)}
        {mode === 'tree' && <svg width="100%" height="100%" onPointerDown={onDown} onPointerMove={onMove} onPointerUp={() => { drag.current = null }}
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
                  {n.state === 'learning' && (
                    <circle r={R - 4} className="km-progress" pathLength={100} strokeDasharray={`${Math.round(n.mastery * 100)} 100`}
                      transform="rotate(-90)" />
                  )}
                  {labelLines(n.title).map((t, i) => <text key={i} y={R + 14 + i * 13} textAnchor="middle" className="km-label">{t}</text>)}
                </g>
              )
            })}
          </g>
        </svg>}
        {sel && <NodePanel n={sel} g={g} onPick={id => { setSelected(id); centerOn(id) }} onClose={() => setSelected(null)} />}
      </div>
    </div>
  )
}

/** "Add a goal" (SPEC §53): one line; the goal agent finds its direction and building blocks. */
function AddGoal() {
  const { s, dispatch } = useStore()
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const busy = s.jobs.some(j => j.kind === 'goal_research' && (j.status === 'queued' || j.status === 'running'))
  if (!open) return <button className="btn btn-small" disabled={busy} onClick={() => setOpen(true)}>{busy ? 'Researching your goal…' : '★ Add a goal'}</button>
  const go = async () => { if (title.trim().length >= 4 && await dispatch({ type: 'addMapGoal', title: title.trim() })) { setTitle(''); setOpen(false) } }
  return (
    <span className="row hm-add-goal">
      <input className="input input-small" autoFocus placeholder="For example: a top-level AI/ML engineer, like Karpathy" value={title}
        onChange={e => setTitle(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') void go(); if (e.key === 'Escape') setOpen(false) }} />
      <button className="btn btn-small btn-primary" onClick={() => void go()}>Add</button>
      <button className="link small" onClick={() => setOpen(false)}>Cancel</button>
    </span>
  )
}

/** One goal (SPEC §53): its direction, how much of the way you have, the next moves, and its missing building blocks. */
function GoalPanel({ goal, g, onPick, onAdded, onClose }: { goal: MapGoal; g: GraphView; onPick: (id: string) => void; onAdded: (title: string) => void; onClose: () => void }) {
  const { s, dispatch } = useStore()
  const navigate = useNavigate()
  const [renaming, setRenaming] = useState<string | null>(null)
  const busy = goal.busy || s.jobs.some(j => j.kind === 'goal_research' && (j.status === 'queued' || j.status === 'running'))
  const mine = g.nodes.filter(n => (goal.scores[n.id] ?? 0) >= 0.7)
  const count = (st: string) => mine.filter(n => cellState(n.state) === st).length
  const total = mine.length + goal.blocks.length || 1
  const learned = new Set(g.nodes.filter(n => n.state === 'learned').map(n => n.id))
  const next = mine.filter(n => n.state !== 'learned' && g.links.some(l => l.dst === n.id && learned.has(l.src)))
    .sort((a, b) => (goal.scores[b.id] ?? 0) - (goal.scores[a.id] ?? 0)).slice(0, 4)
  const first = next.length ? next : mine.filter(n => n.state !== 'learned').sort((a, b) => (goal.scores[b.id] ?? 0) - (goal.scores[a.id] ?? 0)).slice(0, 3)
  return (
    <aside className="km-panel card">
      <div className="row row-between">
        <span className="pill" style={{ borderColor: goal.color, color: goal.color }}>★ goal</span>
        <button className="link small" onClick={onClose} aria-label="Close">Close</button>
      </div>
      {renaming === null
        ? <h2 className="h-small">{goal.title}</h2>
        : <div className="row"><input className="input input-small" autoFocus value={renaming} onChange={e => setRenaming(e.target.value)} />
            <button className="btn btn-small" onClick={async () => { if (await dispatch({ type: 'renameMapGoal', goalId: goal.id, title: renaming })) setRenaming(null) }}>Save</button></div>}
      {busy && <p className="skeleton small">The goal agent is finding the direction and the building blocks…</p>}
      {goal.error && !busy && <p className="small error">The research failed: {goal.error}</p>}
      {goal.direction && <><div className="eyebrow">The direction</div><p className="small">{goal.direction}</p></>}
      {goal.researched && <>
        <div className="eyebrow">Building blocks: {count('learned')} of {total} learned</div>
        <div className="hm-meter">
          <i style={{ width: `${count('learned') / total * 100}%`, background: 'var(--cell-learned)' }} />
          <i style={{ width: `${count('known') / total * 100}%`, background: 'var(--cell-known)' }} />
          <i style={{ width: `${count('unexplored') / total * 100}%`, background: 'var(--cell-unexplored-edge)' }} />
        </div>
        <p className="small muted">{count('learned')} learned · {count('known')} started · {count('unexplored')} on your map, not explored · {goal.blocks.length} not on your map yet</p>
        {first.length > 0 && <><div className="eyebrow">Next moves toward it</div>
          {first.map(n => <button key={n.id} className="hm-next" onClick={() => onPick(n.id)}>
            <b><Markdown inline>{n.title}</Markdown></b> <span className="muted small">· {CELL_LABEL[cellState(n.state)]}</span></button>)}</>}
        {goal.blocks.length > 0 && <><div className="eyebrow">Not on your map yet</div>
          {goal.blocks.map(b => (
            <div key={b.id} className="hm-gap-idea">
              <div className="row row-between"><b><Markdown inline>{b.title}</Markdown></b>
                <span className="row">
                  <button className="btn btn-small" onClick={async () => { if (await dispatch({ type: 'addGoalBlock', goalId: goal.id, blockId: b.id })) onAdded(b.title) }}>Add to map</button>
                  <button className="btn btn-small btn-primary" onClick={() => navigate('/study', { state: { topic: `Teach me: ${b.title}. ${b.says}`.slice(0, 400) } })}>Teach me this</button>
                </span></div>
              <div className="small muted"><Markdown inline>{b.says}</Markdown></div>
            </div>))}</>}
      </>}
      <div className="row">
        <button className="link small" onClick={() => setRenaming(goal.title)}>Rename</button>
        <button className="link small" onClick={async () => { if (window.confirm(`Remove the goal “${goal.title}”? Your cells stay on the map.`) && await dispatch({ type: 'removeMapGoal', goalId: goal.id })) onClose() }}>Remove the goal</button>
      </div>
    </aside>
  )
}

/** "Find gaps" (SPEC §51): an agent looks at the arrows near what you study for ideas that are missing. */
function FindGaps() {
  const { s, dispatch } = useStore()
  const busy = s.jobs.some(j => j.kind === 'find_gaps' && (j.status === 'queued' || j.status === 'running') && !j.input?.focus)
  return <button className="btn btn-small" disabled={busy} onClick={() => dispatch({ type: 'findGaps' })}
    title="An agent looks for ideas missing between the ideas you study">{busy ? 'Looking for gaps…' : 'Find gaps'}</button>
}

/** One gap (SPEC §51): what is missing between two ideas. Add an idea (it becomes a cell, the gap shrinks), ask for more
 *  (the gap grows, at most 3), or say it is not missing (the gap closes for good). */
function GapPanel({ gap, g, onPick, onAdded, onClose }: { gap: MapGap; g: GraphView; onPick: (id: string) => void; onAdded: (title: string) => void; onClose: () => void }) {
  const { s, dispatch } = useStore()
  const title = (id: string) => g.nodes.find(x => x.id === id)?.title ?? id
  const looking = gap.busy || s.jobs.some(j => j.kind === 'find_gaps' && (j.status === 'queued' || j.status === 'running') && j.input?.focus === gap.id)
  return (
    <aside className="km-panel card">
      <div className="row row-between">
        <span className="pill hm-pill-gap">gap</span>
        <button className="link small" onClick={onClose} aria-label="Close">Close</button>
      </div>
      <h2 className="h-small">Something is missing here</h2>
      <p className="small">Between <button className="link" onClick={() => onPick(gap.between[0])}><Markdown inline>{title(gap.between[0])}</Markdown></button> and{' '}
        <button className="link" onClick={() => onPick(gap.between[1])}><Markdown inline>{title(gap.between[1])}</Markdown></button>,
        the tutor found {gap.ideas.length === 1 ? 'one idea' : `${gap.ideas.length} ideas`} that connect them. Add one to your map: it becomes a cell, and the gap shrinks.</p>
      {gap.ideas.map((i, n) => (
        <div key={i.title} className="hm-gap-idea">
          <div className="row row-between"><b><Markdown inline>{i.title}</Markdown></b>
            <button className="btn btn-small btn-primary" onClick={async () => { if (await dispatch({ type: 'acceptGap', gapId: gap.id, index: n })) onAdded(i.title) }}>Add to map</button></div>
          <div className="small muted"><Markdown inline>{i.says}</Markdown></div>
        </div>
      ))}
      <div className="row">
        <button className="btn btn-small" disabled={looking || gap.ideas.length >= 3} onClick={() => dispatch({ type: 'findGaps', gapId: gap.id })}
          title={gap.ideas.length >= 3 ? 'At most 3 ideas in one gap' : 'The tutor looks at this place again'}>{looking ? 'Looking…' : 'Find more'}</button>
        <button className="btn btn-small" onClick={async () => { if (await dispatch({ type: 'dismissGap', gapId: gap.id })) onClose() }}
          title="Nothing is missing here: the gap closes and is not proposed again">Not missing</button>
      </div>
    </aside>
  )
}

const KIND_ICON: Record<string, string> = { book: '📘', article: '📄', web: '🌐', video: '▶️', custom: '✎', session: '💬' }

function NodePanel({ n, g, onPick, onClose }: { n: GraphNode; g: GraphView; onPick: (id: string) => void; onClose: () => void }) {
  const { s, dispatch } = useStore()
  const navigate = useNavigate()
  const [d, setD] = useState<IdeaDetail | null>(null)
  useEffect(() => {  // the idea's sources and its one lesson (SPEC §49, §50); a formula without a page has none
    let live = true
    setD(null)
    if (!n.id.startsWith('fx:')) getIdea(n.id).then(x => live && setD(x), () => {})
    return () => { live = false }
  }, [n.id])
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
        <span className={`pill hm-pill hm-${cellState(n.state)}`}>{CELL_LABEL[cellState(n.state)]}{n.state === 'learning' ? ` · ${Math.round(n.mastery * 100)}%` : ''}</span>
        <button className="link small" onClick={onClose} aria-label="Close">Close</button>
      </div>
      {n.kind === 'formula' && <div className="eyebrow">Formula</div>}
      {n.step && <div className="eyebrow">A step of a lesson</div>}
      <h2 className="h-small"><Markdown inline>{n.title}</Markdown></h2>
      {n.tex && <Markdown>{`$$${n.tex}$$`}</Markdown>}
      {n.statement && <div className="small"><Markdown>{n.statement}</Markdown></div>}
      {before.length > 0 && <><div className="eyebrow">Builds on</div>
        <ul className="km-list">{before.map(id => <li key={id}><button className="link" onClick={() => onPick(id)}><Markdown inline>{title(id)}</Markdown></button></li>)}</ul></>}
      {after.length > 0 && <><div className="eyebrow">Leads to</div>
        <ul className="km-list">{after.map(id => <li key={id}><button className="link" onClick={() => onPick(id)}><Markdown inline>{title(id)}</Markdown></button></li>)}</ul></>}
      {n.step && <><div className="eyebrow">Taught in</div>
        <ul className="km-list"><li><Link to={`/lesson/${n.step.conceptId}`}><Markdown inline>{n.step.lesson}</Markdown></Link></li></ul></>}
      {d && d.sources.length > 0 && <><div className="eyebrow">Sources ({d.sources.length})</div>
        <ul className="km-list hm-sources">{d.sources.map((x, i) => (
          <li key={i}><span className="hm-src-icon" aria-hidden>{KIND_ICON[x.kind] ?? '📘'}</span>
            {'sessionId' in x
              ? <span><Link to={`/study/${x.sessionId}`}>{x.title}</Link><div className="muted small">study session</div></span>
              : <span><Link to={`/book/${x.bookId}`}>{x.title}</Link>
                  <div className="muted small">{x.part} · {x.pages[0] === x.pages[1] ? `p. ${x.pages[0]}` : `pp. ${x.pages[0]}–${x.pages[1]}`}</div></span>}
          </li>))}</ul>
        {d.sources.length > 1 && <p className="small muted">One lesson: the tutor picks from these sources when it writes it.</p>}</>}
      {!d && n.lessons.length > 0 && <><div className="eyebrow">Lessons</div>
        <ul className="km-list">{n.lessons.map(l => (
          <li key={l.id}><button className="link" onClick={() => openLesson(l.id, l.goalId)}>{l.title}</button>
            <span className="muted small"> · {goalTitle(l.goalId)}</span></li>
        ))}</ul></>}
      <div className="row">
        {d?.lesson && <Link className={`btn btn-small${LIT.has(n.state) ? '' : ' btn-primary'}`} to={`/lesson/${d.lesson}`}>
          {LIT.has(n.state) ? 'Open the lesson' : n.state === 'learning' ? 'Continue the lesson' : 'Start the lesson'}</Link>}
        {!LIT.has(n.state) && !d?.lesson && (
          <button className="btn btn-primary btn-small" onClick={() => navigate('/study', { state: { topic: `Teach me: ${n.title}. ${n.statement}`.slice(0, 400) } })}>
            Teach me this</button>
        )}
        {n.state !== 'pending' && n.state !== 'locked' && !n.id.startsWith('fx:') && (
          <button className={`btn btn-small ${LIT.has(n.state) ? 'btn-primary' : ''}`} title="Problems that make you recall this idea"
            onClick={() => navigate('/practice', { state: { nodeIds: [n.id], title: n.title } })}>Practise</button>
        )}
      </div>
    </aside>
  )
}
