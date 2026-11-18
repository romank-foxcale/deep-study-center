// An explorable formula (viz type "formula"). Each important part has a color; hovering it shows what it means, and
// the legend under the formula repeats every part in its color. A parameter has a slider (and can be dragged in the
// formula). Every change is explained: the formula again with your values and its result, a line on what the change
// did, and a plot that follows (dashed: the starting values).
// "What if": click a part in the legend and type another form for it (σ√2π → σ√3π, μ → 2μ). The real formula then
// moves to the left ("real") and yours to the right ("yours"), or one above the other when they are too wide. The plot
// shows the real formula dashed, live checks (area under the curve, highest point, ...) compare the two, and a "why"
// prepared for that form (if any) says what breaks. The spec is validated on the server (viz.py).

import katex from 'katex'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { VizSpec } from '../../types'
import { evaluate, parse, resolveRefs, toTex } from './expr'

type Spec = Extract<VizSpec, { type: 'formula' }>
type Part = Spec['parts'][number]
type Param = Spec['params'][number]
interface Edit { text: string; tex: string; expr: string; why: string }

const COLORS: Record<string, string> = {
  green: '#2f9e6e', purple: '#7c6cf0', pink: '#d0508f', orange: '#e08a2e', blue: '#3b8ee0', teal: '#1aa6a8',
}
const FUNCS = /^(sin|cos|tan|exp|log|sqrt|abs|tanh|sigmoid|relu|max|min)$/
const decimals = (p?: Param) => (p && p.max - p.min > 20 ? 0 : p && p.max - p.min <= 2 ? 2 : 1)
const fmt = (v: number, p?: Param) => (Number.isFinite(v) ? v.toFixed(decimals(p)) : '—')
const fmtResult = (v: number) => (!Number.isFinite(v) ? '—' : Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 1 ? v.toFixed(2) : v.toPrecision(3))
const norm = (e: string) => e.replace(/\s+/g, '').toLowerCase()
const tex2html = (tex: string, display = false) =>
  katex.renderToString(tex, { displayMode: display, throwOnError: false, strict: 'ignore', trust: ctx => ctx.command === '\\htmlClass' })

/** Fill in {{id}} parts. `show` returns TeX to use instead of a part (its value), or null; `swap` returns the TeX of
 * the learner's form of the part, or null for the real one. */
function expand(tex: string, parts: Part[], show: (p: Part) => string | null, mark: boolean,
  swap: (p: Part) => string | null = () => null, depth = 0): string {
  if (depth > 4) return tex
  return tex.replace(/\{\{([a-z][a-z0-9_]{0,15})\}\}/g, (_m, id: string, at: number, whole: string) => {
    const p = parts.find(x => x.id === id)
    if (!p) return ''
    let inner = show(p)
    // A value after a number or symbol ("2σ" → "2(1.6)") or a negative value gets parentheses, so it reads right.
    if (inner !== null && (inner.startsWith('-') || /[0-9A-Za-z}]$/.test(whole.slice(0, at).trimEnd()))) inner = `\\left(${inner}\\right)`
    const alt = swap(p)
    if (inner === null && alt !== null && /[0-9A-Za-z}]$/.test(whole.slice(0, at).trimEnd()) && /[+-]/.test(alt)) inner = `\\left(${alt}\\right)`
    inner = inner ?? expand(alt ?? p.tex, parts, show, mark, swap, depth + 1)
    const colored = `\\textcolor{${COLORS[p.color] ?? '#888'}}{${inner}}`
    const cls = `${p.param ? 'fpp' : 'fp'}-${p.id}`
    return mark ? `\\htmlClass{${cls}}{${alt ? `\\htmlClass{fchanged}{${colored}}` : colored}}` : `{${colored}}`
  })
}

function compile(expr?: string) {
  if (!expr) return null
  try { return parse(expr) } catch { return null }
}
const calc = (tree: ReturnType<typeof compile>, vars: Record<string, number>) => {
  if (!tree) return NaN
  try { return evaluate(tree, vars) } catch { return NaN }
}

export default function Formula({ spec }: { spec: Spec }) {
  const start = useMemo(() => Object.fromEntries(spec.params.map(p => [p.name, p.value])), [spec.params])
  const [values, setValues] = useState<Record<string, number>>(start)
  const [changed, setChanged] = useState<{ name: string; from: number } | null>(null)
  const [hover, setHover] = useState<{ part: Part; x: number; y: number } | null>(null)
  const [edits, setEdits] = useState<Record<string, Edit>>({})
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState<{ text: string; error: string }>({ text: '', error: '' })
  const [stacked, setStacked] = useState(false)
  const stage = useRef<HTMLDivElement>(null)
  const pair = useRef<HTMLDivElement>(null)
  const paramOf = (name: string) => spec.params.find(p => p.name === name)
  const partFor = (name: string) => spec.parts.find(p => p.param === name)
  /** A part's real calculator form: its `expr`, or for a parameter part its name. */
  const realExpr = (p: Part) => p.expr ?? p.param ?? undefined
  const edited = spec.parts.filter(p => edits[p.id])
  const anyEdit = edited.length > 0

  const set = (name: string, v: number) => {
    const p = paramOf(name)!
    const step = (p.max - p.min) / 100
    const clean = Math.min(p.max, Math.max(p.min, Math.round(v / step) * step))
    setChanged(c => (c && c.name === name ? c : { name, from: values[name] }))
    setValues(cur => ({ ...cur, [name]: clean }))
  }

  // The real formula and yours, as computable trees: [part] references take the part's form, and an edited
  // parameter part replaces that parameter's name everywhere.
  const trees = useMemo(() => {
    const build = (e: string | undefined, yours: boolean) => {
      if (!e) return null
      let s = resolveRefs(e, id => (yours ? edits[id]?.expr : undefined) ?? spec.parts.find(p => p.id === id)?.expr)
      if (yours) {
        for (const p of spec.parts) {
          if (p.param && edits[p.id]) s = s.replace(new RegExp(`\\b${p.param}\\b`, 'g'), `(${edits[p.id].expr})`)
        }
      }
      return compile(s)
    }
    return { plot: build(spec.plotExpr, true), plotReal: build(spec.plotExpr, false),
      result: build(spec.resultExpr, true), resultReal: build(spec.resultExpr, false) }
  }, [spec, edits])
  const swap = (p: Part) => edits[p.id]?.tex ?? null
  const showValue = (yours: boolean) => (p: Part) => {
    if (!p.param) return null
    if (yours && edits[p.id]) return fmt(calc(compile(edits[p.id].expr), values), paramOf(p.param))
    return fmt(values[p.param], paramOf(p.param))
  }

  const realHtml = useMemo(() => tex2html(expand(spec.tex, spec.parts, () => null, true), true), [spec])
  const yoursHtml = useMemo(() => (anyEdit ? tex2html(expand(spec.tex, spec.parts, () => null, true, swap), true) : ''),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [spec, edits, anyEdit])
  const result = calc(trees.result, values)
  const filled = useMemo(() => {
    const tex = expand(spec.tex, spec.parts, showValue(true), false, swap)
    return tex2html(spec.resultExpr ? `${tex} = ${fmtResult(result)}` : tex, true)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spec, values, result, edits])

  // Real and yours side by side when both fit; one above the other otherwise.
  // A KaTeX display block is as wide as its box; the formula itself is the span of its .base pieces.
  const fits = (el: HTMLElement) => {
    const widths = [...el.querySelectorAll('.formula-side')].map(side => {
      const rects = [...side.querySelectorAll('.katex-html > .base')].map(b => b.getBoundingClientRect())
      return rects.length ? Math.max(...rects.map(r => r.right)) - Math.min(...rects.map(r => r.left)) : 0
    })
    return widths.reduce((a, b) => a + b, 0) + 50 <= el.clientWidth
  }
  useLayoutEffect(() => {
    const el = pair.current
    if (!el || !anyEdit) return
    // measure side by side first, then decide
    el.classList.remove('stacked')
    const st = !fits(el)
    el.classList.toggle('stacked', st)
    setStacked(st)
  }, [realHtml, yoursHtml, anyEdit])
  useEffect(() => {
    const el = pair.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => {
      el.classList.remove('stacked')
      const st = !fits(el)
      el.classList.toggle('stacked', st)
      setStacked(st)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [anyEdit])

  const partOf = (el: EventTarget | null): Part | undefined => {
    const span = (el as HTMLElement | null)?.closest?.('[class*="fp-"], [class*="fpp-"]')
    const cls = span ? [...span.classList].find(c => c.startsWith('fp-') || c.startsWith('fpp-')) : undefined
    return cls ? spec.parts.find(p => cls === `fp-${p.id}` || cls === `fpp-${p.id}`) : undefined
  }

  function onOver(e: React.MouseEvent) {
    const p = partOf(e.target)
    if (!p || !stage.current) { setHover(null); return }
    const span = (e.target as HTMLElement).closest(`.fp-${p.id}, .fpp-${p.id}`)!
    const r = span.getBoundingClientRect(), base = stage.current.getBoundingClientRect()
    setHover({ part: p, x: r.left + r.width / 2 - base.left, y: r.top - base.top })
  }

  function startDrag(e: React.PointerEvent) {
    const p = partOf(e.target)
    const param = p?.param ? paramOf(p.param) : undefined
    if (!param) return
    e.preventDefault()
    const x0 = e.clientX, v0 = values[param.name]
    const move = (ev: PointerEvent) => set(param.name, v0 + ((ev.clientX - x0) / 240) * (param.max - param.min))
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  // Typing another form for a part: every valid change shows at once; the real form (or empty) restores it.
  function type(p: Part, text: string) {
    const clean = text.trim().toLowerCase()
    const real = realExpr(p)!
    if (!clean || norm(clean) === norm(real)) {
      setEdits(cur => { const next = { ...cur }; delete next[p.id]; return next })
      setDraft({ text, error: '' })
      return
    }
    const allowed = new Set([...spec.params.map(x => x.name), 'pi', 'e', 'x'])
    try {
      const tree = parse(clean)
      const bad = (clean.match(/[a-z_][a-z0-9_]*/g) ?? []).find(n => !FUNCS.test(n) && !allowed.has(n))
      if (bad) throw new Error(`unknown name “${bad}”: use ${[...allowed].join(', ')}`)
      const why = p.variants?.find(v => norm(v.expr) === norm(clean))?.why ?? ''
      setEdits(cur => ({ ...cur, [p.id]: { text, tex: toTex(tree), expr: clean, why } }))
      setDraft({ text, error: '' })
    } catch (err) {
      setDraft({ text, error: (err as Error).message })
    }
  }
  const openEditor = (p: Part) => { setEditing(p.id); setDraft({ text: edits[p.id]?.text ?? realExpr(p) ?? '', error: '' }) }
  const restore = (p: Part) => { setEdits(cur => { const next = { ...cur }; delete next[p.id]; return next }); if (editing === p.id) setEditing(null) }

  // The plot over x (or over one parameter), and the numbers the checks need.
  const series = useMemo(() => {
    if (!trees.plot) return null
    const v = spec.plotVar ?? 'x', xmin = spec.xmin ?? -5, xmax = spec.xmax ?? 5
    const curve = (tree: ReturnType<typeof compile>, vars: Record<string, number>) => {
      const pts: [number, number][] = []
      for (let i = 0; i <= 400; i++) {
        const x = xmin + ((xmax - xmin) * i) / 400
        const y = calc(tree, { ...vars, [v]: x, x })
        if (Number.isFinite(y)) pts.push([x, y])
      }
      return pts
    }
    return { v, xmin, xmax, now: curve(trees.plot, values), ref: anyEdit ? curve(trees.plotReal, values) : curve(trees.plot, start) }
  }, [trees, spec, values, start, anyEdit])

  const plot = useMemo(() => {
    if (!series) return null
    const { now, ref, xmin, xmax, v } = series
    const ys = [...now, ...ref].map(p => p[1])
    const ymin = Math.min(0, ...ys), ymax = Math.max(0.1, ...ys)
    const W = 480, H = 170
    const px = (x: number) => ((x - xmin) / (xmax - xmin)) * W
    const py = (y: number) => H - 8 - ((y - ymin) / (ymax - ymin || 1)) * (H - 16)
    const d = (pts: [number, number][]) => pts.map((p, i) => `${i ? 'L' : 'M'}${px(p[0]).toFixed(1)},${py(p[1]).toFixed(1)}`).join('')
    const dotX = v !== 'x' ? values[v] : null
    const dotY = dotX !== null ? calc(trees.plot, { ...values, x: dotX }) : NaN
    const color = COLORS[partFor(v)?.color ?? 'pink'] ?? COLORS.pink
    return { W, H, now: d(now), ref: d(ref), axisY: py(0), axisX: xmin < 0 && xmax > 0 ? px(0) : null, color,
      dot: dotX !== null && Number.isFinite(dotY) ? { x: px(dotX), y: py(dotY) } : null }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [series])

  // Checks: the real formula vs yours.
  const measure = (kind: string, yours: boolean, at?: number) => {
    if (kind === 'result') return calc(yours ? trees.result : trees.resultReal, values)
    const tree = yours ? trees.plot : trees.plotReal
    const pts = yours ? series?.now : (anyEdit ? series?.ref : series?.now)
    if (kind === 'at') return calc(tree, { ...values, [spec.plotVar ?? 'x']: at ?? 0, x: at ?? 0 })
    if (!pts || pts.length < 2) return NaN
    if (kind === 'peak') return Math.max(...pts.map(p => p[1]))
    let a = 0
    for (let i = 1; i < pts.length; i++) a += ((pts[i][0] - pts[i - 1][0]) * (pts[i][1] + pts[i - 1][1])) / 2
    return a
  }
  const checks = (spec.checks ?? []).map(c => {
    const real = measure(c.kind, false, c.at)
    const now = anyEdit ? measure(c.kind, true, c.at) : NaN
    const good = (x: number) => c.expect === undefined || (Number.isFinite(x) && Math.abs(x - c.expect) <= Math.max(0.02 * Math.abs(c.expect), 0.01))
    return { ...c, real, now, realOk: good(real), nowOk: good(now) }
  })

  const cp = changed ? paramOf(changed.name) : undefined
  const cpart = changed ? partFor(changed.name) : undefined
  const reset = () => { setValues(start); setChanged(null); setEdits({}); setEditing(null) }
  const plain = (t: string, yours = false) => expand(t, spec.parts, () => null, false, yours ? swap : () => null).replace(/\\textcolor\{#[0-9a-f]{6}\}/gi, '')
  const askTutor = () => {
    const lines = checks.map(c => `${c.label}: real ${fmtResult(c.real)}, mine ${fmtResult(c.now)}`).join('; ')
    const what = edited.map(p => `“${p.label}” from $${plain(p.tex)}$ to $${edits[p.id].tex}$`).join(' and ')
    window.dispatchEvent(new CustomEvent('dsc:ask-tutor', { detail:
      `The real formula is $${plain(spec.tex)}$. I changed ${what}, so mine is $${plain(spec.tex, true)}$. ` +
      `${lines ? `Checks: ${lines}. ` : ''}Why does the formula use the real form? What goes wrong with mine?` }))
  }

  return (
    <div className="formula-w">
      <div className="formula-stage" ref={stage} onPointerDown={startDrag} onMouseOver={onOver} onMouseLeave={() => setHover(null)}>
        {anyEdit ? (
          <div className={`formula-pair ${stacked ? 'stacked' : ''}`} ref={pair}>
            <div className="formula-side"><span className="formula-tag">real</span><div className="formula-math" dangerouslySetInnerHTML={{ __html: realHtml }} /></div>
            <div className="formula-sep" aria-hidden />
            <div className="formula-side yours"><span className="formula-tag yours">yours</span><div className="formula-math" dangerouslySetInnerHTML={{ __html: yoursHtml }} /></div>
          </div>
        ) : (
          <div className="formula-math" dangerouslySetInnerHTML={{ __html: realHtml }} />
        )}
        {hover && (
          <div className="formula-tip" style={{ left: hover.x, top: hover.y, borderColor: COLORS[hover.part.color], color: COLORS[hover.part.color] }}>
            {hover.part.label}{hover.part.param && <span className="muted"> · drag or use the slider</span>}
          </div>
        )}
      </div>

      <div className="formula-legend">
        {spec.parts.map(p => {
          const param = p.param ? paramOf(p.param) : undefined
          const canEdit = !!realExpr(p)
          const sym = edits[p.id] ? edits[p.id].tex : expand(p.tex, spec.parts, () => null, false)
          return (
            <div key={p.id} className={`formula-row ${hover?.part.id === p.id ? 'on' : ''} ${editing === p.id ? 'editing' : ''}`} style={{ '--c': COLORS[p.color] } as React.CSSProperties}>
              {editing === p.id ? (
                <span className="formula-edit">
                  <input autoFocus className={`input input-small ${draft.error ? 'bad' : ''}`} value={draft.text}
                    aria-label={`Change ${p.label}`} onChange={e => type(p, e.target.value)}
                    onBlur={() => setEditing(null)} onKeyDown={e => { if (e.key === 'Enter' || e.key === 'Escape') setEditing(null) }} />
                </span>
              ) : (
                <button className={`formula-sym ${canEdit ? 'editable' : ''} ${edits[p.id] ? 'edited' : ''}`} disabled={!canEdit}
                  title={canEdit ? 'Click to change this part and see what happens' : undefined} onClick={() => openEditor(p)}
                  dangerouslySetInnerHTML={{ __html: tex2html(`\\textcolor{${COLORS[p.color]}}{${sym}}`) }} />
              )}
              <span className="formula-desc">
                {p.label}
                {edits[p.id] && <> · <button className="link small" onMouseDown={e => e.preventDefault()} onClick={() => restore(p)}>back to real</button></>}
                {editing === p.id && draft.error && <span className="small bad-text"> · {draft.error}</span>}
                {editing === p.id && !draft.error && p.variants?.length ? (
                  <span className="muted small"> · try {p.variants.map(v => v.expr).join(', ')}</span>
                ) : null}
              </span>
              {param ? (
                <span className="formula-control">
                  <input type="range" min={param.min} max={param.max} step={(param.max - param.min) / 100} value={values[param.name]}
                    aria-label={p.label} onChange={e => set(param.name, Number(e.target.value))} />
                  <span className="formula-val">{fmt(values[param.name], param)}</span>
                </span>
              ) : <span />}
            </div>
          )
        })}
        {!anyEdit && spec.parts.some(p => realExpr(p)) && <span className="muted small">Click a colored part above to change it and see why the formula is as it is.</span>}
      </div>

      <details className="formula-fold" open>
        <summary>{anyEdit ? 'Your formula, with your values' : 'With your values'}</summary>
        <div dangerouslySetInnerHTML={{ __html: filled }} />
      </details>

      {anyEdit && (
        <div className="formula-why">
          {edited.map(p => (
            <div key={p.id}>
              <strong>Why the real formula uses <span dangerouslySetInnerHTML={{ __html: tex2html(`\\textcolor{${COLORS[p.color]}}{${expand(p.tex, spec.parts, () => null, false)}}`) }} /></strong>
              {edits[p.id].why ? <span> — {edits[p.id].why}</span> : <span className="muted"> — the checks below show what your change does.</span>}
            </div>
          ))}
          <button className="link small" onClick={askTutor}>Ask the tutor why</button>
        </div>
      )}

      {checks.length > 0 && (
        <details className="formula-fold" open>
        <summary>Checks{anyEdit ? `: ${checks.filter(c => c.expect !== undefined && !c.nowOk).length ? 'yours breaks something' : 'yours passes'}` : ''}</summary>
        <table className="formula-checks">
          <thead><tr><th>Check</th><th>Real</th>{anyEdit && <th>Yours</th>}</tr></thead>
          <tbody>
            {checks.map((c, i) => (
              <tr key={i}>
                <td>{c.label}{c.expect !== undefined && <span className="muted"> (should be {fmtResult(c.expect)})</span>}</td>
                <td>{c.kind === 'area' ? '≈ ' : ''}{fmtResult(c.real)} {c.expect !== undefined && (c.realOk ? <span className="ok-text">✓</span> : <span className="bad-text">✗</span>)}</td>
                {anyEdit && <td>{c.kind === 'area' ? '≈ ' : ''}{fmtResult(c.now)} {c.expect !== undefined && (c.nowOk ? <span className="ok-text">✓</span> : <span className="bad-text">✗</span>)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
        </details>
      )}

      {changed && cp && (
        <div className="formula-change" style={{ borderColor: COLORS[cpart?.color ?? 'blue'] }}>
          <span dangerouslySetInnerHTML={{ __html: tex2html(`\\textcolor{${COLORS[cpart?.color ?? 'blue']}}{${cpart ? expand(cpart.tex, spec.parts, () => null, false) : cp.name}}`) }} />
          {' '}went from {fmt(changed.from, cp)} to {fmt(values[cp.name], cp)}
          {cp.effect && <span className="muted"> (when it grows: {cp.effect})</span>}
          {spec.resultExpr && <> → result {fmtResult(calc(trees.result, { ...values, [cp.name]: changed.from }))} → {fmtResult(result)}</>}
        </div>
      )}
      {(changed || anyEdit) && <div><button className="link small" onClick={reset}>Reset everything</button></div>}

      {plot && (
        <svg viewBox={`0 0 ${plot.W} ${plot.H}`} className="formula-plot" role="img" aria-label="Plot that follows the formula">
          <line x1={0} y1={plot.axisY} x2={plot.W} y2={plot.axisY} className="viz-axis" />
          {plot.axisX !== null && <line x1={plot.axisX} y1={0} x2={plot.axisX} y2={plot.H} className="viz-axis" />}
          <path d={plot.ref} className="formula-curve-start" />
          <path d={plot.now} className="formula-curve" style={{ stroke: plot.color }} />
          {plot.dot && <circle cx={plot.dot.x} cy={plot.dot.y} r={5} fill={plot.color} />}
          <g className="formula-plot-legend" transform={`translate(${plot.W - 118}, 8)`}>
            <rect x={-8} y={-4} width={122} height={40} rx={6} />
            <line x1={0} y1={8} x2={26} y2={8} className="formula-curve-start" />
            <text x={34} y={12}>{anyEdit ? 'real' : 'at the start'}</text>
            <line x1={0} y1={26} x2={26} y2={26} className="formula-curve" style={{ stroke: plot.color }} />
            <text x={34} y={30}>{anyEdit ? 'yours' : 'now'}</text>
          </g>
        </svg>
      )}
      {plot && (
        <div className="viz-readout">
          <span>Across: {spec.plotVar && spec.plotVar !== 'x' ? (partFor(spec.plotVar)?.label ?? spec.plotVar) : 'x'}
            {' '}({fmt(spec.xmin ?? -5)} to {fmt(spec.xmax ?? 5)})</span>
          <span>Up: {spec.resultTex
            ? <span dangerouslySetInnerHTML={{ __html: tex2html(spec.resultTex) }} />
            : 'the formula’s value'}</span>
        </div>
      )}
    </div>
  )
}
