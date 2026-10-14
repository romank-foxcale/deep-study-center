// Built-in interactive widgets for lessons. Agents choose a widget and its numbers (validated by
// the backend); everything that runs here is our own code.

import { useMemo, useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from 'react'
import type { VizSpec } from '../../types'
import { evaluate, parse } from './expr'

const SIZE = 320
const R = 5 // world units from the centre to the edge

const toPx = (x: number, y: number, r = R): [number, number] => [SIZE / 2 + (x / r) * (SIZE / 2), SIZE / 2 - (y / r) * (SIZE / 2)]
const round = (v: number) => Math.round(v * 2) / 2
const fmt = (v: number) => (Math.round(v * 100) / 100).toString()

function Grid({ r = R }: { r?: number }) {
  const lines: ReactNode[] = []
  for (let i = -r; i <= r; i++) {
    const [x] = toPx(i, 0, r), [, y] = toPx(0, i, r)
    lines.push(<line key={`v${i}`} x1={x} y1={0} x2={x} y2={SIZE} className={i === 0 ? 'viz-axis' : 'viz-grid'} />)
    lines.push(<line key={`h${i}`} x1={0} y1={y} x2={SIZE} y2={y} className={i === 0 ? 'viz-axis' : 'viz-grid'} />)
  }
  return <g>{lines}</g>
}

function Arrow({ from = [0, 0], to, cls, label, dashed }: { from?: number[]; to: number[]; cls: string; label?: string; dashed?: boolean }) {
  const [x1, y1] = toPx(from[0], from[1]), [x2, y2] = toPx(to[0], to[1])
  const ang = Math.atan2(y2 - y1, x2 - x1), h = 9
  const head = `${x2},${y2} ${x2 - h * Math.cos(ang - 0.4)},${y2 - h * Math.sin(ang - 0.4)} ${x2 - h * Math.cos(ang + 0.4)},${y2 - h * Math.sin(ang + 0.4)}`
  const len = Math.hypot(x2 - x1, y2 - y1)
  return (
    <g className={cls}>
      {len > 2 && <line x1={x1} y1={y1} x2={x2} y2={y2} strokeDasharray={dashed ? '5 4' : undefined} />}
      {len > 2 && <polygon points={head} />}
      {label && <text x={Math.min(x2 + 8, SIZE - 6)} y={Math.max(y2 - 8, 14)} textAnchor={x2 + 8 > SIZE - 50 ? 'end' : 'start'}>{label}</text>}
    </g>
  )
}

/** A draggable point handle (mouse, touch, or arrow keys when focused). */
function useDrag() {
  const svg = useRef<SVGSVGElement>(null)
  const dragging = useRef<number | null>(null)
  const toWorld = (e: PointerEvent) => {
    const pt = svg.current!.createSVGPoint()
    pt.x = e.clientX; pt.y = e.clientY
    const p = pt.matrixTransform(svg.current!.getScreenCTM()!.inverse())
    return [round(((p.x - SIZE / 2) / (SIZE / 2)) * R), round(((SIZE / 2 - p.y) / (SIZE / 2)) * R)]
  }
  return {
    svg,
    start: (i: number) => (e: PointerEvent) => { dragging.current = i; (e.target as Element).setPointerCapture(e.pointerId) },
    move: (cb: (i: number, x: number, y: number) => void) => (e: PointerEvent) => {
      if (dragging.current === null) return
      const [x, y] = toWorld(e)
      cb(dragging.current, Math.max(-R, Math.min(R, x)), Math.max(-R, Math.min(R, y)))
    },
    end: () => { dragging.current = null },
  }
}

function keyNudge(e: KeyboardEvent, x: number, y: number, set: (x: number, y: number) => void) {
  const d = { ArrowLeft: [-0.5, 0], ArrowRight: [0.5, 0], ArrowUp: [0, 0.5], ArrowDown: [0, -0.5] }[e.key]
  if (!d) return
  e.preventDefault()
  set(Math.max(-R, Math.min(R, x + d[0])), Math.max(-R, Math.min(R, y + d[1])))
}

function Vectors2D({ spec }: { spec: Extract<VizSpec, { type: 'vectors2d' }> }) {
  const [vs, setVs] = useState(spec.vectors.map(v => ({ ...v })))
  const set = (i: number, x: number, y: number) => setVs(cur => cur.map((v, j) => (j === i ? { ...v, x, y } : v)))
  const drag = useDrag()
  const sum = vs.reduce((a, v) => [a[0] + v.x, a[1] + v.y], [0, 0])
  return (
    <>
      <svg ref={drag.svg} viewBox={`0 0 ${SIZE} ${SIZE}`} className="viz-svg" onPointerMove={drag.move(set)} onPointerUp={drag.end}
        role="img" aria-label={spec.caption}>
        <Grid />
        {spec.showSum && vs.length > 1 && vs.slice(1).map((v, i) => {
          const from = vs.slice(0, i + 1).reduce((a, w) => [a[0] + w.x, a[1] + w.y], [0, 0])
          return <Arrow key={`t${i}`} from={from} to={[from[0] + v.x, from[1] + v.y]} cls={`viz-v${(i + 1) % 4} viz-ghost`} dashed />
        })}
        {spec.showSum && vs.length > 1 && <Arrow to={sum} cls="viz-sum" label={vs.map(v => v.label).join(' + ')} dashed />}
        {vs.map((v, i) => <Arrow key={i} to={[v.x, v.y]} cls={`viz-v${i % 4}`} label={v.label} />)}
        {vs.map((v, i) => {
          const [cx, cy] = toPx(v.x, v.y)
          return <circle key={`h${i}`} cx={cx} cy={cy} r={13} className="viz-handle" tabIndex={0} role="slider"
            aria-label={`${v.label} tip, ${fmt(v.x)}, ${fmt(v.y)}`} aria-valuetext={`(${fmt(v.x)}, ${fmt(v.y)})`}
            onPointerDown={drag.start(i)} onKeyDown={e => keyNudge(e, v.x, v.y, (x, y) => set(i, x, y))} />
        })}
      </svg>
      <div className="viz-readout">
        {vs.map((v, i) => <span key={i}><b className={`viz-c${i % 4}`}>{v.label}</b> = ({fmt(v.x)}, {fmt(v.y)})</span>)}
        {spec.showSum && vs.length > 1 && <span><b>sum</b> = ({fmt(sum[0])}, {fmt(sum[1])}) · |sum| = {fmt(Math.hypot(sum[0], sum[1]))}</span>}
      </div>
    </>
  )
}

function Slider({ label, value, min, max, step = 0.1, onChange }: { label: string; value: number; min: number; max: number; step?: number; onChange: (v: number) => void }) {
  return (
    <label className="viz-slider">
      <span>{label} = {fmt(value)}</span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={e => onChange(Number(e.target.value))} />
    </label>
  )
}

function LinComb2D({ spec }: { spec: Extract<VizSpec, { type: 'lincomb2d' }> }) {
  const [a, setA] = useState(1), [b, setB] = useState(1)
  const { u, v, target } = spec
  const au = [a * u[0], a * u[1]], res = [au[0] + b * v[0], au[1] + b * v[1]]
  const hit = target && Math.hypot(res[0] - target[0], res[1] - target[1]) < 0.15
  const parallel = Math.abs(u[0] * v[1] - u[1] * v[0]) < 1e-9
  return (
    <>
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="viz-svg" role="img" aria-label={spec.caption}>
        <Grid />
        {parallel && (() => { const [x1, y1] = toPx(-u[0] * 20, -u[1] * 20), [x2, y2] = toPx(u[0] * 20, u[1] * 20); return <line x1={x1} y1={y1} x2={x2} y2={y2} className="viz-span" /> })()}
        {target && (() => { const [cx, cy] = toPx(target[0], target[1]); return <circle cx={cx} cy={cy} r={8} className={hit ? 'viz-target hit' : 'viz-target'} /> })()}
        <Arrow to={au} cls="viz-v0" label="a·u" />
        <Arrow from={au} to={res} cls="viz-v1" label="b·v" />
        <Arrow to={res} cls="viz-sum" dashed />
      </svg>
      <div className="viz-controls">
        <Slider label="a" value={a} min={-4} max={4} onChange={setA} />
        <Slider label="b" value={b} min={-4} max={4} onChange={setB} />
      </div>
      <div className="viz-readout">
        <span>a·u + b·v = ({fmt(res[0])}, {fmt(res[1])})</span>
        {target && <span>{hit ? 'On target!' : `target (${fmt(target[0])}, ${fmt(target[1])})`}</span>}
        {parallel && <span>u and v are parallel: every combination stays on one line.</span>}
      </div>
    </>
  )
}

function Matrix2D({ spec }: { spec: Extract<VizSpec, { type: 'matrix2d' }> }) {
  const [m, setM] = useState(spec.matrix.map(r => [...r]))
  const T = (x: number, y: number) => [m[0][0] * x + m[0][1] * y, m[1][0] * x + m[1][1] * y]
  const det = m[0][0] * m[1][1] - m[0][1] * m[1][0]
  const lines: ReactNode[] = []
  for (let i = -R; i <= R; i++) {
    const segs = [[T(i, -R), T(i, R)], [T(-R, i), T(R, i)]]
    segs.forEach(([p, q], k) => {
      const [x1, y1] = toPx(p[0], p[1]), [x2, y2] = toPx(q[0], q[1])
      lines.push(<line key={`${i}-${k}`} x1={x1} y1={y1} x2={x2} y2={y2} className="viz-tgrid" />)
    })
  }
  const sq = [T(0, 0), T(1, 0), T(1, 1), T(0, 1)].map(p => toPx(p[0], p[1]).join(',')).join(' ')
  return (
    <>
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="viz-svg" role="img" aria-label={spec.caption}>
        <Grid />
        <g>{lines}</g>
        <polygon points={sq} className="viz-square" />
        <Arrow to={T(1, 0)} cls="viz-v0" label="A·e₁" />
        <Arrow to={T(0, 1)} cls="viz-v1" label="A·e₂" />
      </svg>
      <div className="viz-controls viz-matrix">
        {[0, 1].map(r => [0, 1].map(c => (
          <label key={`${r}${c}`}>
            <span className="sr-only">row {r + 1} column {c + 1}</span>
            <input type="number" step={0.5} min={-5} max={5} value={m[r][c]} className="input input-small"
              onChange={e => { const v = Number(e.target.value); setM(cur => cur.map((row, i) => row.map((x, j) => (i === r && j === c ? v : x)))) }} />
          </label>
        )))}
      </div>
      <div className="viz-readout"><span>det A = {fmt(det)} (area of the unit square after A{det < 0 ? ', flipped' : ''})</span></div>
    </>
  )
}

function Plot({ spec }: { spec: Extract<VizSpec, { type: 'plot' }> }) {
  const [params, setParams] = useState(Object.fromEntries(spec.params.map(p => [p.name, p.value])))
  const tree = useMemo(() => { try { return parse(spec.expr) } catch { return null } }, [spec.expr])
  const W = SIZE * 1.6, H = SIZE * 0.8
  const pts: [number, number][] = []
  if (tree) {
    for (let i = 0; i <= 240; i++) {
      const x = spec.xmin + ((spec.xmax - spec.xmin) * i) / 240
      let y = NaN
      try { y = evaluate(tree, { ...params, x }) } catch { /* outside domain */ }
      if (Number.isFinite(y)) pts.push([x, y])
    }
  }
  const ys = pts.map(p => p[1])
  const ymin = Math.min(-1, ...ys), ymax = Math.max(1, ...ys)
  const px = (x: number) => ((x - spec.xmin) / (spec.xmax - spec.xmin)) * W
  const py = (y: number) => H - ((y - ymin) / (ymax - ymin || 1)) * H
  const path = pts.map((p, i) => `${i ? 'L' : 'M'}${px(p[0]).toFixed(1)},${py(p[1]).toFixed(1)}`).join('')
  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} className="viz-svg viz-plot" role="img" aria-label={spec.caption}>
        {spec.xmin < 0 && spec.xmax > 0 && <line x1={px(0)} y1={0} x2={px(0)} y2={H} className="viz-axis" />}
        {ymin < 0 && ymax > 0 && <line x1={0} y1={py(0)} x2={W} y2={py(0)} className="viz-axis" />}
        <path d={path} className="viz-curve" />
      </svg>
      <div className="viz-readout"><span>y = {spec.expr}</span><span>x ∈ [{fmt(spec.xmin)}, {fmt(spec.xmax)}], y ∈ [{fmt(ymin)}, {fmt(ymax)}]</span></div>
      {spec.params.length > 0 && (
        <div className="viz-controls">
          {spec.params.map(p => <Slider key={p.name} label={p.name} value={params[p.name]} min={p.min} max={p.max}
            step={(p.max - p.min) / 100} onChange={v => setParams(cur => ({ ...cur, [p.name]: v }))} />)}
        </div>
      )}
    </>
  )
}

export default function Viz({ spec }: { spec: VizSpec }) {
  return (
    <figure className="viz">
      {spec.type === 'vectors2d' && <Vectors2D spec={spec} />}
      {spec.type === 'lincomb2d' && <LinComb2D spec={spec} />}
      {spec.type === 'matrix2d' && <Matrix2D spec={spec} />}
      {spec.type === 'plot' && <Plot spec={spec} />}
      {spec.caption && <figcaption className="muted small">{spec.caption}</figcaption>}
    </figure>
  )
}
