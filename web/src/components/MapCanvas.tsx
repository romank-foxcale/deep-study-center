import { useEffect, useMemo, useRef, useState } from 'react'
import { hierarchy, pack, type HierarchyCircularNode } from 'd3-hierarchy'
import type { GraphNode, MapCluster, MapViewId } from '../types'
import { areaColor, ESSENTIAL_COLOR, FIELD_COLORS, FIELD_ORDER, fieldColors, UNSORTED_COLOR } from '../areaColors'

// The knowledge map's canvas views (SPEC §29). Same data, three layouts the learner can choose from:
//  wheel      — round skill tree: the main goal's basics in the core, each book a sector, each chapter a spoke
//  cells      — circle packing: book > chapter > idea, sized by the number of ideas
//  territory  — hex world map: every idea a hex, every book a country, learning lights the land
// Each book or goal has its fixed area color (areaColors.ts), the same as on its book card.
// Clusters, chapters and the reading order come from the backend (graph.view); depth (the longest prerequisite chain
// inside a cluster) is computed here.

export type CanvasView = Exclude<MapViewId, 'tree'>
const STATE_LABEL: Record<string, string> = {
  mastered: 'know strongly', learned: 'learned', learning: 'learning', rusty: 'due for review', ready: 'ready to learn',
  locked: 'needs others first', pending: 'not started',
}

interface C { id: string; title: string; kind: string; color: string; nodes: N[]; maxDepth: number; cx: number; cy: number; a0?: number; a1?: number; lx?: number; ly?: number }
interface N {
  id: string; title: string; state: string; mastery: number; c: C; also: C[]; chapter: number; chapterTitle: string; order: number
  idx: number; depth: number; prereqs: N[]; next: N[]; px: number; py: number; pr: number; formula: boolean; step: string | null; fields: string[]
}
interface L { s: N; t: N; cross: boolean }
interface Props {
  view: CanvasView; nodes: GraphNode[]; links: { src: string; dst: string }[]; clusters: MapCluster[]
  selected: string | null; matches: Set<string>; center: { id: string; n: number } | null; onSelect: (id: string | null) => void
  /** A small map inside a card: no zoom buttons, and the wheel scrolls the page. */
  compact?: boolean
  /** The field names, for the provinces of the Formulas country in the legend. */
  fields?: { id: string; title: string }[]
}

const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()
const rgba = (hex: string, a: number) => {
  const h = hex.replace('#', ''), f = h.length === 3 ? h.split('').map(x => x + x).join('') : h
  const n = parseInt(f, 16)
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`
}
const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / Math.max(1, xs.length)
const GOLDEN = 2.39996

function build(nodes: GraphNode[], links: { src: string; dst: string }[], clusters: MapCluster[]) {
  const cs = new Map<string, C>()
  clusters.forEach(c => cs.set(c.id, { id: c.id, title: c.title, kind: c.kind, color: areaColor(c.color), nodes: [], maxDepth: 1, cx: 0, cy: 0 }))
  const loose = (id: string) => { if (!cs.has(id)) cs.set(id, { id, title: 'Other ideas', kind: 'loose', color: areaColor(-1), nodes: [], maxDepth: 1, cx: 0, cy: 0 }); return cs.get(id)! }
  const ns: N[] = nodes.map(g => {
    const c = cs.get(g.cluster) ?? loose(g.cluster || 'loose')
    const n: N = { id: g.id, title: g.title, state: g.state, mastery: g.mastery, c, also: (g.also ?? []).map(a => cs.get(a)).filter((x): x is C => !!x),
      chapter: g.chapter ?? 0, chapterTitle: g.chapterTitle ?? '', order: g.order ?? 0, idx: 0, depth: 0, prereqs: [], next: [], px: 0, py: 0, pr: 4, formula: g.kind === 'formula', step: g.step?.lesson ?? null, fields: (g.fields ?? []).filter(f => FIELD_COLORS[f]) }
    c.nodes.push(n)
    return n
  })
  const by = new Map(ns.map(n => [n.id, n]))
  const ls: L[] = []
  for (const l of links) {
    const s = by.get(l.src), t = by.get(l.dst)
    if (!s || !t || s === t) continue
    ls.push({ s, t, cross: s.c !== t.c }); t.prereqs.push(s); s.next.push(t)
  }
  const cl = [...cs.values()].filter(c => c.nodes.length)
  for (const c of cl) {
    c.nodes.sort((a, b) => a.order - b.order || a.title.localeCompare(b.title))
    c.nodes.forEach((n, i) => { n.idx = i })
    const memo = new Map<N, number>()
    const depth = (n: N, path: Set<N>): number => {
      if (memo.has(n)) return memo.get(n)!
      if (path.has(n)) return 1
      path.add(n)
      const d = 1 + Math.max(0, ...n.prereqs.filter(p => p.c === c).map(p => depth(p, path)))
      path.delete(n); memo.set(n, d)
      return d
    }
    for (const n of c.nodes) n.depth = depth(n, new Set())
    c.maxDepth = Math.max(1, ...c.nodes.map(n => n.depth))
  }
  cl.sort((a, b) => b.nodes.length - a.nodes.length)
  return { ns, ls, cl, by }
}

type Model = ReturnType<typeof build>

// ------------------------------------------------------------------ layouts (world coordinates in a W x H box)

function layoutWheel(m: Model, W: number, H: number) {
  const cx = W / 2, cy = H / 2, R = Math.min(W, H) / 2 - 34
  const core = m.cl.find(c => c.kind === 'goal') ?? null
  const outer = m.cl.filter(c => c !== core)
  const coreR = core ? R * 0.24 : R * 0.12
  if (core) core.nodes.forEach((n, i) => { const a = i * GOLDEN, r = coreR * Math.sqrt((i + 0.5) / core.nodes.length); n.px = cx + Math.cos(a) * r; n.py = cy + Math.sin(a) * r; n.pr = 4.5 })
  const total = outer.reduce((s, c) => s + c.nodes.length, 0)
  let a0 = -Math.PI / 2
  const gap = outer.length > 1 ? 0.06 : 0
  for (const c of outer) {
    const span = (c.nodes.length / Math.max(1, total)) * Math.PI * 2 - gap
    c.a0 = a0 + gap / 2; c.a1 = c.a0 + span; a0 += span + gap
    const chapters = [...new Set(c.nodes.map(n => n.chapter))].sort((a, b) => a - b)
    let s0 = c.a0
    const midR = (coreR + R) / 2
    for (const ch of chapters) { // each chapter is a spoke from the core (its basics) to the rim
      const list = c.nodes.filter(n => n.chapter === ch).sort((a, b) => a.depth - b.depth || a.idx - b.idx)
      const sspan = span * (list.length / c.nodes.length)
      const cols = Math.max(1, Math.min(4, Math.round((sspan * midR) / 16))), rows = Math.ceil(list.length / cols)
      list.forEach((n, i) => {
        const row = Math.floor(i / cols), col = i % cols
        const r = coreR + 26 + (R - coreR - 34) * (rows > 1 ? row / (rows - 1) : 0.5)
        const a = s0 + sspan * ((col + 0.5 + (cols > 1 ? (row % 2 ? 0.25 : -0.25) : 0)) / cols)
        n.px = cx + Math.cos(a) * r; n.py = cy + Math.sin(a) * r; n.pr = 3.8
      })
      s0 += sspan
    }
    const mid = (c.a0 + c.a1) / 2
    c.lx = cx + Math.cos(mid) * (R + 4); c.ly = cy + Math.sin(mid) * (R + 4)
  }
  return { cx, cy, R, coreR, core }
}

function layoutCells(m: Model, W: number, H: number) {
  type D = { c?: C; ch?: number; title?: string; n?: N; children?: D[] }
  const root = hierarchy<D>({ children: m.cl.map(c => ({ c, children: [...new Set(c.nodes.map(n => n.chapter))].map(ch => ({ c, ch, title: c.nodes.find(n => n.chapter === ch)?.chapterTitle, children: c.nodes.filter(n => n.chapter === ch).map(n => ({ n })) })) })) })
    .sum(d => (d.n ? 1 : 0)).sort((a, b) => (b.value ?? 0) - (a.value ?? 0))
  pack<D>().size([W - 20, H - 20]).padding(d => (d.depth === 0 ? 14 : d.depth === 1 ? 6 : 2))(root)
  const packed = root as HierarchyCircularNode<D>
  for (const leaf of packed.leaves()) { const n = leaf.data.n!; n.px = leaf.x + 10; n.py = leaf.y + 10; n.pr = Math.max(2.4, Math.min(5.5, leaf.r * 0.72)) }
  return { books: packed.children ?? [], chapters: packed.descendants().filter(d => d.depth === 2) }
}

function layoutTerritory(m: Model, W: number, H: number) {
  const total = m.ns.length, s3 = Math.sqrt(3)
  const radius = Math.ceil(Math.sqrt(total / 2.2)) + 3
  type Cell = { q: number; r: number; owner: C | null; node?: N }
  const cells = new Map<string, Cell>(), key = (q: number, r: number) => `${q},${r}`
  for (let q = -radius; q <= radius; q++) for (let r = -radius; r <= radius; r++) if (Math.abs(q + r) <= radius) cells.set(key(q, r), { q, r, owner: null })
  const dirs = [[1, 0], [1, -1], [0, -1], [-1, 0], [-1, 1], [0, 1]]
  const dist = (a: number[], b: number[]) => (Math.abs(a[0] - b[0]) + Math.abs(a[0] + a[1] - b[0] - b[1]) + Math.abs(a[1] - b[1])) / 2
  const seeds = new Map<C, number[]>()
  const ring = Math.round(radius * 0.55)
  const middle = m.cl.find(c => c.kind === 'goal') ?? m.cl[0] // the goal's basics in the middle, books around them
  const around = m.cl.filter(c => c !== middle)
  seeds.set(middle, [0, 0])
  around.forEach((c, i) => {
    const a = (i / Math.max(1, around.length)) * Math.PI * 2 + 0.4
    seeds.set(c, [Math.round(Math.cos(a) * ring), Math.round(Math.sin(a) * ring - (Math.cos(a) * ring) / 2)])
  })
  const owned = new Map<C, Cell[]>(m.cl.map(c => [c, []]))
  for (const c of m.cl) { const s = cells.get(key(seeds.get(c)![0], seeds.get(c)![1])); if (s && !s.owner) { s.owner = c; owned.get(c)!.push(s) } }
  const stuck = new Set<C>()
  for (;;) {
    const order = m.cl.filter(c => !stuck.has(c) && owned.get(c)!.length < c.nodes.length)
      .sort((a, b) => owned.get(a)!.length / a.nodes.length - owned.get(b)!.length / b.nodes.length)
    if (!order.length) break
    const c = order[0], seedC = seeds.get(c)!
    let best: Cell | null = null, bd = 1e9
    for (const cell of owned.get(c)!.length ? owned.get(c)! : [{ q: seedC[0], r: seedC[1], owner: null }]) for (const [dq, dr] of dirs) {
      const nb = cells.get(key(cell.q + dq, cell.r + dr)); if (!nb || nb.owner) continue
      const d = dist([nb.q, nb.r], seedC) + ((nb.q * 7 + nb.r * 13) % 5) * 0.1; if (d < bd) { bd = d; best = nb }
    }
    if (best) { best.owner = c; owned.get(c)!.push(best) } else stuck.add(c)
  }
  const size = Math.min((W - 30) / ((radius * 2 + 1) * s3), (H - 30) / ((radius * 2 + 1) * 1.5))
  const placed: Cell[] = []
  const touching = (cell: Cell, c: C) => dirs.some(([dq, dr]) => { const nb = cells.get(key(cell.q + dq, cell.r + dr)); return !!nb && !!nb.owner && nb.owner !== c })
  for (const c of m.cl) {
    if (c.kind === 'formulas') {  // provinces by field (SPEC §41)
      for (const [cell, n] of placeFormulas(owned.get(c)!, c.nodes)) {
        cell.node = n; n.px = W / 2 + size * s3 * (cell.q + cell.r / 2); n.py = H / 2 + size * 1.5 * cell.r; n.pr = size * 0.8; placed.push(cell)
      }
      continue
    }
    const seedC = seeds.get(c)!
    const list = owned.get(c)!.slice().sort((a, b) => dist([a.q, a.r], seedC) - dist([b.q, b.r], seedC))
    const ideas = c.nodes.slice().sort((a, b) => a.depth - b.depth || a.idx - b.idx) // basics at the heart
    const shared = ideas.filter(n => n.also.length), plain = ideas.filter(n => !n.also.length)
    const border = list.filter(cell => touching(cell, c)).reverse(), inner = list.filter(cell => !border.includes(cell))
    const slots = [...inner, ...border], assign = [...plain.slice(0, inner.length), ...shared, ...plain.slice(inner.length)]
    slots.forEach((cell, i) => {
      const n = assign[i]; if (!n) return
      cell.node = n; n.px = W / 2 + size * s3 * (cell.q + cell.r / 2); n.py = H / 2 + size * 1.5 * cell.r; n.pr = size * 0.8; placed.push(cell)
    })
    c.lx = mean(list.map(cell => W / 2 + size * s3 * (cell.q + cell.r / 2))); c.ly = mean(list.map(cell => H / 2 + size * 1.5 * cell.r))
  }
  for (const n of m.ns) if (!placed.some(c => c.node === n)) { n.px = -9999; n.py = -9999 } // boxed in (very rare)
  return { size, placed, cells, key, dirs }
}

/** The province key of a formula: its sorted fields, "essential" for 4 or more, "" when not sorted yet. */
const provinceOf = (n: N) => (n.fields.length >= 4 ? 'essential' : [...n.fields].sort().join('+'))

/** Places formulas inside the Formulas country (SPEC §41). Each field present gets a seed on a ring around the country's
 *  middle (in ring order, so related fields are neighbours). A formula in 1 field goes near its field's seed; in 2 or 3
 *  fields, near the middle point of those seeds (where the provinces meet); in 4 or more, at the middle ("Essential").
 *  Formulas with more fields are placed first, each on the free cell nearest to its point. */
function placeFormulas<T extends { q: number; r: number }>(cells: T[], nodes: N[]): [T, N][] {
  const xy = (q: number, r: number) => [Math.sqrt(3) * (q + r / 2), 1.5 * r]
  const pts = cells.map(c => xy(c.q, c.r))
  const cx = mean(pts.map(p => p[0])), cy = mean(pts.map(p => p[1]))
  const present = FIELD_ORDER.filter(f => nodes.some(n => n.fields.length < 4 && n.fields.includes(f)))
  if (nodes.some(n => !n.fields.length)) present.push('')  // "Not sorted yet" gets a place on the ring too
  const rad = Math.sqrt(cells.length) * 0.62
  const seed = new Map(present.map((f, i) => {
    const a = (i / Math.max(1, present.length)) * Math.PI * 2 - Math.PI / 2
    return [f, present.length > 1 ? [cx + Math.cos(a) * rad, cy + Math.sin(a) * rad] : [cx, cy]] as const
  }))
  const target = (n: N) => {
    if (n.fields.length >= 4) return [cx, cy]
    const ps = (n.fields.length ? n.fields : ['']).map(f => seed.get(f) ?? [cx, cy])
    const k = n.fields.length > 1 ? 0.85 : 1  // a shared formula a little toward the middle, where its provinces meet
    return [cx + (mean(ps.map(p => p[0])) - cx) * k, cy + (mean(ps.map(p => p[1])) - cy) * k]
  }
  const free = new Set(cells.map((_, i) => i))
  const out: [T, N][] = []
  for (const n of nodes.slice().sort((a, b) => b.fields.length - a.fields.length || a.order - b.order)) {
    const [tx, ty] = target(n)
    let best = -1, bd = Infinity
    for (const i of free) { const d = (pts[i][0] - tx) ** 2 + (pts[i][1] - ty) ** 2; if (d < bd) { bd = d; best = i } }
    if (best < 0) break
    free.delete(best); out.push([cells[best], n])
  }
  return out
}

// ------------------------------------------------------------------ the component

export default function MapCanvas({ view, nodes, links, clusters, selected, matches, center, onSelect, compact, fields }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const cv = useRef<HTMLCanvasElement>(null)
  const tipRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ W: 800, H: 600 })
  const model = useMemo(() => build(nodes, links, clusters), [nodes, links, clusters])
  const geo = useRef<Record<string, unknown>>({})
  const t = useRef({ x: 0, y: 0, k: 1 })
  const hover = useRef<N | null>(null)
  const drag = useRef<{ x: number; y: number; tx: number; ty: number; moved: boolean } | null>(null)
  // touch: the fingers on the canvas, and the start of a two-finger pinch (distance, zoom and pan at that moment)
  const touches = useRef(new Map<number, { x: number; y: number }>())
  const pinch = useRef<{ d: number; k: number; x: number; y: number } | null>(null)
  const spread = () => { const p = [...touches.current.values()]; return p.length < 2 ? 1 : Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y) }
  const raf = useRef(0)
  const drawRef = useRef<() => void>(() => {})

  useEffect(() => {
    const el = box.current
    if (!el) return
    const measure = () => setSize(s => (s.W === el.clientWidth && s.H === el.clientHeight ? s : { W: el.clientWidth, H: el.clientHeight }))
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // layout when the data, the view or the size change
  useEffect(() => {
    const { W, H } = size
    t.current = { x: 0, y: 0, k: 1 }
    if (view === 'wheel') geo.current = layoutWheel(model, W, H)
    else if (view === 'cells') geo.current = layoutCells(model, W, H)
    else geo.current = layoutTerritory(model, W, H)
    drawRef.current()
  }, [model, view, size])

  // center on an idea the page asked for (search, panel links)
  useEffect(() => {
    if (!center) return
    const n = model.by.get(center.id)
    if (!n) return
    const { W, H } = size, k = Math.max(t.current.k, 1.4)
    t.current = { k, x: W / 2 - n.px * k, y: H / 2 - n.py * k }
    drawRef.current()
  }, [center, model, view, size])

  // drawing
  useEffect(() => {
    const canvas = cv.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    const { W, H } = size
    const DPR = Math.min(2, window.devicePixelRatio || 1)
    canvas.width = W * DPR; canvas.height = H * DPR
    const draw = () => {
      cancelAnimationFrame(raf.current)
      raf.current = requestAnimationFrame(() => paint(ctx, DPR))
    }
    drawRef.current = draw
    draw()
    return () => cancelAnimationFrame(raf.current)
    // paint reads refs and props through closure; re-bind when they change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size, view, model, selected, matches])

  function paint(ctx: CanvasRenderingContext2D, DPR: number) {
    const { W, H } = size
    const col = { bg: css('--bg'), fg: css('--text'), muted: css('--muted'), surface: css('--surface'), accent: css('--accent'), dark: css('color-scheme').includes('dark') }
    const st: Record<string, string> = {
      mastered: css('--st-mastered'), learned: css('--st-learned'), learning: css('--st-learning'), rusty: css('--st-rusty'),
      ready: css('--st-ready'), locked: css('--st-locked'), pending: css('--st-ready'),
    }
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0)
    ctx.clearRect(0, 0, W, H)
    const { x: tx, y: ty, k } = t.current
    const sel = selected ? model.by.get(selected) ?? null : null
    const focus = hover.current ?? sel
    const near = focus ? new Set<N>([focus, ...focus.prereqs, ...focus.next]) : null
    const dim = (n: N) => (near && !near.has(n) ? 0.35 : 1)
    const world = () => ctx.setTransform(DPR * k, 0, 0, DPR * k, DPR * tx, DPR * ty)
    const screen = () => ctx.setTransform(DPR, 0, 0, DPR, 0, 0)

    const dot = (n: N, x: number, y: number, r: number, alpha: number) => {
      const c = st[n.state] ?? st.ready
      ctx.globalAlpha = alpha
      if (n.state === 'mastered') {
        const g = ctx.createRadialGradient(x, y, 0, x, y, r * 3.2)
        g.addColorStop(0, rgba(c, col.dark ? 0.55 : 0.4)); g.addColorStop(1, rgba(c, 0))
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r * 3.2, 0, 7); ctx.fill()
      }
      ctx.beginPath(); ctx.arc(x, y, r, 0, 7)
      if (n.state === 'ready' || n.state === 'pending') { ctx.fillStyle = col.surface; ctx.fill(); ctx.lineWidth = 1.4; ctx.strokeStyle = c; ctx.stroke() }
      else if (n.state === 'learning') {
        ctx.fillStyle = col.surface; ctx.fill(); ctx.lineWidth = 1.6; ctx.strokeStyle = c; ctx.stroke()
        ctx.beginPath(); ctx.moveTo(x, y); ctx.arc(x, y, r, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * Math.max(0.15, n.mastery)); ctx.closePath(); ctx.fillStyle = c; ctx.fill()
      } else { ctx.fillStyle = c; ctx.fill() }
      if (n.also.length) { ctx.beginPath(); ctx.arc(x, y, r + 2.4, 0, 7); ctx.lineWidth = 1.5; ctx.strokeStyle = n.also[0].color; ctx.stroke() }
      if (matches.has(n.id) || n === sel) { ctx.beginPath(); ctx.arc(x, y, r + 4.5, 0, 7); ctx.lineWidth = 2; ctx.strokeStyle = n === sel ? col.fg : col.accent; ctx.stroke() }
      ctx.globalAlpha = 1
    }
    const edge = (l: L, base: number) => {
      const on = !!focus && (l.s === focus || l.t === focus)
      return on ? { a: 0.95, w: 1.6, c: col.fg } : { a: focus ? base * 0.35 : l.cross ? base * 0.6 : base, w: 0.8, c: col.muted }
    }
    const label = (c: C, x: number, y: number) => {
      if (compact) return  // a small map: no cluster names
      screen()
      const sx = x * k + tx, sy = y * k + ty
      ctx.font = `600 ${W < 600 ? 11 : 13}px system-ui, sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
      const known = c.nodes.filter(n => ['mastered', 'learned', 'rusty'].includes(n.state)).length
      const txt = c.title.length > 42 ? c.title.slice(0, 40) + '…' : c.title
      ctx.lineWidth = 4; ctx.strokeStyle = rgba(col.bg.startsWith('#') ? col.bg : '#000000', 0.85)
      ctx.strokeText(txt, sx, sy); ctx.fillStyle = c.color; ctx.fillText(txt, sx, sy)
      ctx.font = '400 10px ui-monospace, monospace'; ctx.fillStyle = col.muted
      ctx.strokeText(`${known}/${c.nodes.length} ideas`, sx, sy + 15); ctx.fillText(`${known}/${c.nodes.length} ideas`, sx, sy + 15)
      world()
    }
    const lines = (base: number, only?: (l: L) => boolean, curve?: (l: L) => [number, number] | null) => {
      for (const l of model.ls) {
        if (only && !only(l)) continue
        const e = edge(l, base)
        ctx.strokeStyle = rgba(e.c.startsWith('#') ? e.c : '#8b95aa', e.a); ctx.lineWidth = e.w / k
        ctx.beginPath(); ctx.moveTo(l.s.px, l.s.py)
        const q = curve?.(l)
        if (q) ctx.quadraticCurveTo(q[0], q[1], l.t.px, l.t.py); else ctx.lineTo(l.t.px, l.t.py)
        ctx.stroke()
      }
    }

    world()

    if (view === 'wheel') {
      const g0 = geo.current as ReturnType<typeof layoutWheel>
      for (const c of model.cl) {
        if (c === g0.core || c.a0 === undefined) continue
        const g = ctx.createRadialGradient(g0.cx, g0.cy, g0.coreR, g0.cx, g0.cy, g0.R + 10)
        g.addColorStop(0, rgba(c.color, 0.04)); g.addColorStop(1, rgba(c.color, col.dark ? 0.16 : 0.12))
        ctx.fillStyle = g; ctx.beginPath(); ctx.moveTo(g0.cx, g0.cy); ctx.arc(g0.cx, g0.cy, g0.R + 10, c.a0, c.a1!); ctx.closePath(); ctx.fill()
      }
      if (g0.core) { ctx.fillStyle = rgba(g0.core.color, 0.13); ctx.beginPath(); ctx.arc(g0.cx, g0.cy, g0.coreR + 8, 0, 7); ctx.fill() }
      lines(0.45, l => !l.cross || l.s === focus || l.t === focus, l => (l.cross ? [g0.cx, g0.cy] : null))
      for (const n of model.ns) dot(n, n.px, n.py, n === focus ? 6 : n.pr, dim(n))
      for (const c of model.cl) {
        if (c === g0.core) label(c, g0.cx, g0.cy + g0.coreR + 22)
        else label(c, Math.max(90, Math.min(W - 90, c.lx ?? 0)), Math.max(16, Math.min(H - 30, c.ly ?? 0)))
      }
      return
    }
    if (view === 'cells') {
      const g0 = geo.current as ReturnType<typeof layoutCells>
      for (const b of g0.books) {
        const c = b.data.c!
        ctx.fillStyle = rgba(c.color, 0.1); ctx.strokeStyle = rgba(c.color, 0.55); ctx.lineWidth = 1.2 / k
        ctx.beginPath(); ctx.arc(b.x + 10, b.y + 10, b.r, 0, 7); ctx.fill(); ctx.stroke()
      }
      for (const ch of g0.chapters) {
        const on = !!focus && focus.c === ch.data.c && focus.chapter === ch.data.ch
        ctx.fillStyle = rgba(ch.data.c!.color, on ? 0.16 : 0.06); ctx.strokeStyle = rgba(ch.data.c!.color, on ? 0.6 : 0.2); ctx.lineWidth = 1 / k
        ctx.beginPath(); ctx.arc(ch.x + 10, ch.y + 10, ch.r, 0, 7); ctx.fill(); ctx.stroke()
      }
      lines(0.5, l => l.cross || l.s === focus || l.t === focus, l => {
        const mx = (l.s.px + l.t.px) / 2, my = (l.s.py + l.t.py) / 2, dx = l.t.px - l.s.px, dy = l.t.py - l.s.py
        return [mx - dy * 0.25, my + dx * 0.25]
      })
      for (const n of model.ns) dot(n, n.px, n.py, n === focus ? n.pr + 2 : n.pr, dim(n))
      for (const b of g0.books) label(b.data.c!, b.x + 10, Math.max(16, b.y + 10 - b.r + 14))
      if (focus) {
        const ch = g0.chapters.find(c => c.data.c === focus.c && c.data.ch === focus.chapter)
        if (ch?.data.title) { screen(); ctx.font = '500 11px system-ui, sans-serif'; ctx.textAlign = 'center'; ctx.fillStyle = col.fg; ctx.fillText(ch.data.title, (ch.x + 10) * k + tx, (ch.y + 10 + ch.r) * k + ty + 12); world() }
      }
      return
    }
    if (view === 'territory') {
      const g0 = geo.current as ReturnType<typeof layoutTerritory>
      const s = g0.size
      const corner = (x: number, y: number, i: number, kk = 1) => { const a = (Math.PI / 180) * (60 * i - 30); return [x + s * kk * Math.cos(a), y + s * kk * Math.sin(a)] }
      for (const cell of g0.placed) {
        const n = cell.node!, x = n.px, y = n.py, c = st[n.state] ?? st.ready
        ctx.beginPath(); for (let i = 0; i < 6; i++) { const [px, py] = corner(x, y, i, 0.94); if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py) } ctx.closePath()
        const lit = ({ mastered: 0.95, learned: 0.62, rusty: 0.7, learning: 0.5 } as Record<string, number>)[n.state] ?? 0
        ctx.globalAlpha = dim(n)
        if (n.formula) {  // a formula: its fields (one slice each, the same split form for every hex), its state inside
          const cols = fieldColors(n.fields)
          ctx.save(); ctx.clip()
          cols.forEach((fc, i) => {
            const a0 = -Math.PI / 4 + (i * 2 * Math.PI) / cols.length
            ctx.beginPath(); ctx.moveTo(x, y); ctx.arc(x, y, s * 1.2, a0, a0 + (2 * Math.PI) / cols.length); ctx.closePath()
            ctx.fillStyle = rgba(fc, 0.42); ctx.fill()
          })
          ctx.restore()
          if (lit) {
            ctx.beginPath(); for (let i = 0; i < 6; i++) { const [px, py] = corner(x, y, i, 0.5); if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py) } ctx.closePath()
            ctx.fillStyle = rgba(c, Math.min(1, lit + 0.25)); ctx.fill()
          }
          ctx.beginPath(); for (let i = 0; i < 6; i++) { const [px, py] = corner(x, y, i, 0.94); if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py) } ctx.closePath()
        } else {
          ctx.fillStyle = rgba(n.c.color, n.state === 'locked' ? 0.07 : 0.17); ctx.fill()
          if (lit) { ctx.fillStyle = rgba(c, lit); ctx.fill() }
        }
        if (n.also.length) { ctx.strokeStyle = n.also[0].color; ctx.lineWidth = 1.6 / k; ctx.stroke() }
        if (n === focus || n === sel || matches.has(n.id)) { ctx.strokeStyle = n === sel || n === focus ? col.fg : col.accent; ctx.lineWidth = 2 / k; ctx.stroke() }
        ctx.globalAlpha = 1
      }
      ctx.lineWidth = 2 / k
      for (const cell of g0.placed) {
        g0.dirs.forEach(([dq, dr], i) => {
          const nb = g0.cells.get(g0.key(cell.q + dq, cell.r + dr))
          const province = nb && nb.owner === cell.owner && cell.node!.formula && nb.node && provinceOf(nb.node) !== provinceOf(cell.node!)
          if (nb && nb.owner === cell.owner && !province) return
          const side = [0, 5, 4, 3, 2, 1][i]
          const [ax, ay] = corner(cell.node!.px, cell.node!.py, side), [bx, by] = corner(cell.node!.px, cell.node!.py, (side + 1) % 6)
          if (province) {  // a thin dashed line between two provinces of the Formulas country
            ctx.save(); ctx.setLineDash([3 / k, 3 / k]); ctx.lineWidth = 1 / k; ctx.strokeStyle = rgba(col.fg, 0.35)
            ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke(); ctx.restore(); return
          }
          ctx.strokeStyle = rgba(cell.owner!.color, 0.85); ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke()
        })
      }
      if (focus) lines(1, l => l.s === focus || l.t === focus)
      // the country names are in the legend under the map (AreaLegend), not on the land
    }
  }

  // ------------------------------------------------------------------ interaction
  function pick(mx: number, my: number): N | null {
    const { x: tx, y: ty, k } = t.current
    let best: N | null = null, bd = 14 * 14
    for (const n of model.ns) {
      const sx = n.px * k + tx, sy = n.py * k + ty
      const d = (sx - mx) ** 2 + (sy - my) ** 2
      if (d < bd) { bd = d; best = n }
    }
    return best
  }
  const local = (e: { clientX: number; clientY: number }) => { const r = cv.current!.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top] }
  const showTip = (n: N | null, mx: number, my: number) => {
    const tip = tipRef.current
    if (!tip) return
    if (!n) { tip.hidden = true; return }
    tip.hidden = false
    tip.querySelector('strong')!.textContent = n.title
    tip.querySelector('.mc-tip-state')!.textContent = (n.formula ? 'Formula · ' : n.step ? `Step of “${n.step}” · ` : '') + (STATE_LABEL[n.state] ?? n.state)
    ;(tip.querySelector('.mc-tip-dot') as HTMLElement).style.background = css(`--st-${n.state === 'pending' ? 'ready' : n.state}`)
    tip.querySelector('.mc-tip-where')!.textContent = [n.c.title, ...n.also.map(c => c.title)].join(' · ') + (n.chapterTitle ? ` — ${n.chapterTitle}` : '')
    tip.style.left = Math.min(size.W - tip.offsetWidth - 8, mx + 14) + 'px'
    tip.style.top = Math.max(8, Math.min(size.H - tip.offsetHeight - 8, my + 14)) + 'px'
  }

  useEffect(() => {
    const el = cv.current
    if (!el || compact) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const [mx, my] = local(e), v = t.current
      const k = Math.min(6, Math.max(0.3, v.k * Math.exp(-e.deltaY * 0.0015)))
      t.current = { k, x: mx - ((mx - v.x) / v.k) * k, y: my - ((my - v.y) / v.k) * k }
      drawRef.current()
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  })

  const zoomBy = (f: number) => {
    const v = t.current, mx = size.W / 2, my = size.H / 2, k = Math.min(6, Math.max(0.3, v.k * f))
    t.current = { k, x: mx - ((mx - v.x) / v.k) * k, y: my - ((my - v.y) / v.k) * k }
    drawRef.current()
  }

  return (
    <div className="mc">
      <div className="mc-stage" ref={box}>
      <canvas ref={cv} className="mc-canvas" style={{ width: size.W, height: size.H }} aria-label="Knowledge map"
        onPointerDown={e => {
          touches.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
          e.currentTarget.setPointerCapture(e.pointerId)
          if (touches.current.size === 2) { pinch.current = { d: spread(), ...t.current }; drag.current = null; return }
          drag.current = { x: e.clientX, y: e.clientY, tx: t.current.x, ty: t.current.y, moved: false }
        }}
        onPointerMove={e => {
          if (touches.current.has(e.pointerId)) touches.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
          if (pinch.current && touches.current.size === 2 && !compact) {  // two fingers: zoom around their midpoint
            const p = pinch.current, k = Math.min(6, Math.max(0.3, p.k * spread() / Math.max(1, p.d)))
            const pts = [...touches.current.values()], r = cv.current!.getBoundingClientRect()
            const mx = (pts[0].x + pts[1].x) / 2 - r.left, my = (pts[0].y + pts[1].y) / 2 - r.top
            t.current = { k, x: mx - ((mx - p.x) / p.k) * k, y: my - ((my - p.y) / p.k) * k }
            showTip(null, 0, 0); drawRef.current(); return
          }
          const [mx, my] = local(e), d = drag.current
          if (d) {
            const dx = e.clientX - d.x, dy = e.clientY - d.y
            if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true
            if (d.moved) {
              t.current = { ...t.current, x: d.tx + dx, y: d.ty + dy }
              showTip(null, 0, 0); drawRef.current(); return
            }
          }
          const n = pick(mx, my)
          if (n !== hover.current) { hover.current = n; drawRef.current() }
          showTip(n, mx, my)
        }}
        onPointerUp={e => {
          touches.current.delete(e.pointerId)
          if (pinch.current) { if (touches.current.size < 2) pinch.current = null; drag.current = null; drawRef.current(); return }
          const d = drag.current; drag.current = null
          if (d && !d.moved) { const [mx, my] = local(e); const n = pick(mx, my); onSelect(n ? (n.id === selected ? null : n.id) : null) }
          drawRef.current()
        }}
        onPointerCancel={e => { touches.current.delete(e.pointerId); pinch.current = null; drag.current = null }}
        onPointerLeave={() => { hover.current = null; showTip(null, 0, 0); drawRef.current() }} />
      </div>
      <div className="mc-tip" ref={tipRef} hidden>
        <strong />
        <span className="mc-tip-row"><i className="mc-tip-dot" /><span className="mc-tip-state" /></span>
        <span className="mc-tip-where" />
      </div>
      {view === 'territory' && !compact && <AreaLegend areas={model.cl} fields={fields ?? []} />}
      {!compact && <div className="km-zoom mc-zoom">
        <button className="btn btn-small" onClick={() => zoomBy(1.25)} aria-label="Zoom in">+</button>
        <button className="btn btn-small" onClick={() => zoomBy(0.8)} aria-label="Zoom out">−</button>
        <button className="btn btn-small" onClick={() => { t.current = { x: 0, y: 0, k: 1 }; drawRef.current() }}>Fit</button>
      </div>}
    </div>
  )
}

const KNOWN = ['mastered', 'learned', 'rusty']
const LEGEND_KEY = 'dsc.mapLegendOpen'

/** The countries of the Territories view: each book or goal with its color and how many of its ideas you know. It can be
 *  collapsed; the choice is kept in this browser. */
function AreaLegend({ areas, fields }: { areas: C[]; fields: { id: string; title: string }[] }) {
  const [open, setOpen] = useState(() => { try { return localStorage.getItem(LEGEND_KEY) !== '0' } catch { return true } })
  const toggle = () => {
    const next = !open
    setOpen(next)
    try { localStorage.setItem(LEGEND_KEY, next ? '1' : '0') } catch { /* no storage: the choice is not kept */ }
  }
  const shown = areas.filter(c => c.nodes.length > 0)
  if (!shown.length) return null
  return (
    <div className={`mc-legend${open ? '' : ' closed'}`}>
      <button className="mc-legend-head small" onClick={toggle} aria-expanded={open}>
        <span>Countries ({shown.length})</span><span aria-hidden>{open ? '▾' : '▸'}</span>
      </button>
      {open && <ul className="mc-legend-list small">
        {shown.map(c => (
          <li key={c.id} title={c.title} className={c.kind === 'formulas' ? 'mc-legend-formulas' : undefined}>
            <span className="mc-legend-row">
              <i className="mc-legend-swatch" style={{ background: c.color }} />
              <span className="mc-legend-name">{c.title}</span>
              <span className="muted mc-legend-count">{c.nodes.filter(n => KNOWN.includes(n.state)).length}/{c.nodes.length}</span>
            </span>
            {c.kind === 'formulas' && <Provinces nodes={c.nodes} fields={fields} />}
          </li>
        ))}
      </ul>}
    </div>
  )
}

/** The provinces of the Formulas country in the legend: each field with how many formulas are in it (a formula in two
 *  fields counts in both; "shared" says how many of them are also in another field), then Essential and Not sorted. */
function Provinces({ nodes, fields }: { nodes: N[]; fields: { id: string; title: string }[] }) {
  const title = new Map(fields.map(f => [f.id, f.title]))
  const rows = FIELD_ORDER.map(f => {
    const all = nodes.filter(n => n.fields.length < 4 && n.fields.includes(f))
    return { id: f, title: title.get(f) ?? f, color: FIELD_COLORS[f], n: all.length, shared: all.filter(n => n.fields.length > 1).length }
  }).filter(r => r.n)
  const essential = nodes.filter(n => n.fields.length >= 4).length, unsorted = nodes.filter(n => !n.fields.length).length
  return (
    <ul className="mc-legend-sub">
      {rows.map(r => (
        <li key={r.id}><i className="mc-legend-swatch" style={{ background: r.color }} /><span className="mc-legend-name">{r.title}</span>
          <span className="muted mc-legend-count">{r.n}{r.shared ? ` · ${r.shared} shared` : ''}</span></li>
      ))}
      {essential > 0 && <li><i className="mc-legend-swatch" style={{ background: ESSENTIAL_COLOR }} /><span className="mc-legend-name">Essential (4+ fields)</span>
        <span className="muted mc-legend-count">{essential}</span></li>}
      {unsorted > 0 && <li><i className="mc-legend-swatch" style={{ background: UNSORTED_COLOR }} /><span className="mc-legend-name">Not sorted yet</span>
        <span className="muted mc-legend-count">{unsorted}</span></li>}
    </ul>
  )
}
