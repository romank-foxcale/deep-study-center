import { useMemo, type CSSProperties, type ReactNode } from 'react'
import type { Concept, GridPos, Module, Track } from '../types'

/** Ohtani table (Mandala Chart): nine 3×3 blocks. The goal sits in the middle of the center block, each
 * outer block is one area with its 8 steps around the area name, and the 8 cells around the goal are merge
 * steps that join two neighbouring areas. A cell fills as its concepts are learned (tested, not just opened). */

const RING: GridPos[] = ['TL', 'TM', 'TR', 'MR', 'BR', 'BM', 'BL', 'ML']
/** Ring index → [row, col] inside a 3×3 block (clockwise from the top-left cell). */
const RING_CELL: [number, number][] = [[0, 0], [0, 1], [0, 2], [1, 2], [2, 2], [2, 1], [2, 0], [1, 0]]
const BLOCK: Record<string, [number, number]> = Object.fromEntries([...RING.map((p, i) => [p, RING_CELL[i]]), ['C', [1, 1]]])
const DONE = new Set(['learned', 'mastered', 'rusty'])

export type GridPick = { kind: 'goal' } | { kind: 'area'; trackId: string } | { kind: 'step'; moduleId: string }

export interface StepProgress { done: number; total: number; fill: number; locked: boolean }

export function useStepProgress(modules: Module[], concepts: Concept[]): Record<string, StepProgress> {
  return useMemo(() => {
    const byId = Object.fromEntries(concepts.map(c => [c.id, c]))
    const out: Record<string, StepProgress> = {}
    for (const m of modules) {
      const cs = m.conceptIds.map(id => byId[id]).filter(Boolean)
      const done = cs.filter(c => DONE.has(c.state)).length
      out[m.id] = { done, total: cs.length, fill: m.known ? 1 : cs.length ? done / cs.length : 0, locked: false }
    }
    for (const m of modules) out[m.id].locked = m.requires.some(r => (out[r]?.fill ?? 0) < 1)
    return out
  }, [modules, concepts])
}

const avg = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0)
const pct = (x: number) => `${Math.round(x * 100)}%`

interface Props {
  goalTitle: string
  tracks: Track[]
  modules: Module[]
  concepts: Concept[]
  pick: GridPick | null
  onPick: (p: GridPick) => void
}

export default function OhtaniGrid({ goalTitle, tracks, modules, concepts, pick, onPick }: Props) {
  const prog = useStepProgress(modules, concepts)
  // The step the learner works on now: the module of the first unfinished, unlocked lesson in learning order.
  const current = concepts.find(c => ['ready', 'learning', 'rusty'].includes(c.state))?.moduleId
  const selected = pick?.kind === 'step' ? modules.find(m => m.id === pick.moduleId) : undefined
  const highlighted = new Set(selected?.requires ?? [])
  const total = avg(modules.map(m => prog[m.id].fill))

  // cells[row][col] of the full 9×9 grid
  const cells: (ReactNode | null)[][] = Array.from({ length: 9 }, () => Array(9).fill(null))
  const put = (pos: GridPos, inner: [number, number], el: ReactNode) => {
    const [br, bc] = BLOCK[pos]
    cells[br * 3 + inner[0]][bc * 3 + inner[1]] = el
  }

  for (const t of tracks) {
    if (!BLOCK[t.pos]) continue
    const steps = modules.filter(m => m.trackId === t.id).sort((a, b) => a.ord - b.ord).slice(0, 8)
    steps.forEach((m, i) => {
      const p = prog[m.id]
      const cls = ['og-cell', t.pos === 'C' ? 'og-merge' : 'og-step', p.fill >= 1 && 'og-done', p.locked && p.fill < 1 && 'og-locked',
        m.id === current && 'og-current', pick?.kind === 'step' && pick.moduleId === m.id && 'og-picked',
        highlighted.has(m.id) && 'og-needed'].filter(Boolean).join(' ')
      const status = m.known ? 'known' : p.total ? `${p.done}/${p.total} learned` : `~${m.plannedConcepts} planned`
      put(t.pos, RING_CELL[i], (
        <button key={m.id} className={cls} style={{ '--fill': pct(p.fill) } as CSSProperties}
          title={`${m.title}: ${status}${p.locked && p.fill < 1 ? ' (locked until its steps are learned)' : ''}`}
          onClick={() => onPick({ kind: 'step', moduleId: m.id })}>
          <span className="og-label">{m.title}</span>
        </button>
      ))
    })
    if (t.pos !== 'C') {
      const fill = avg(steps.map(m => prog[m.id].fill))
      const cls = ['og-cell', 'og-area', pick?.kind === 'area' && pick.trackId === t.id && 'og-picked'].filter(Boolean).join(' ')
      put(t.pos, [1, 1], (
        <button key={t.id} className={cls} style={{ '--fill': pct(fill) } as CSSProperties}
          title={`${t.title}: ${pct(fill)}`} onClick={() => onPick({ kind: 'area', trackId: t.id })}>
          <span className="og-label">{t.title}</span>
        </button>
      ))
    }
  }
  put('C', [1, 1], (
    <button key="goal" className={`og-cell og-goal${pick?.kind === 'goal' ? ' og-picked' : ''}`}
      style={{ '--fill': pct(total) } as CSSProperties} title={`${goalTitle}: ${pct(total)}`} onClick={() => onPick({ kind: 'goal' })}>
      <span className="og-label">{goalTitle}</span>
      <span className="og-pct">{pct(total)}</span>
    </button>
  ))

  return (
    <div className="og" role="group" aria-label="Ohtani table">
      {[0, 1, 2].map(br => [0, 1, 2].map(bc => (
        <div key={`${br}${bc}`} className={`og-block${br === 1 && bc === 1 ? ' og-block-center' : ''}`}>
          {[0, 1, 2].map(r => [0, 1, 2].map(c => cells[br * 3 + r][bc * 3 + c] ?? <span key={`${r}${c}`} className="og-cell og-empty" />))}
        </div>
      )))}
    </div>
  )
}
