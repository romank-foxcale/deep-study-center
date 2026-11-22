import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getFormulaTree, useStore } from '../store'
import { layout } from '../components/graphLayout'
import Markdown from '../components/Markdown'
import type { FormulaTreeNode, FormulaTreeView } from '../types'

// The whole formula tree (SPEC §38): every formula lesson and the blocks it is built from, basics at the bottom.
// An arrow goes from a block to the formula built from it. Learn from the bottom up: a gray block under a formula is
// what you still need before it.

const R = 15
const GLYPH: Record<string, string> = { formula: '=', notation: '∑', idea: '•' }
const STATE: Record<string, string> = { known: 'you hold it', learning: 'learning', writing: 'lesson being written', new: 'new to you' }

function lines(t: string): string[] {
  const out: string[] = []
  let cur = ''
  for (const w of t.split(/\s+/)) {
    if ((cur + ' ' + w).trim().length > 20 && cur) { out.push(cur); cur = w } else cur = (cur + ' ' + w).trim()
  }
  if (cur) out.push(cur)
  return out.length > 3 ? [...out.slice(0, 2), out[2] + '…'] : out
}

export default function Formulas() {
  const { s } = useStore()
  const [params, setParams] = useSearchParams()
  const [tree, setTree] = useState<FormulaTreeView | null>(null)
  const [hideBasic, setHideBasic] = useState(false)
  const selected = params.get('focus')
  const select = (id: string | null) => setParams(id ? { focus: id } : {}, { replace: true })
  const running = s.jobs.filter(j => j.kind === 'formula_lesson' && (j.status === 'queued' || j.status === 'running')).length
  useEffect(() => { getFormulaTree().then(setTree, () => setTree({ nodes: [], links: [] })) }, [running])

  const nodes = useMemo(() => (tree?.nodes ?? []).filter(n => !(hideBasic && n.basic)), [tree, hideBasic])
  const ids = useMemo(() => new Set(nodes.map(n => n.id)), [nodes])
  const links = useMemo(() => (tree?.links ?? []).filter(l => ids.has(l.src) && ids.has(l.dst)), [tree, ids])
  const pos = useMemo(() => layout(nodes.map(n => n.id), links), [nodes, links])
  const byId = useMemo(() => new Map(nodes.map(n => [n.id, n])), [nodes])
  const box = useMemo(() => {
    const ps = [...pos.values()]
    if (!ps.length) return { x: 0, y: 0, w: 0, h: 0 }
    const minX = Math.min(...ps.map(p => p.x)) - 90, maxX = Math.max(...ps.map(p => p.x)) + 90
    const minY = Math.min(...ps.map(p => p.y)) - 30, maxY = Math.max(...ps.map(p => p.y)) + 70
    return { x: minX, y: minY, w: maxX - minX, h: maxY - minY }
  }, [pos])
  // the selected node's whole subtree (everything it is built from) and what is built from it
  const under = useMemo(() => {
    const out = new Set<string>()
    const stack = selected ? [selected] : []
    while (stack.length) {
      const id = stack.pop()!
      for (const l of links) if (l.dst === id && !out.has(l.src)) { out.add(l.src); stack.push(l.src) }
    }
    return out
  }, [selected, links])
  useEffect(() => {  // a link from a lesson opens the tree on its formula
    if (!selected || !pos.has(selected)) return
    document.getElementById(`ft-${selected}`)?.scrollIntoView({ block: 'center', inline: 'center' })
  }, [selected, pos])

  const sel = selected ? byId.get(selected) ?? null : null
  const formulas = nodes.filter(n => n.formula).length
  const held = nodes.filter(n => n.state === 'known').length

  return (
    <div className="page formula-map">
      <div className="km-bar">
        <h1 className="km-title">Formula tree</h1>
        <span className="spacer" />
        <label className="small row"><input type="checkbox" checked={hideBasic} onChange={e => setHideBasic(e.target.checked)} /> Hide basic blocks</label>
        <span className="muted small">{formulas} formula lesson{formulas === 1 ? '' : 's'} · {held} of {nodes.length} blocks you hold</span>
      </div>
      <div className="km-legend small muted">
        {(['known', 'learning', 'writing', 'new'] as const).map(st => <span key={st} className="km-legend-item"><i className={`ft-swatch ft-${st}`} />{STATE[st]}</span>)}
        <span className="km-legend-item">= formula · ∑ notation · • idea. Basics at the bottom; an arrow goes to the formula built from it.</span>
      </div>
      {tree && nodes.length === 0 && (
        <p className="muted">No formula lessons yet. Hover a formula in a lesson and choose "Make a formula lesson".</p>
      )}
      <div className="ft-layout">
        {nodes.length > 0 && (
          <div className="ft-canvas card">
            <svg width={box.w} height={box.h} viewBox={`${box.x} ${box.y} ${box.w} ${box.h}`}
              onClick={e => { if (!(e.target as Element).closest('.ft-node')) select(null) }}>
              <defs>
                <marker id="ft-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" className="km-arrowhead" />
                </marker>
              </defs>
              {links.map(l => {
                const a = pos.get(l.src)!, b = pos.get(l.dst)!
                const hot = selected && (l.dst === selected || l.src === selected || (under.has(l.src) && (under.has(l.dst) || l.dst === selected)))
                const lit = byId.get(l.src)?.state === 'known'
                const dy = Math.max(30, (a.y - b.y) / 2)
                return <path key={`${l.src}>${l.dst}`} className={`km-link ${lit ? 'lit' : ''} ${hot ? 'hot' : ''}`} markerEnd="url(#ft-arrow)"
                  d={`M ${a.x} ${a.y - R} C ${a.x} ${a.y - R - dy}, ${b.x} ${b.y + R + dy}, ${b.x} ${b.y + R + 3}`} />
              })}
              {nodes.map(n => {
                const p = pos.get(n.id)!
                const dim = selected && n.id !== selected && !under.has(n.id) && !links.some(l => l.src === selected && l.dst === n.id)
                return (
                  <g key={n.id} id={`ft-${n.id}`} className={`ft-node ft-${n.state}${n.id === selected ? ' selected' : ''}${dim ? ' dim' : ''}`}
                    transform={`translate(${p.x},${p.y})`} onClick={() => select(n.id === selected ? null : n.id)}
                    role="button" tabIndex={0} aria-label={`${n.name}: ${STATE[n.state]}`}
                    onKeyDown={e => { if (e.key === 'Enter') select(n.id) }}>
                    <title>{`${n.name} (${n.kind}, ${STATE[n.state]})`}</title>
                    {n.formula ? <rect x={-R} y={-R} width={2 * R} height={2 * R} rx={6} className="ft-shape" />
                      : <circle r={R} className="ft-shape" />}
                    <text y={5} textAnchor="middle" className="ft-glyph">{GLYPH[n.kind] ?? '•'}</text>
                    {lines(n.name).map((t, i) => <text key={i} y={R + 14 + i * 13} textAnchor="middle" className="km-label">{t}</text>)}
                  </g>
                )
              })}
            </svg>
          </div>
        )}
        {sel && <NodePanel n={sel} nodes={byId} links={links} onPick={select} />}
      </div>
    </div>
  )
}

function NodePanel({ n, nodes, links, onPick }: {
  n: FormulaTreeNode; nodes: Map<string, FormulaTreeNode>; links: { src: string; dst: string }[]; onPick: (id: string) => void
}) {
  const { dispatch } = useStore()
  const below = links.filter(l => l.dst === n.id).map(l => nodes.get(l.src)).filter((x): x is FormulaTreeNode => !!x)
  const above = links.filter(l => l.src === n.id).map(l => nodes.get(l.dst)).filter((x): x is FormulaTreeNode => !!x)
  const missing = below.filter(b => !b.lesson && !b.basic && b.state !== 'known').length
  const item = (b: FormulaTreeNode) => (
    <li key={b.id}><button className="link" onClick={() => onPick(b.id)}><i className={`ft-swatch ft-${b.state}`} />{b.name}</button>
      <span className="muted small"> · {b.kind}{b.basic ? ' · basic' : ''}</span></li>
  )
  return (
    <aside className="ft-panel card" aria-label="Selected block">
      <div className="eyebrow">{n.formula ? (n.kind === 'notation' ? 'Notation lesson' : 'Formula lesson') : `Building block · ${n.kind}`}</div>
      <h2>{n.name}</h2>
      {n.tex && <Markdown>{`$$${n.tex}$$`}</Markdown>}
      {n.meaning && <div className="small"><Markdown inline>{n.meaning}</Markdown></div>}
      <p className="small"><i className={`ft-swatch ft-${n.state}`} />{STATE[n.state]}{n.basic ? ' (basic: no lesson needed)' : ''}</p>
      {n.covers.length > 0 && <p className="small muted">Teaches here: {n.covers.join(', ')}</p>}
      {n.source?.title && <p className="small muted">From the lesson <Link to={`/lesson/${n.source.id}`}>{n.source.title}</Link></p>}
      <div className="row">
        {n.lesson && <Link className="btn btn-small btn-primary" to={`/lesson/${n.lesson}`}>{n.state === 'known' ? 'Open again' : 'Open the lesson'}</Link>}
        {!n.lesson && !n.basic && <span className="muted small">No lesson yet. Use "Learn these first" on the formula above it.</span>}
      </div>
      {n.formula && !n.blocksReady && <p className="muted small">Its building blocks are found when the lesson is written.</p>}
      {below.length > 0 && <>
        <div className="eyebrow">Built from</div>
        <ul className="ft-list">{below.map(item)}</ul>
      </>}
      {n.formula && missing > 0 && (
        <div className="row small">
          <span>{missing} block{missing > 1 ? 's have' : ' has'} no lesson yet.</span>
          <button className="btn btn-small btn-primary" onClick={() => dispatch({ type: 'learnBlocksFirst', formulaId: n.id })}>Learn {missing > 1 ? 'them' : 'it'} first</button>
        </div>
      )}
      {above.length > 0 && <>
        <div className="eyebrow">Used in</div>
        <ul className="ft-list">{above.map(item)}</ul>
      </>}
    </aside>
  )
}
