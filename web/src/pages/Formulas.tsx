import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getFormulaTree, useStore } from '../store'
import Markdown from '../components/Markdown'
import type { FormulaTreeNode, FormulaTreeView } from '../types'

// The formula derivation graph (SPEC §38, §40). Pick a formula: it is at the top, and under it the formulas, notations
// and ideas it is derived from, each with its own formula. Open a node to see what it is built from, one level down,
// down to the basics. A node gets a formula page (a short lesson) only when you ask for one.

const W = 230, H = 104, GX = 26, GY = 70
const STATE: Record<string, string> = { known: 'you hold it', learning: 'learning', writing: 'page being written', new: 'new to you' }
const KIND: Record<string, string> = { formula: 'formula', notation: 'notation', idea: 'idea' }

interface Placed { n: FormulaTreeNode; x: number; y: number; level: number }

/** Levels from the roots down (a node shared by two formulas is placed once, at its first level), then each level in
 *  the order of its parents. */
function place(roots: string[], byId: Map<string, FormulaTreeNode>, kids: Map<string, string[]>): { at: Map<string, Placed>; w: number; h: number } {
  const level = new Map<string, number>()
  const order: string[][] = []
  let cur = roots.filter(r => byId.has(r))
  cur.forEach(r => level.set(r, 0))
  for (let d = 0; cur.length && d < 40; d++) {
    order.push(cur)
    const next: string[] = []
    for (const id of cur) for (const k of kids.get(id) ?? []) {
      if (!level.has(k) && byId.has(k)) { level.set(k, d + 1); next.push(k) }
    }
    cur = next
  }
  const widest = Math.max(1, ...order.map(r => r.length))
  const totalW = widest * (W + GX) - GX
  const at = new Map<string, Placed>()
  order.forEach((row, d) => {
    const rowW = row.length * (W + GX) - GX, x0 = (totalW - rowW) / 2
    row.forEach((id, i) => at.set(id, { n: byId.get(id)!, x: x0 + i * (W + GX), y: d * (H + GY), level: d }))
  })
  return { at, w: totalW, h: order.length * (H + GY) - GY }
}

export default function Formulas() {
  const { s, dispatch } = useStore()
  const [params, setParams] = useSearchParams()
  const [tree, setTree] = useState<FormulaTreeView | null>(null)
  const [hideBasic, setHideBasic] = useState(false)
  const root = params.get('focus')
  const [selected, setSelected] = useState<string | null>(root)
  const setRoot = (id: string | null) => { setParams(id ? { focus: id } : {}, { replace: true }); setSelected(id) }
  const running = s.jobs.filter(j => (j.kind === 'formula_lesson' || j.kind === 'formula_open') && (j.status === 'queued' || j.status === 'running')).length
  useEffect(() => { getFormulaTree().then(setTree, () => setTree({ nodes: [], links: [] })) }, [running])

  const byId = useMemo(() => new Map((tree?.nodes ?? []).filter(n => !(hideBasic && n.basic)).map(n => [n.id, n])), [tree, hideBasic])
  const links = useMemo(() => (tree?.links ?? []).filter(l => byId.has(l.src) && byId.has(l.dst)), [tree, byId])
  /** parent -> what it is built from (a link goes from the part to the formula built from it) */
  const kids = useMemo(() => {
    const m = new Map<string, string[]>()
    for (const l of links) m.set(l.dst, [...(m.get(l.dst) ?? []), l.src])
    return m
  }, [links])
  const tops = useMemo(() => {  // formulas nothing else is built from: the starting points
    const used = new Set(links.map(l => l.src))
    return [...byId.values()].filter(n => n.formula && !used.has(n.id))
  }, [byId, links])
  const roots = root && byId.has(root) ? [root] : tops.map(n => n.id)
  const { at, w, h } = useMemo(() => place(roots, byId, kids), [roots.join('|'), byId, kids])  // eslint-disable-line react-hooks/exhaustive-deps
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => { box.current?.scrollTo({ left: Math.max(0, (w - (box.current?.clientWidth ?? 0)) / 2) }) }, [w, root])
  // a long formula is made smaller until it fits its card
  useLayoutEffect(() => {
    box.current?.querySelectorAll<HTMLElement>('.ft-card-tex').forEach(el => {
      const m = el.querySelector<HTMLElement>('.katex')
      if (!m) return
      m.style.fontSize = ''
      const r = m.getBoundingClientRect()  // .katex is inline: its scroll size is 0, its box is not
      const k = Math.min(1, (el.clientWidth - 4) / Math.max(1, r.width), (el.clientHeight - 2) / Math.max(1, r.height))
      if (k < 1) m.style.fontSize = `${Math.max(0.45, k)}em`
    })
  })

  const sel = selected ? byId.get(selected) ?? null : null
  const formulas = [...byId.values()].filter(n => n.formula)

  return (
    <div className="page page-wide formula-map">
      <div className="km-bar">
        <h1 className="km-title">Formula tree</h1>
        <select className="input input-small" value={root ?? ''} aria-label="Formula" onChange={e => setRoot(e.target.value || null)}>
          <option value="">All formulas ({tops.length})</option>
          {formulas.map(n => <option key={n.id} value={n.id}>{n.name}</option>)}
        </select>
        <span className="spacer" />
        <label className="small row"><input type="checkbox" checked={hideBasic} onChange={e => setHideBasic(e.target.checked)} /> Hide basic arithmetic</label>
      </div>
      <p className="muted small">A formula is at the top; under it, what it is derived from, each with its own formula. Click “What is it built
        from?” on a node to go one level down. Green: you hold it. Orange: learning. Gray: new to you.</p>
      {tree && byId.size === 0 && (
        <p className="muted">No formulas yet. Hover a formula in a lesson and choose “Make a lesson about this formula”.</p>
      )}
      <div className="ft-layout">
        {byId.size > 0 && (
          <div className="ft-canvas card" ref={box}>
            <div className="ft-world" style={{ width: w, height: h }}>
              <svg className="ft-edges" width={w} height={h} aria-hidden>
                {links.map(l => {
                  const a = at.get(l.dst), b = at.get(l.src)  // a: the formula, b: a part of it
                  if (!a || !b) return null
                  const x1 = a.x + W / 2, y1 = a.y + H, x2 = b.x + W / 2, y2 = b.y
                  const hot = selected && (l.src === selected || l.dst === selected)
                  const lit = b.n.state === 'known'
                  return <path key={`${l.src}>${l.dst}`} className={`ft-edge${hot ? ' hot' : ''}${lit ? ' lit' : ''}`}
                    d={`M ${x1} ${y1} C ${x1} ${(y1 + y2) / 2}, ${x2} ${(y1 + y2) / 2}, ${x2} ${y2}`} />
                })}
              </svg>
              {[...at.values()].map(p => (
                <div key={p.n.id} className={`ft-card ft-${p.n.state}${p.n.formula ? ' ft-has-page' : ''}${p.n.id === selected ? ' selected' : ''}`}
                  style={{ left: p.x, top: p.y, width: W, height: H }} role="button" tabIndex={0}
                  aria-label={`${p.n.name}: ${STATE[p.n.state]}`} onClick={() => setSelected(p.n.id === selected ? null : p.n.id)}
                  onKeyDown={e => { if (e.key === 'Enter') setSelected(p.n.id) }}>
                  <div className="ft-card-name">{p.n.name}</div>
                  <div className="ft-card-tex">{p.n.tex ? <Markdown inline>{`$${p.n.tex}$`}</Markdown> : <span className="muted small">{KIND[p.n.kind]}</span>}</div>
                  <div className="ft-card-foot small">
                    {p.n.opening ? <span className="muted">Finding its parts…</span>
                      : p.n.openable ? <button className="link small" onClick={e => { e.stopPropagation(); dispatch({ type: 'openFormula', node: p.n.id }) }}>What is it built from?</button>
                        : (kids.get(p.n.id)?.length ?? 0) > 0 && root !== p.n.id
                          ? <button className="link small" onClick={e => { e.stopPropagation(); setRoot(p.n.id) }}>Start here</button>
                          : <span className="muted">{p.n.basic ? 'basic' : p.n.lesson ? 'has a page' : ''}</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        {sel && <NodePanel n={sel} parts={(kids.get(sel.id) ?? []).map(k => byId.get(k)!).filter(Boolean)}
          usedIn={links.filter(l => l.src === sel.id).map(l => byId.get(l.dst)!).filter(Boolean)} onPick={id => setSelected(id)} />}
      </div>
    </div>
  )
}

function NodePanel({ n, parts, usedIn, onPick }: { n: FormulaTreeNode; parts: FormulaTreeNode[]; usedIn: FormulaTreeNode[]; onPick: (id: string) => void }) {
  const { dispatch } = useStore()
  const item = (b: FormulaTreeNode) => (
    <li key={b.id}><button className="link" onClick={() => onPick(b.id)}><i className={`ft-swatch ft-${b.state}`} />{b.name}</button>
      {b.tex && <span className="small"> <Markdown inline>{`$${b.tex}$`}</Markdown></span>}</li>
  )
  return (
    <aside className="ft-panel card" aria-label="Selected formula">
      <div className="eyebrow">{n.lesson ? (n.kind === 'notation' ? 'Notation page' : 'Formula page') : KIND[n.kind]}</div>
      <h2>{n.name}</h2>
      {n.tex && <Markdown>{`$$${n.tex}$$`}</Markdown>}
      {n.meaning && <div className="small"><Markdown inline>{n.meaning}</Markdown></div>}
      <p className="small"><i className={`ft-swatch ft-${n.state}`} />{STATE[n.state]}{n.basic ? ' (basic arithmetic)' : ''}</p>
      {n.covers.length > 0 && <p className="small muted">Teaches here: {n.covers.join(', ')}</p>}
      <div className="row">
        {n.lesson && <Link className="btn btn-small btn-primary" to={`/lesson/${n.lesson}`}>Open the page</Link>}
        {!n.lesson && !n.basic && n.kind !== 'idea' && (
          <button className="btn btn-small" disabled={n.state === 'writing'} onClick={() => dispatch({ type: 'makeFormulaPage', node: n.id })}>
            Make a formula page</button>
        )}
        {n.openable && !n.opening && <button className="btn btn-small" onClick={() => dispatch({ type: 'openFormula', node: n.id })}>What is it built from?</button>}
        {n.opening && <span className="muted small">Finding its parts…</span>}
      </div>
      {parts.length > 0 && <>
        <div className="eyebrow">Derived from</div>
        <ul className="ft-list">{parts.map(item)}</ul>
      </>}
      {usedIn.length > 0 && <>
        <div className="eyebrow">Used in</div>
        <ul className="ft-list">{usedIn.map(item)}</ul>
      </>}
    </aside>
  )
}
