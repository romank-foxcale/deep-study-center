// A 3D surface z = f(x, y) (viz type "surface3d"), for example a loss over two weights. Drag to turn it, use the top
// view to see it as a map. Optimizers start from one point and walk down; each path is drawn on the surface, and Play
// moves them step by step, so you see why momentum, RMSProp and Adam behave differently from plain gradient descent.
// Canvas only: our own projection, no 3D library.

import { useEffect, useMemo, useRef, useState, type PointerEvent } from 'react'
import { evaluate, parse } from './expr'

export type Optimizer = 'sgd' | 'momentum' | 'rmsprop' | 'adam'
export interface SurfaceSpec {
  type: 'surface3d'; caption: string; expr: string; xmin: number; xmax: number; ymin: number; ymax: number
  start: [number, number]; optimizers: Optimizer[]; lr: number; steps: number
}

const NAMES: Record<Optimizer, string> = { sgd: 'Gradient descent', momentum: 'Momentum', rmsprop: 'RMSProp', adam: 'Adam' }
const COLORS: Record<Optimizer, string> = { sgd: '#ff5c7a', momentum: '#ffb35c', rmsprop: '#7cc4ff', adam: '#b48cff' }
const ALL: Optimizer[] = ['sgd', 'momentum', 'rmsprop', 'adam']
const N = 40 // grid cells per side
const W = 640
const H = 420

type Pt = [number, number, number]

/** The path of one optimizer: (x, y, loss) for every step; it stops when the loss is not a number or it leaves far away. */
export function descend(f: (x: number, y: number) => number, kind: Optimizer, start: [number, number], lr: number, steps: number,
  box: [number, number, number, number]): Pt[] {
  const [x0, x1, y0, y1] = box
  const span = Math.max(x1 - x0, y1 - y0)
  const h = 1e-4 * span
  const grad = (x: number, y: number): [number, number] =>
    [(f(x + h, y) - f(x - h, y)) / (2 * h), (f(x, y + h) - f(x, y - h)) / (2 * h)]
  let [x, y] = start
  let vx = 0, vy = 0, sx = 0, sy = 0, mx = 0, my = 0
  const out: Pt[] = [[x, y, f(x, y)]]
  for (let t = 1; t <= steps; t++) {
    const [gx, gy] = grad(x, y)
    if (!Number.isFinite(gx) || !Number.isFinite(gy)) break
    if (kind === 'sgd') { x -= lr * gx; y -= lr * gy }
    if (kind === 'momentum') { vx = 0.9 * vx + gx; vy = 0.9 * vy + gy; x -= lr * vx; y -= lr * vy }
    if (kind === 'rmsprop') {
      sx = 0.9 * sx + 0.1 * gx * gx; sy = 0.9 * sy + 0.1 * gy * gy
      x -= lr * gx / (Math.sqrt(sx) + 1e-8); y -= lr * gy / (Math.sqrt(sy) + 1e-8)
    }
    if (kind === 'adam') {
      mx = 0.9 * mx + 0.1 * gx; my = 0.9 * my + 0.1 * gy
      sx = 0.999 * sx + 0.001 * gx * gx; sy = 0.999 * sy + 0.001 * gy * gy
      const c1 = 1 - 0.9 ** t, c2 = 1 - 0.999 ** t
      x -= lr * (mx / c1) / (Math.sqrt(sx / c2) + 1e-8); y -= lr * (my / c1) / (Math.sqrt(sy / c2) + 1e-8)
    }
    const z = f(x, y)
    if (!Number.isFinite(z) || x < x0 - span || x > x1 + span || y < y0 - span || y > y1 + span) break
    out.push([x, y, z])
  }
  return out
}

const fmt = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 1 ? v.toFixed(2) : v.toPrecision(2))

/** Height color: deep blue (low) through teal and green to yellow (high). */
function heat(t: number, light: number): string {
  const stops = [[30, 50, 140], [20, 140, 160], [80, 190, 110], [240, 220, 90]]
  const s = Math.max(0, Math.min(0.999, t)) * (stops.length - 1)
  const i = Math.floor(s), u = s - i
  const c = stops[i].map((v, k) => v + (stops[i + 1][k] - v) * u).map(v => Math.round(v * light))
  return `rgb(${c[0]},${c[1]},${c[2]})`
}

export default function Surface3D({ spec }: { spec: SurfaceSpec }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const [yaw, setYaw] = useState(-0.7)
  const [pitch, setPitch] = useState(0.62)
  const [lr, setLr] = useState(spec.lr)
  const [start, setStart] = useState<[number, number]>(spec.start)
  const [on, setOn] = useState<Optimizer[]>(spec.optimizers.length ? spec.optimizers : ['sgd'])
  const [t, setT] = useState(spec.steps)
  const [playing, setPlaying] = useState(false)
  const drag = useRef<{ x: number; y: number; yaw: number; pitch: number } | null>(null)

  const f = useMemo(() => {
    try {
      const tree = parse(spec.expr)
      return (x: number, y: number) => evaluate(tree, { x, y })
    } catch { return null }
  }, [spec.expr])
  const box: [number, number, number, number] = [spec.xmin, spec.xmax, spec.ymin, spec.ymax]

  // The surface on a grid, and the height range shown (a high cliff is cut, so the valley stays readable).
  const grid = useMemo(() => {
    if (!f) return null
    const zs: number[][] = []
    const all: number[] = []
    for (let i = 0; i <= N; i++) {
      zs.push([])
      for (let j = 0; j <= N; j++) {
        const z = f(spec.xmin + (spec.xmax - spec.xmin) * i / N, spec.ymin + (spec.ymax - spec.ymin) * j / N)
        zs[i].push(z)
        if (Number.isFinite(z)) all.push(z)
      }
    }
    all.sort((a, b) => a - b)
    const lo = all[0] ?? 0, hi = all[Math.floor(all.length * 0.97)] ?? 1
    return { zs, lo, hi: hi > lo ? hi : lo + 1 }
  }, [f, spec.xmin, spec.xmax, spec.ymin, spec.ymax])

  const paths = useMemo(() => (f ? on.map(k => ({ k, pts: descend(f, k, start, lr, spec.steps, box) })) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [f, on, start, lr, spec.steps, spec.xmin, spec.xmax, spec.ymin, spec.ymax])

  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => setT(v => {
      if (v >= spec.steps) { setPlaying(false); return v }
      return v + 1
    }), Math.max(16, 3500 / spec.steps))
    return () => clearInterval(id)
  }, [playing, spec.steps])

  useEffect(() => {
    const c = canvas.current
    const ctx = c?.getContext('2d')
    if (!c || !ctx || !grid) return
    const dpr = window.devicePixelRatio || 1
    c.width = W * dpr
    c.height = H * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, W, H)
    const { zs, lo, hi } = grid
    const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch)
    const norm = (x: number, y: number, z: number): [number, number, number] => [
      ((x - spec.xmin) / (spec.xmax - spec.xmin)) * 2 - 1, ((y - spec.ymin) / (spec.ymax - spec.ymin)) * 2 - 1,
      (Math.min(Math.max(z, lo), hi) - lo) / (hi - lo) * 1.1 - 0.55]
    const project = (X: number, Y: number, Z: number): [number, number, number] => {
      const x = X * cy - Y * sy, y = X * sy + Y * cy
      const depth = y * cp - Z * sp
      const up = y * sp + Z * cp
      const s = 3.2 / (3.2 + depth) * Math.min(W, H) * 0.3
      return [W / 2 + x * s, H / 2 + 28 - up * s, depth]
    }
    // the surface: quads, far ones first, shaded by height and by their slope towards the light
    const quads: { d: number; p: [number, number][]; col: string }[] = []
    for (let i = 0; i < N; i++) {
      for (let j = 0; j < N; j++) {
        const corners: [number, number][] = [[i, j], [i + 1, j], [i + 1, j + 1], [i, j + 1]]
        const raw = corners.map(([a, b]) => zs[a][b])
        if (raw.some(z => !Number.isFinite(z))) continue
        const w = corners.map(([a, b], k) => norm(spec.xmin + (spec.xmax - spec.xmin) * a / N, spec.ymin + (spec.ymax - spec.ymin) * b / N, raw[k]))
        const pr = w.map(p => project(p[0], p[1], p[2]))
        const ux = w[1][0] - w[0][0], uz = w[1][2] - w[0][2], vy = w[3][1] - w[0][1], vz = w[3][2] - w[0][2]
        const n = [-uz * vy, -ux * vz, ux * vy]
        const nl = Math.hypot(n[0], n[1], n[2]) || 1
        const light = 0.55 + 0.45 * Math.abs((n[0] * -0.4 + n[1] * -0.5 + n[2] * 0.77) / nl)
        const avg = (raw.reduce((a, b) => a + Math.min(Math.max(b, lo), hi), 0) / 4 - lo) / (hi - lo)
        quads.push({ d: pr.reduce((a, p) => a + p[2], 0) / 4, p: pr.map(p => [p[0], p[1]]), col: heat(avg, light) })
      }
    }
    quads.sort((a, b) => b.d - a.d)
    ctx.lineWidth = 0.4
    ctx.strokeStyle = 'rgba(10,14,24,0.35)'
    for (const q of quads) {
      ctx.beginPath()
      q.p.forEach(([x, y], k) => (k ? ctx.lineTo(x, y) : ctx.moveTo(x, y)))
      ctx.closePath()
      ctx.fillStyle = q.col
      ctx.fill()
      ctx.stroke()
    }
    // axes labels
    ctx.fillStyle = 'rgba(232,230,223,0.75)'
    ctx.font = '12px Inter, system-ui, sans-serif'
    const ax = project(1.15, -1, -0.55), ay = project(-1, 1.15, -0.55)
    ctx.fillText('x', ax[0], ax[1])
    ctx.fillText('y', ay[0], ay[1])
    // the paths, drawn a little above the surface so they stay visible
    for (const { k, pts } of paths) {
      const shown = pts.slice(0, t + 1)
      ctx.strokeStyle = COLORS[k]
      ctx.lineWidth = 2.4
      ctx.beginPath()
      shown.forEach(([x, y, z], n) => {
        const w = norm(x, y, z)
        const [px, py] = project(w[0], w[1], w[2] + 0.03)
        if (n) ctx.lineTo(px, py); else ctx.moveTo(px, py)
      })
      ctx.stroke()
      const last = shown[shown.length - 1]
      if (last) {
        const w = norm(last[0], last[1], last[2])
        const [px, py] = project(w[0], w[1], w[2] + 0.03)
        ctx.fillStyle = COLORS[k]
        ctx.beginPath()
        ctx.arc(px, py, 5.5, 0, Math.PI * 2)
        ctx.fill()
        ctx.strokeStyle = '#0b0e16'
        ctx.lineWidth = 1.5
        ctx.stroke()
      }
    }
  }, [grid, paths, yaw, pitch, t, spec.xmin, spec.xmax, spec.ymin, spec.ymax])

  if (!f || !grid) return <p className="muted small">This surface could not be drawn.</p>

  const down = (e: PointerEvent<HTMLCanvasElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId)
    drag.current = { x: e.clientX, y: e.clientY, yaw, pitch }
  }
  const move = (e: PointerEvent<HTMLCanvasElement>) => {
    const d = drag.current
    if (!d) return
    setYaw(d.yaw + (e.clientX - d.x) * 0.01)
    setPitch(Math.max(0.1, Math.min(Math.PI / 2, d.pitch + (e.clientY - d.y) * 0.01)))
  }
  const toggle = (k: Optimizer) => setOn(cur => (cur.includes(k) ? cur.filter(x => x !== k) : [...cur, k]))
  const span = Math.max(spec.xmax - spec.xmin, spec.ymax - spec.ymin)

  return (
    <div className="surface3d">
      <canvas ref={canvas} className="surface3d-canvas" style={{ aspectRatio: `${W} / ${H}` }}
        onPointerDown={down} onPointerMove={move} onPointerUp={() => { drag.current = null }} onPointerCancel={() => { drag.current = null }}
        aria-label={`3D surface of ${spec.expr}; drag to turn it`} role="img" />
      <div className="row surface3d-tools">
        <button className="btn btn-small btn-primary" onClick={() => { if (t >= spec.steps) setT(0); setPlaying(p => !p) }}>
          {playing ? 'Pause' : t >= spec.steps ? 'Play again' : 'Play'}</button>
        <input type="range" min={0} max={spec.steps} value={t} onChange={e => { setPlaying(false); setT(Number(e.target.value)) }}
          aria-label="Step" className="surface3d-step" />
        <span className="muted small">step {t} of {spec.steps}</span>
        <span className="spacer" />
        <button className="btn btn-small" onClick={() => { setYaw(0); setPitch(Math.PI / 2) }}>Top view</button>
        <button className="btn btn-small" onClick={() => { setYaw(-0.7); setPitch(0.62) }}>3D view</button>
      </div>
      <div className="surface3d-legend">
        {ALL.map(k => {
          const p = paths.find(x => x.k === k)
          const at = p ? p.pts[Math.min(t, p.pts.length - 1)] : null
          return (
            <label key={k} className={`surface3d-opt${on.includes(k) ? ' on' : ''}`}>
              <input type="checkbox" checked={on.includes(k)} onChange={() => toggle(k)} />
              <i style={{ background: COLORS[k] }} /> {NAMES[k]}
              {at && <span className="muted small"> loss {fmt(at[2])}{p && p.pts.length - 1 < spec.steps && t >= p.pts.length - 1 ? ' · stopped (left the surface)' : ''}</span>}
            </label>
          )
        })}
      </div>
      <div className="viz-controls surface3d-sliders">
        <label className="small">Learning rate <b>{lr.toPrecision(2)}</b>
          <input type="range" min={-3} max={0} step={0.01} value={Math.log10(lr)} onChange={e => { setLr(10 ** Number(e.target.value)); setT(spec.steps) }} /></label>
        <label className="small">Start x <b>{start[0].toFixed(2)}</b>
          <input type="range" min={spec.xmin} max={spec.xmax} step={span / 200} value={start[0]} onChange={e => setStart([Number(e.target.value), start[1]])} /></label>
        <label className="small">Start y <b>{start[1].toFixed(2)}</b>
          <input type="range" min={spec.ymin} max={spec.ymax} step={span / 200} value={start[1]} onChange={e => setStart([start[0], Number(e.target.value)])} /></label>
      </div>
      <p className="muted small">Drag the surface to turn it. Each path starts at the same point; the dot is where that method is
        after the step shown.</p>
    </div>
  )
}
