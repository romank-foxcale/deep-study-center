import { useMemo } from 'react'
import Markdown from './Markdown'
import type { SessionIdea } from '../types'

// The plan of a study session as a graph (SPEC §54): an arrow means "needed for"; ideas side by side can be learned in
// any order. Colors say what placement found: new to you (blue), partly known (orange), you know it (green, dashed,
// skipped). On the Learn step it also shows what is done, the idea now, and the ideas open now.

const W = 190, H = 68, GX = 18, GY = 36

/** Rows from the top: the goal on top, the ideas with nothing they need at the bottom. */
function layout(ideas: SessionIdea[]) {
  const by = new Map(ideas.map(i => [i.key, i]))
  const level = new Map<string, number>()
  const lv = (k: string, seen: Set<string>): number => {
    if (level.has(k)) return level.get(k)!
    if (seen.has(k)) return 0
    seen.add(k)
    const v = Math.max(-1, ...(by.get(k)?.prereqs ?? []).filter(p => by.has(p)).map(p => lv(p, seen))) + 1
    level.set(k, v)
    return v
  }
  ideas.forEach(i => lv(i.key, new Set()))
  const top = Math.max(0, ...level.values())
  const rows: string[][] = Array.from({ length: top + 1 }, () => [])
  ideas.forEach(i => rows[top - level.get(i.key)!].push(i.key))
  const widest = Math.max(1, ...rows.map(r => r.length))
  const w = widest * (W + GX) - GX
  const at = new Map<string, { x: number; y: number }>()
  rows.forEach((row, r) => {
    const x0 = (w - (row.length * (W + GX) - GX)) / 2
    row.forEach((k, j) => at.set(k, { x: x0 + j * (W + GX), y: r * (H + GY) }))
  })
  return { at, w, h: rows.length * (H + GY) - GY }
}

export type IdeaMark = 'skip' | 'done' | 'now' | 'open' | 'later'
export const LEVEL_LABEL: Record<string, string> = { known: 'you know it', partial: 'partly known', unknown: 'new to you' }

export function levelOf(i: SessionIdea): 'known' | 'partial' | 'new' {
  return i.level === 'known' && !i.again ? 'known' : i.level === 'partial' || i.again ? 'partial' : 'new'
}

export default function SessionPlanGraph({ ideas, marks, selected, onSelect, small }: {
  ideas: SessionIdea[]; marks: Record<string, IdeaMark>; selected?: string | null; onSelect?: (key: string) => void; small?: boolean
}) {
  const geo = useMemo(() => layout(ideas), [ideas])
  const scale = small ? Math.min(0.8, 280 / Math.max(1, geo.w)) : 1
  return (
    <div className={`sp-canvas${small ? ' sp-small' : ''}`}>
      <div className="sp-world" style={{ width: geo.w * scale, height: geo.h * scale }}>
        <div style={{ width: geo.w, height: geo.h, transform: `scale(${scale})`, transformOrigin: '0 0', position: 'relative' }}>
          <svg className="lp-edges" width={geo.w} height={geo.h} aria-hidden>
            {ideas.flatMap(i => i.prereqs.map(p => {
              const a = geo.at.get(p), b = geo.at.get(i.key)
              if (!a || !b) return null
              const x1 = a.x + W / 2, y1 = a.y, x2 = b.x + W / 2, y2 = b.y + H
              const hot = selected && (p === selected || i.key === selected)
              return <path key={`${p}>${i.key}`} className={hot ? 'hot' : ''} d={`M ${x1} ${y1} C ${x1} ${(y1 + y2) / 2}, ${x2} ${(y1 + y2) / 2}, ${x2} ${y2}`} />
            }))}
          </svg>
          {ideas.map(i => {
            const p = geo.at.get(i.key)!
            const m = marks[i.key] ?? 'later'
            const lv = levelOf(i)
            const note = m === 'skip' ? 'skipped · you know it' : m === 'done' ? 'done' : m === 'now' ? 'learning now' : m === 'open' ? 'open now'
              : LEVEL_LABEL[lv === 'new' ? 'unknown' : lv]
            return (
              <div key={i.key} role={onSelect ? 'button' : undefined} tabIndex={onSelect ? 0 : undefined}
                className={`sp-node sp-${lv} sp-${m}${i.target ? ' sp-goal' : ''}${selected === i.key ? ' selected' : ''}`}
                style={{ left: p.x, top: p.y, width: W, height: H }}
                onClick={() => onSelect?.(i.key)} onKeyDown={e => { if (e.key === 'Enter') onSelect?.(i.key) }}
                aria-label={`${i.title}: ${note}`}>
                <div className="sp-title">{m === 'done' && '✓ '}<Markdown inline>{i.title}</Markdown>{i.target && ' ★'}</div>
                <div className="sp-note">{note}</div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
