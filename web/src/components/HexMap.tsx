import { useEffect, useMemo, useRef, useState } from 'react'
import Markdown from './Markdown'
import type { GraphNode, MapGap, MapGoal } from '../types'

// The map of ideas (SPEC §50): one hex per idea (one cell per idea, §49), no countries. Ideas that build on each other
// sit next to each other: a small force layout (links pull, cells push apart), then every cell snaps to the nearest
// free hex, the most linked first. Colors: learned (green), known but not learned yet (blue-gray: you started it),
// not explored (dark). Point at a cell for what it is; click it for its sources (the page's panel). A gap (§51) takes
// one empty, dashed hex per missing idea, between its two cells: point at it for what is missing, click it to add.

export type CellState = 'learned' | 'known' | 'unexplored'
export const cellState = (state: string): CellState => (state === 'learned' ? 'learned' : state === 'learning' ? 'known' : 'unexplored')
export const CELL_LABEL: Record<CellState, string> = { learned: 'learned', known: 'known, not learned yet', unexplored: 'not explored' }

interface Link { src: string; dst: string }
interface Cell { id: string; q: number; r: number; x: number; y: number }

const S = 20                       // hex size (center to corner)
const W3 = Math.sqrt(3)
const STEP = S * W3                // the distance between two touching hexes
const DIRS: [number, number][] = [[1, 0], [1, -1], [0, -1], [-1, 0], [-1, 1], [0, 1]]
const toPix = (q: number, r: number) => [S * W3 * (q + r / 2), S * 1.5 * r]
function roundHex(x: number, y: number): [number, number] {
  const q = (W3 / 3 * x - y / 3) / S, r = (2 / 3 * y) / S
  let rx = Math.round(q), rz = Math.round(r)
  const ry = Math.round(-q - r)
  const dx = Math.abs(rx - q), dz = Math.abs(rz - r), dy = Math.abs(ry + q + r)
  if (dx > dy && dx > dz) rx = -ry - rz; else if (dz > dy) rz = -rx - ry
  return [rx, rz]
}
const hash = (s: string) => { let h = 2166136261; for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619); return h >>> 0 }

/** Positions for every idea: deterministic (the same map gives the same picture), linked ideas side by side. A gap is
 *  laid out as one more cell linked to its two ideas, then takes one free hex per missing idea. */
export interface GoalPlace { star: { x: number; y: number }; blocks: { id: number; title: string; says: string; x: number; y: number }[] }

/** With goals (SPEC §53), every cell also wants a place along each goal's direction that depends on its score: a
 *  building block goes toward the goal, a side road away from it; links still keep neighbours together. Each goal's
 *  star sits just past the edge of the land in its direction, its missing blocks on the way to it. */
export function layoutCells(ids: string[], links: Link[], gaps: MapGap[] = [], goals: MapGoal[] = []): { cells: Map<string, Cell>; gapCells: Map<string, Cell[]>; goalPlaces: Map<string, GoalPlace> } {
  const known = new Set(ids)
  const gs = gaps.filter(g => known.has(g.between[0]) && known.has(g.between[1]))
  links = [...links, ...gs.flatMap(g => [{ src: g.between[0], dst: g.id }, { src: g.id, dst: g.between[1] }])]
  ids = [...ids, ...gs.map(g => g.id)]
  const size = new Map(gs.map(g => [g.id, g.ideas.length]))
  const order = [...ids].sort((a, b) => hash(a) - hash(b))
  const at = new Map<string, number>(order.map((id, i) => [id, i]))
  const n = order.length
  const X = new Float64Array(n), Y = new Float64Array(n)
  order.forEach((_, i) => { const rr = STEP * 0.9 * Math.sqrt(i + 0.5), a = i * 2.399963; X[i] = rr * Math.cos(a); Y[i] = rr * Math.sin(a) })
  const L = links.map(l => [at.get(l.src), at.get(l.dst)]).filter((p): p is [number, number] => p[0] !== undefined && p[1] !== undefined && p[0] !== p[1])
  const deg = new Float64Array(n); L.forEach(([a, b]) => { deg[a]++; deg[b]++ })
  const CELL = STEP * 3  // the grid for near neighbours (push apart only nearby cells: fast for many ideas)
  const axes = goals.map(g => { const a = g.angle * Math.PI / 180; return { ux: Math.cos(a), uy: Math.sin(a), score: (id: string) => g.scores[id] ?? 0.1 } })
  for (let it = 0, alpha = 1; it < 320; it++, alpha *= 0.985) {
    for (const ax of axes) for (let i = 0; i < n; i++) {  // a place along each goal's direction, by score
      const target = (ax.score(order[i]) - 0.45) * STEP * 14, proj = X[i] * ax.ux + Y[i] * ax.uy
      const f = (target - proj) * 0.06 * alpha
      X[i] += ax.ux * f; Y[i] += ax.uy * f
    }
    for (const [a, b] of L) {  // links pull to one hex apart
      const dx = X[b] - X[a], dy = Y[b] - Y[a], d = Math.hypot(dx, dy) || 1e-6
      const f = ((d - STEP) / d) * 0.35 * alpha / Math.max(1, Math.sqrt(Math.min(deg[a], deg[b])))
      X[a] += dx * f; Y[a] += dy * f; X[b] -= dx * f; Y[b] -= dy * f
    }
    const grid = new Map<string, number[]>()
    for (let i = 0; i < n; i++) { const k = `${Math.floor(X[i] / CELL)},${Math.floor(Y[i] / CELL)}`; (grid.get(k) ?? grid.set(k, []).get(k)!).push(i) }
    for (let i = 0; i < n; i++) {
      const gx = Math.floor(X[i] / CELL), gy = Math.floor(Y[i] / CELL)
      for (let ox = -1; ox <= 1; ox++) for (let oy = -1; oy <= 1; oy++) for (const j of grid.get(`${gx + ox},${gy + oy}`) ?? []) {
        if (j <= i) continue
        const dx = X[j] - X[i], dy = Y[j] - Y[i], d = Math.hypot(dx, dy) || 1e-3
        if (d >= CELL) continue
        const push = d < STEP * 0.98 ? (STEP * 0.98 - d) / d * 0.5 : (CELL - d) / d * 0.012 * alpha  // no overlap; a little room
        X[i] -= dx * push; Y[i] -= dy * push; X[j] += dx * push; Y[j] += dy * push
      }
    }
    for (let i = 0; i < n; i++) { X[i] *= 1 - 0.012 * alpha; Y[i] *= 1 - 0.012 * alpha }  // one piece of land
  }
  const used = new Set<string>(), out = new Map<string, Cell>(), gapCells = new Map<string, Cell[]>()
  const key = (q: number, r: number) => `${q},${r}`
  const free = (q: number, r: number): [number, number] => {
    if (!used.has(key(q, r))) return [q, r]
    for (let k = 1; k < 60; k++) {
      let c: [number, number] = [q - k, r + k]
      for (const [dq, dr] of DIRS) for (let i = 0; i < k; i++) { if (!used.has(key(...c))) return c; c = [c[0] + dq, c[1] + dr] }
    }
    return [q, r]
  }
  const byDegree = [...order.keys()].sort((a, b) => deg[b] - deg[a] || a - b)
  for (const i of byDegree) {
    const [q, r] = free(...roundHex(X[i], Y[i]))
    used.add(key(q, r))
    const [x, y] = toPix(q, r)
    const k = size.get(order[i])
    if (k === undefined) { out.set(order[i], { id: order[i], q, r, x, y }); continue }
    const mine: Cell[] = [{ id: order[i], q, r, x, y }]  // a gap: this hex and free neighbours, one per missing idea
    for (const [dq, dr] of DIRS) {
      if (mine.length >= k) break
      if (!used.has(key(q + dq, r + dr))) { used.add(key(q + dq, r + dr)); const [px, py] = toPix(q + dq, r + dr); mine.push({ id: order[i], q: q + dq, r: r + dr, x: px, y: py }) }
    }
    gapCells.set(order[i], mine)
  }
  const goalPlaces = new Map<string, GoalPlace>()
  for (const [gi, g] of goals.entries()) {
    const { ux, uy, score } = axes[gi]
    const pts = [...out.values()]
    const reach = pts.length ? Math.max(...pts.map(p => p.x * ux + p.y * uy)) : 0
    const [sq, sr] = free(...roundHex(ux * (reach + STEP * 3.5), uy * (reach + STEP * 3.5)))
    used.add(key(sq, sr))
    const [sx, sy] = toPix(sq, sr)
    const mine = pts.filter(p => score(p.id) >= 0.7)
    const cx = mine.length ? mine.reduce((s, p) => s + p.x, 0) / mine.length : 0, cy = mine.length ? mine.reduce((s, p) => s + p.y, 0) / mine.length : 0
    const blocks = g.blocks.map((b, i) => {
      const t = 0.62 + 0.07 * i, side = (i % 2 ? 1 : -1) * STEP * 1.6 * Math.ceil(i / 2)
      const ang = Math.atan2(sy - cy, sx - cx)
      const [q, r] = free(...roundHex(cx + (sx - cx) * t - Math.sin(ang) * side, cy + (sy - cy) * t + Math.cos(ang) * side))
      used.add(key(q, r))
      const [x, y] = toPix(q, r)
      return { ...b, x, y }
    })
    goalPlaces.set(g.id, { star: { x: sx, y: sy }, blocks })
  }
  return { cells: out, gapCells, goalPlaces }
}

const CORNERS = Array.from({ length: 6 }, (_, i) => { const a = Math.PI / 180 * (60 * i - 30); return [S * 0.95 * Math.cos(a), S * 0.95 * Math.sin(a)] })
const hexPoints = (x: number, y: number, k = 1) => CORNERS.map(([a, b]) => `${(x + a * k).toFixed(1)},${(y + b * k).toFixed(1)}`).join(' ')

interface Props {
  nodes: GraphNode[]; links: Link[]; selected: string | null; matches: Set<string>
  onSelect: (id: string | null) => void
  /** Open gaps (SPEC §51) and what to do when one is clicked. */
  gaps?: MapGap[]; onGap?: (id: string) => void; selectedGap?: string | null
  /** Goals on the map (SPEC §53): stars at their edges; a click opens the goal's panel. */
  goals?: MapGoal[]; onGoal?: (id: string) => void; selectedGoal?: string | null
  /** Pan to this idea (n changes every time it is asked for). */
  center?: { id: string; n: number } | null
  compact?: boolean; names?: boolean
}

const NO_GAPS: MapGap[] = []
const NO_GOALS: MapGoal[] = []

export default function HexMap({ nodes, links, selected, matches, onSelect, center, compact, names, gaps = NO_GAPS, onGap, selectedGap, goals = NO_GOALS, onGoal, selectedGoal }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const { cells, gapCells, goalPlaces } = useMemo(() => layoutCells(nodes.map(n => n.id), links, gaps, goals), [nodes, links, gaps, goals])
  // the goal a cell serves most (score 0.6 or more): a thin ring in that goal's color
  const ringOf = useMemo(() => {
    const m = new Map<string, string>()
    if (goals.length < 2) return m  // one goal: its glow and pull say enough; rings only tell several goals apart
    for (const n of nodes) {
      let best = 0.6, color = ''
      for (const g of goals) if ((g.scores[n.id] ?? 0) >= best) { best = g.scores[n.id]; color = g.color }
      if (color) m.set(n.id, color)
    }
    return m
  }, [nodes, goals])
  const byId = useMemo(() => new Map(nodes.map(n => [n.id, n])), [nodes])
  const near = useMemo(() => {
    const m = new Map<string, string[]>()
    for (const l of links) { (m.get(l.src) ?? m.set(l.src, []).get(l.src)!).push(l.dst); (m.get(l.dst) ?? m.set(l.dst, []).get(l.dst)!).push(l.src) }
    return m
  }, [links])
  const [view, setView] = useState({ x: 0, y: 0, k: 1 })
  const [hover, setHover] = useState<{ id: string; x: number; y: number } | null>(null)
  const [hoverGap, setHoverGap] = useState<{ id: string; x: number; y: number } | null>(null)
  const [hoverBlock, setHoverBlock] = useState<{ title: string; says: string; goal: string; x: number; y: number } | null>(null)
  const title = (id: string) => byId.get(id)?.title ?? id
  const drag = useRef<{ x: number; y: number; vx: number; vy: number; moved: boolean } | null>(null)

  const fitted = useRef(false)
  const fit = () => {
    const el = box.current
    // a hidden or not yet laid out box has no size: fitting then would scale the map to 0 (an empty map)
    if (!el || cells.size === 0 || el.clientWidth === 0 || el.clientHeight === 0) return
    fitted.current = true
    const stars = [...goalPlaces.values()].map(p => p.star)
    const xs = [...cells.values(), ...stars].map(c => c.x), ys = [...cells.values(), ...stars].map(c => c.y)
    const minX = Math.min(...xs) - S * 2, maxX = Math.max(...xs) + S * 2, minY = Math.min(...ys) - S * 2, maxY = Math.max(...ys) + S * 2
    const k = Math.min(compact ? 1.2 : 2, el.clientWidth / (maxX - minX), el.clientHeight / (maxY - minY))
    setView({ k, x: el.clientWidth / 2 - ((minX + maxX) / 2) * k, y: el.clientHeight / 2 - ((minY + maxY) / 2) * k })
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- fit when the map changes
  useEffect(fit, [cells])
  useEffect(() => {  // fit once the box gets its size
    const el = box.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => { if (!fitted.current) fit() })
    ro.observe(el)
    return () => ro.disconnect()
  // eslint-disable-next-line react-hooks/exhaustive-deps -- the newest fit is enough
  }, [cells])
  useEffect(() => {
    const c = center && cells.get(center.id), el = box.current
    if (!c || !el) return
    setView(v => { const k = Math.max(v.k, 1.4); return { k, x: el.clientWidth / 2 - c.x * k, y: el.clientHeight / 2 - c.y * k } })
  }, [center, cells])
  useEffect(() => {  // wheel zoom around the cursor (non-passive: the page must not scroll)
    const el = box.current
    if (!el || compact) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const r = el.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top
      setView(v => { const k = Math.min(5, Math.max(0.2, v.k * Math.exp(-e.deltaY * 0.0015))); return { k, x: mx - ((mx - v.x) / v.k) * k, y: my - ((my - v.y) / v.k) * k } })
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [compact])
  const zoom = (f: number) => {
    const el = box.current
    if (!el) return
    const mx = el.clientWidth / 2, my = el.clientHeight / 2
    setView(v => { const k = Math.min(5, Math.max(0.2, v.k * f)); return { k, x: mx - ((mx - v.x) / v.k) * k, y: my - ((my - v.y) / v.k) * k } })
  }

  const focus = hover?.id ?? selected
  const lit = focus ? new Set([focus, ...(near.get(focus) ?? [])]) : null
  const h = hover ? byId.get(hover.id) : undefined
  return (
    <div className={`hexmap${compact ? ' hexmap-compact' : ''}`} ref={box}
      onPointerDown={e => { if ((e.target as Element).closest('.hm-cell')) return; drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false }; (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId) }}
      onPointerMove={e => { const d = drag.current; if (d) { d.moved = d.moved || Math.abs(e.clientX - d.x) + Math.abs(e.clientY - d.y) > 3; setView(v => ({ ...v, x: d.vx + e.clientX - d.x, y: d.vy + e.clientY - d.y })) } }}
      onPointerUp={() => { const d = drag.current; drag.current = null; if (d && !d.moved) onSelect(null) }}>
      <svg className="hm-svg" role="img" aria-label={`Map of ${nodes.length} ideas`}>
        <defs>{goals.map(g => (
          <radialGradient key={g.id} id={`hm-glow-${g.id}`}><stop offset="0%" stopColor={g.color} stopOpacity={0.16} /><stop offset="100%" stopColor={g.color} stopOpacity={0} /></radialGradient>))}
        </defs>
        <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          {lit && focus && cells.get(focus) && (near.get(focus) ?? []).map(o => {
            const a = cells.get(focus)!, b = cells.get(o)
            return b ? <line key={o} className="hm-link" x1={a.x} y1={a.y} x2={b.x} y2={b.y} /> : null
          })}
          {goals.map(g => { const p = goalPlaces.get(g.id); return p ? (
            <circle key={`glow-${g.id}`} cx={p.star.x} cy={p.star.y} r={STEP * 9} fill={`url(#hm-glow-${g.id})`} pointerEvents="none" />) : null })}
          {goals.map(g => (goalPlaces.get(g.id)?.blocks ?? []).map(b => (
            <g key={`blk-${g.id}-${b.id}`} className="hm-block" onClick={e => { e.stopPropagation(); onGoal?.(g.id) }}
              onPointerEnter={e => { const r = box.current!.getBoundingClientRect(); setHoverBlock({ title: b.title, says: b.says, goal: g.title, x: e.clientX - r.left, y: e.clientY - r.top }) }}
              onPointerLeave={() => setHoverBlock(null)}>
              <polygon points={hexPoints(b.x, b.y)} style={{ stroke: g.color }} />
            </g>)))}
          {!compact && gaps.map(g => (gapCells.get(g.id) ?? []).map((c, i) => (
            <g key={`${g.id}-${i}`} className={`hm-gap${g.id === selectedGap ? ' hm-gap-selected' : ''}`}
              onPointerEnter={e => { const r = box.current!.getBoundingClientRect(); setHoverGap({ id: g.id, x: e.clientX - r.left, y: e.clientY - r.top }) }}
              onPointerLeave={() => setHoverGap(null)}
              onClick={e => { e.stopPropagation(); onGap?.(g.id) }}>
              <polygon points={hexPoints(c.x, c.y)} />
              {i === 0 && <text x={c.x} y={c.y + 4}>+</text>}
            </g>)))}
          {nodes.map(n => {
            const c = cells.get(n.id)
            if (!c) return null
            const st = cellState(n.state)
            const cls = ['hm-cell', `hm-${st}`, n.id === selected && 'hm-selected', matches.has(n.id) && 'hm-match',
              ((lit && !lit.has(n.id)) || (matches.size > 0 && !matches.has(n.id))) && 'hm-dim']
              .filter(Boolean).join(' ')
            return (
              <polygon key={n.id} className={cls} points={hexPoints(c.x, c.y)}
                onPointerEnter={e => { const r = box.current!.getBoundingClientRect(); setHover({ id: n.id, x: e.clientX - r.left, y: e.clientY - r.top }) }}
                onPointerMove={e => { const r = box.current!.getBoundingClientRect(); setHover({ id: n.id, x: e.clientX - r.left, y: e.clientY - r.top }) }}
                onPointerLeave={() => setHover(null)}
                onClick={e => { e.stopPropagation(); onSelect(n.id === selected ? null : n.id) }} />
            )
          })}
          {nodes.map(n => { const c = cells.get(n.id), col = ringOf.get(n.id); return c && col
            ? <polygon key={`ring-${n.id}`} className="hm-ring" points={hexPoints(c.x, c.y, 0.6)} style={{ stroke: col }} /> : null })}
          {goals.map(g => { const p = goalPlaces.get(g.id); return p ? (
            <g key={`star-${g.id}`} className={`hm-star${g.id === selectedGoal ? ' hm-star-on' : ''}`} onClick={e => { e.stopPropagation(); onGoal?.(g.id) }}>
              <polygon points={hexPoints(p.star.x, p.star.y, 1.3)} style={{ stroke: g.color }} />
              <text x={p.star.x} y={p.star.y + 7} style={{ fill: g.color }} className="hm-star-icon">★</text>
              {!compact && <text x={p.star.x} y={p.star.y + S * 2.2} style={{ fill: g.color }} className="hm-star-name">{g.title.length > 36 ? g.title.slice(0, 34) + '…' : g.title}</text>}
            </g>) : null })}
          {names && view.k > 0.8 && nodes.map(n => {
            const c = cells.get(n.id)
            return c ? <text key={n.id} className="hm-name" x={c.x} y={c.y + S + 9}>{n.title.length > 22 ? n.title.slice(0, 20) + '…' : n.title}</text> : null
          })}
        </g>
      </svg>
      {!compact && <div className="hm-zoom">
        <button className="btn btn-small" onClick={() => zoom(1.25)} aria-label="Zoom in">+</button>
        <button className="btn btn-small" onClick={() => zoom(0.8)} aria-label="Zoom out">−</button>
        <button className="btn btn-small" onClick={fit}>Fit</button>
      </div>}
      {hoverBlock && (
        <div className="hm-tip" style={{ left: Math.min(hoverBlock.x + 14, (box.current?.clientWidth ?? 600) - 270), top: hoverBlock.y + 14 }}>
          <b><Markdown inline>{hoverBlock.title}</Markdown></b>
          <span className="muted">A building block of “{hoverBlock.goal}”, not on your map yet. {hoverBlock.says}</span>
          <span className="small muted">Click to see the goal.</span>
        </div>)}
      {hoverGap && (() => {
        const g = gaps.find(x => x.id === hoverGap.id)
        return g ? (
          <div className="hm-tip" style={{ left: Math.min(hoverGap.x + 14, (box.current?.clientWidth ?? 600) - 270), top: hoverGap.y + 14 }}>
            <b>Something is missing here</b>
            <span className="muted">Between <Markdown inline>{title(g.between[0])}</Markdown> and <Markdown inline>{title(g.between[1])}</Markdown>:{' '}
              {g.ideas.map(i => i.title).join(', ')}.</span>
            <span className="small muted">Click to add it to your map.</span>
          </div>) : null
      })()}
      {h && hover && (
        <div className="hm-tip" style={{ left: Math.min(hover.x + 14, (box.current?.clientWidth ?? 600) - 270), top: hover.y + 14 }}>
          <b><Markdown inline>{h.title}</Markdown></b>
          <span className={`hm-tip-state hm-tip-${cellState(h.state)}`}>{h.kind === 'formula' ? 'Formula · ' : h.step ? `Step of “${h.step.lesson}” · ` : ''}{CELL_LABEL[cellState(h.state)]}</span>
          {h.statement && <span className="muted"><Markdown inline>{h.statement.length > 200 ? h.statement.slice(0, 198) + '…' : h.statement}</Markdown></span>}
          <span className="small muted">{h.books.length + h.sessions.length > 0 ? `${h.books.length + h.sessions.length} source${h.books.length + h.sessions.length > 1 ? 's' : ''} · ` : ''}click to see them</span>
        </div>
      )}
    </div>
  )
}
