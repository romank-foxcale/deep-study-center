import katex from 'katex'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { evaluate, parse } from './viz/expr'
import type { FlowNode, FlowSpec } from '../types'

// The formula flow of a formula page (SPEC §52; the approved mock "A"). Inputs at the top, formula boxes below, an
// arrow from each box to the boxes computed from it, in the color of the value it carries. Drag a dotted value: every
// formula that uses it shows numbers in place of letters while you drag. Point at a box: only what it comes from and
// what it feeds stay bright. Click a box: what it is, its value now, what it is built from and used by, and its
// "what if" forms (change one part, see every box below it: the real value and yours).

const PALETTE = ['#6fa8ff', '#c792ea', '#e8a35a', '#5fd0b0', '#f07fa8', '#d6c36a', '#ff8a65', '#9ad06a', '#7fd3ff', '#e6a1ff', '#ffb86b', '#8fdcaa']
type Val = number | number[]

function fmt(x: Val): string {
  if (Array.isArray(x)) return '(' + x.map(fmt).join(',\\,') + ')'
  if (!Number.isFinite(x)) return '\\infty'
  if (x !== 0 && Math.abs(x) < 1e-3) { const e = Math.floor(Math.log10(Math.abs(x))); return `${(x / 10 ** e).toFixed(1)}\\!\\cdot\\!10^{${e}}` }
  if (Math.abs(x) >= 1000 || (Number.isInteger(x) && x !== 0)) return x.toFixed(0)
  if (Math.abs(x) >= 10) return x.toFixed(1)
  return String(+x.toPrecision(4))
}
const plain = (x: Val) => fmt(x).replace(/\\!\\cdot\\!10\^\{(-?\d+)\}/, ' × 10^$1').replace(/\\,/g, ' ').replace('\\infty', '∞')
const tex = (t: string) => katex.renderToString(t, { throwOnError: false, trust: true, strict: 'ignore' })
const same = (a: Val | undefined, b: Val | undefined) => JSON.stringify(a) === JSON.stringify(b)

type Parsed = ReturnType<typeof parse>
function compile(e: string | string[]): Parsed | Parsed[] | null {
  try { return Array.isArray(e) ? e.map(parse) : parse(e) } catch { return null }
}

/** Every value of the flow at these inputs; `swap` puts another expr in some boxes (a "what if"). */
function compute(spec: FlowSpec, inputs: Record<string, number>, swap: Record<string, Parsed | Parsed[] | null>, compiled: Map<string, Parsed | Parsed[] | null>) {
  const env: Record<string, number> = { ...inputs }
  const out: Record<string, Val> = { ...inputs }
  for (const n of spec.nodes) {
    if (n.input) continue
    const p = n.id in swap ? swap[n.id] : compiled.get(n.id)
    const ev = (q: Parsed) => { try { return evaluate(q, env) } catch { return NaN } }
    const v: Val = !p ? NaN : Array.isArray(p) ? p.map(ev) : ev(p)
    if (Array.isArray(v)) v.forEach((x, k) => { env[`${n.id}_${k + 1}`] = x })
    else env[n.id] = v
    out[n.id] = v
  }
  return out
}

/** The names a box's formula really uses (its TeX), to show numbers only where the dragged value goes. */
const refsOf = (t: string) => [...t.matchAll(/\{([a-z][a-z0-9]{0,11})\}/g)].map(m => m[1])

export default function FormulaFlow({ spec }: { spec: FlowSpec }) {
  const box = useRef<HTMLDivElement>(null)
  const graph = useRef<HTMLDivElement>(null)
  const els = useRef<Record<string, HTMLDivElement | null>>({})
  const [width, setWidth] = useState(720)
  const [values, setValues] = useState<Record<string, number>>(() => Object.fromEntries(spec.inputs.map(i => [i.id, i.value])))
  const [live, setLive] = useState<string | null>(null)
  const [always, setAlways] = useState(false)
  const [hot, setHot] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [pick, setPick] = useState<Record<string, number>>({})  // box -> chosen what-if
  const dragged = useRef(false)
  const [arrows, setArrows] = useState<{ d: string; head: string; color: string; a: string; b: string }[]>([])
  useEffect(() => { setValues(Object.fromEntries(spec.inputs.map(i => [i.id, i.value]))); setPick({}); setOpen(null) }, [spec])

  const byId = useMemo(() => new Map(spec.nodes.map(n => [n.id, n])), [spec])
  const inputs = useMemo(() => new Map(spec.inputs.map(i => [i.id, i])), [spec])
  const holder = useMemo(() => { const h: Record<string, string> = {}; spec.nodes.forEach(n => n.input?.forEach(i => { h[i] = n.id })); return h }, [spec])
  const color = useMemo(() => Object.fromEntries(spec.nodes.map((n, i) => [n.id, PALETTE[i % PALETTE.length]])), [spec])
  const compiled = useMemo(() => new Map(spec.nodes.filter(n => !n.input).map(n => [n.id, compile(n.expr!)])), [spec])
  const swap = useMemo(() => Object.fromEntries(Object.entries(pick).map(([id, k]) => [id, compile(byId.get(id)!.whatif![k].expr)])), [pick, byId])
  const real = useMemo(() => compute(spec, values, {}, compiled), [spec, values, compiled])
  const yours = useMemo(() => (Object.keys(pick).length ? compute(spec, values, swap, compiled) : real), [spec, values, swap, compiled, pick, real])
  const changed = Object.keys(pick).length > 0

  // rows: input boxes on top, each box one row below the lowest box it uses; in a row, boxes by their parents' places
  const layout = useMemo(() => {
    const depth: Record<string, number> = {}
    const d = (n: FlowNode): number => depth[n.id] ??= n.input ? 0 : 1 + Math.max(0, ...(n.uses ?? []).map(u => byId.get(u) ? d(byId.get(u)!) : 0))
    spec.nodes.forEach(d)
    const rows: FlowNode[][] = []
    spec.nodes.forEach(n => { (rows[depth[n.id]] ??= []).push(n) })
    const x: Record<string, number> = {}
    rows.forEach((row, r) => {
      if (r > 0) row.sort((a, b) => avg(a) - avg(b))
      row.forEach((n, i) => { x[n.id] = (i + 0.5) / row.length })
    })
    function avg(n: FlowNode) { const u = (n.uses ?? []).filter(id => id in x); return u.length ? u.reduce((s, id) => s + x[id], 0) / u.length : 0.5 }
    return { depth, x, rows: rows.length }
  }, [spec, byId])
  const wide = Math.max(...Array.from({ length: layout.rows }, (_, r) => spec.nodes.filter(n => layout.depth[n.id] === r).length))
  const W = Math.max(width, wide * 230)
  const ROW = 128

  useEffect(() => {
    const el = box.current
    if (!el) return
    const ro = new ResizeObserver(() => setWidth(el.clientWidth))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // which names show numbers: while dragging, the dragged value and every box that really uses it
  const needs = useMemo(() => {
    if (!live) return new Set<string>()
    const out = new Set([live])
    let grew = true
    while (grew) { grew = false; for (const n of spec.nodes) if (!n.input && !out.has(n.id) && refsOf(n.tex).some(r => r !== n.id && out.has(r))) { out.add(n.id); grew = true } }
    return out
  }, [live, spec])
  const symOf = (id: string) => inputs.get(id)?.sym ?? byId.get(id)?.sym ?? id
  const texOf = (n: FlowNode) => {
    const t = pick[n.id] !== undefined ? n.whatif![pick[n.id]].tex : n.tex
    return t.replace(/\{([a-z][a-z0-9]{0,11})\}/g, (m, id: string) => {
      if (!inputs.has(id) && !byId.has(id)) return m
      const shown = always || needs.has(id)
      const v = inputs.has(id) ? values[id] : yours[id]
      const body = shown && v !== undefined && !byId.get(id)?.input ? `\\htmlClass{ff-num}{${fmt(v)}}` : symOf(id)
      const inp = inputs.get(id)
      return inp && !inp.fixed ? `\\htmlClass{ff-scrub ff-s-${id}}{${body}}` : `{${body}}`
    })
  }

  // arrows, measured from the boxes after they are drawn
  useLayoutEffect(() => {
    const g = graph.current
    if (!g) return
    const gb = g.getBoundingClientRect()
    const out: typeof arrows = []
    for (const n of spec.nodes) (n.uses ?? []).forEach((u, k, all) => {
      const a = els.current[u]?.getBoundingClientRect(), b = els.current[n.id]?.getBoundingClientRect()
      if (!a || !b) return
      const spread = Math.min(b.width - 24, 26 * (all.length - 1))
      const x1 = a.left + a.width / 2 - gb.left, y1 = a.bottom - gb.top
      const x2 = b.left + b.width / 2 - gb.left + (all.length > 1 ? -spread / 2 + (spread * k) / (all.length - 1) : 0), y2 = b.top - gb.top
      const my = y2 - 14 - k * 7, r = Math.min(8, Math.abs(x2 - x1) / 2), sx = Math.sign(x2 - x1)
      const d = Math.abs(x2 - x1) < 1 ? `M${x1},${y1} V${y2 - 6}`
        : `M${x1},${y1} V${my - r} Q${x1},${my} ${x1 + sx * r},${my} H${x2 - sx * r} Q${x2},${my} ${x2},${my + r} V${y2 - 6}`
      out.push({ d, head: `M${x2 - 4.5},${y2 - 8} L${x2},${y2 - 1} L${x2 + 4.5},${y2 - 8} Z`, color: color[u], a: u, b: n.id })
    })
    setArrows(out)
  }, [spec, W, values, pick, always, live, color])

  // drag a dotted value (in a formula or a pill): the value follows the pointer
  const startDrag = (id: string, x0: number) => {
    const inp = inputs.get(id)
    if (!inp || inp.fixed) return
    const v0 = values[id]
    dragged.current = true
    setLive(id)
    document.body.style.cursor = 'ew-resize'
    const move = (e: PointerEvent) => {
      const v = Math.min(inp.max, Math.max(inp.min, v0 + Math.round((e.clientX - x0) / 6) * inp.step))
      setValues(s => ({ ...s, [id]: +v.toFixed(6) }))
    }
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); setLive(null); document.body.style.cursor = ''; setTimeout(() => { dragged.current = false }, 0) }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up)
  }
  const onPointerDown = (e: React.PointerEvent) => {
    const t = (e.target as Element).closest('[class*="ff-s-"]')
    const id = t && [...t.classList].find(c => c.startsWith('ff-s-'))?.slice(5)
    if (id) { e.preventDefault(); e.stopPropagation(); startDrag(id, e.clientX) }
  }

  const ups = (id: string) => { const out = new Set([id]); let grew = true; while (grew) { grew = false; for (const n of spec.nodes) if (out.has(n.id)) for (const u of n.uses ?? []) if (!out.has(u)) { out.add(u); grew = true } } return out }
  const downs = (id: string) => { const out = new Set([id]); let grew = true; while (grew) { grew = false; for (const n of spec.nodes) if (!out.has(n.id) && (n.uses ?? []).some(u => out.has(u))) { out.add(n.id); grew = true } } return out }
  const keep = hot ? new Set([...ups(hot), ...downs(hot)]) : null
  const sinks = spec.nodes.filter(n => !n.input && !spec.nodes.some(m => m.uses?.includes(n.id)))
  const card = open ? byId.get(open) : undefined

  return (
    <div className="ff" ref={box}>
      <div className="ff-bar small muted">
        <span>Drag a dotted value. Point at a box to see where it comes from; click it to read what it is.</span>
        <label><input type="checkbox" checked={always} onChange={e => setAlways(e.target.checked)} /> Numbers in every formula</label>
        {changed && <button className="btn btn-small" onClick={() => setPick({})}>Back to the real formula</button>}
      </div>
      <div className="ff-scroll">
        <div className="ff-graph" ref={graph} style={{ width: W, height: layout.rows * ROW }} onPointerDown={onPointerDown}>
          <svg className="ff-arrows">
            {arrows.map((a, i) => <g key={i} className={keep && !(keep.has(a.a) && keep.has(a.b)) ? 'ff-dim' : undefined}>
              <path d={a.d} stroke={a.color} className="ff-edge" /><path d={a.head} fill={a.color} /></g>)}
          </svg>
          {spec.nodes.map(n => {
            const v = yours[n.id], r = real[n.id]
            const differs = changed && !n.input && !same(v, r)
            return (
              <div key={n.id} ref={el => { els.current[n.id] = el }}
                className={['ff-node', n.input && 'ff-input', keep && !keep.has(n.id) && 'ff-dim', open === n.id && 'ff-open', pick[n.id] !== undefined && 'ff-swapped'].filter(Boolean).join(' ')}
                style={{ top: layout.depth[n.id] * ROW, left: Math.min(W - 110, Math.max(110, layout.x[n.id] * W)) }}
                onPointerEnter={() => setHot(n.id)} onPointerLeave={() => setHot(null)}
                onClick={() => { if (!dragged.current) setOpen(open === n.id ? null : n.id) }}>
                <div className="ff-tex" style={{ color: color[n.id] }} dangerouslySetInnerHTML={{ __html: tex(texOf(n)) }} />
                <div className="ff-label">{n.label}</div>
                {!n.input && (differs
                  ? <div className="ff-val ff-two"><span className="muted">real {plain(r)}</span><span className="ff-yours">yours {plain(v)}</span></div>
                  : <div className="ff-val">= {plain(v)}</div>)}
              </div>
            )
          })}
        </div>
      </div>
      <div className="ff-pills" onPointerDown={onPointerDown}>
        {spec.inputs.map(i => (
          <span key={i.id} className="ff-pill" style={{ color: color[holder[i.id]] }}>
            <span dangerouslySetInnerHTML={{ __html: tex(i.sym) }} /> {i.label}{' '}
            <b className={i.fixed ? '' : `ff-scrub ff-s-${i.id}`}>{plain(values[i.id])}</b>
          </span>))}
      </div>
      <div className="ff-pills">
        {sinks.map(n => <span key={n.id} className="ff-pill ff-out" style={{ color: color[n.id] }}>
          <span dangerouslySetInnerHTML={{ __html: tex(n.sym ?? n.id) }} /> {n.label} <b>{plain(yours[n.id])}</b></span>)}
      </div>
      {card && (
        <div className="ff-card card">
          <div className="row row-between"><span className="eyebrow">{card.input ? 'Inputs' : 'Formula'} · {card.label}</span>
            <button className="link small" onClick={() => setOpen(null)}>Close</button></div>
          <div className="ff-card-tex" style={{ color: color[card.id] }} dangerouslySetInnerHTML={{ __html: tex(texOf({ ...card })) }} />
          <p className="small" dangerouslySetInnerHTML={{ __html: rich(card.say) }} />
          {!card.input && <p className="small"><span className="eyebrow">Now</span> <span dangerouslySetInnerHTML={{ __html: tex(`${card.sym ?? card.id} = ${fmt(yours[card.id])}`) }} /></p>}
          {card.input && <p className="small">{card.input.map(i => <span key={i} className="ff-chip-static">
            <span dangerouslySetInnerHTML={{ __html: tex(`${symOf(i)} = ${fmt(values[i])}`) }} /> {inputs.get(i)?.label}</span>)}</p>}
          {(card.uses ?? []).length > 0 && <><div className="eyebrow">Built from</div>
            <div className="ff-chips">{card.uses!.map(u => <button key={u} style={{ color: color[u] }} onClick={() => setOpen(u)}>{byId.get(u)?.label}</button>)}</div></>}
          {spec.nodes.some(m => m.uses?.includes(card.id)) && <><div className="eyebrow">Used by</div>
            <div className="ff-chips">{spec.nodes.filter(m => m.uses?.includes(card.id)).map(m => <button key={m.id} style={{ color: color[m.id] }} onClick={() => setOpen(m.id)}>{m.label}</button>)}</div></>}
          {(card.whatif ?? []).length > 0 && <><div className="eyebrow">What if this part were different?</div>
            <button className={`ff-whatif${pick[card.id] === undefined ? ' on' : ''}`} onClick={() => setPick(p => { const q = { ...p }; delete q[card.id]; return q })}>The real formula</button>
            {card.whatif!.map((w, k) => (
              <button key={k} className={`ff-whatif${pick[card.id] === k ? ' on' : ''}`} onClick={() => setPick(p => ({ ...p, [card.id]: k }))}>
                <span dangerouslySetInnerHTML={{ __html: tex(w.tex.replace(/\{([a-z][a-z0-9]{0,11})\}/g, (_, id: string) => `{${symOf(id)}}`)) }} />
              </button>))}
            {pick[card.id] !== undefined && <p className={`small ff-why${card.whatif![pick[card.id]].ok ? ' ff-ok' : ''}`}
              dangerouslySetInnerHTML={{ __html: rich(card.whatif![pick[card.id]].why) }} />}</>}
        </div>
      )}
    </div>
  )
}

/** Text with $TeX$ parts, as HTML. */
function rich(text: string): string {
  return (text || '').split(/(\$[^$]+\$)/).map(part => part.length > 2 && part.startsWith('$') && part.endsWith('$')
    ? tex(part.slice(1, -1)) : part.replace(/&/g, '&amp;').replace(/</g, '&lt;')).join('')
}
