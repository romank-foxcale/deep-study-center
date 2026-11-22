import { useEffect, useRef, useState, type RefObject } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { jobActive, useStore } from '../store'
import type { FormulaNote } from '../types'
import Markdown from './Markdown'

const STATE: Record<string, string> = {
  mastered: 'know strongly', learned: 'learned', learning: 'learning', rusty: 'due for review', ready: 'ready to learn',
  locked: 'new', pending: 'new',
}
/** The same key the backend uses: the formula's TeX without any white space. */
const keyOf = (tex: string) => tex.replace(/\s+/g, '').slice(0, 600)
const texOf = (math: Element) => math.querySelector('annotation[encoding="application/x-tex"]')?.textContent ?? ''

/** Hover a formula in the lesson (SPEC §33, §34): its name, what it says, its symbols, where you met it, and its formula
 * lesson. Display formulas get a frame: green (you learned its formula lesson, in this form), orange (a formula lesson
 * exists, this form is new to it), gray (no formula lesson yet), faint (a step of a derivation). */
export default function FormulaHover({ root, notes, pending, conceptId }: {
  root: RefObject<HTMLElement | null>; notes: Record<string, FormulaNote>; pending: boolean; conceptId: string
}) {
  const { s, dispatch } = useStore()
  const [at, setAt] = useState<{ key: string; top: number; left: number; below: boolean } | null>(null)
  const hide = useRef<number | undefined>(undefined)
  const card = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  // frames on the display formulas, again whenever the lesson's text changes on the page
  useEffect(() => {
    const el = root.current
    if (!el) return
    const paint = () => {
      el.querySelectorAll('.katex-display').forEach(m => {
        if (m.closest('.viz')) return
        const n = notes[keyOf(texOf(m))]
        const fx = n ? n.status : 'none'
        if (m.getAttribute('data-fx') !== fx) m.setAttribute('data-fx', fx)
      })
      // formulas inside a sentence: a light frame only when they have a note and are an idea (not a step, not a symbol)
      el.querySelectorAll('.katex').forEach(m => {
        if (m.closest('.katex-display') || m.closest('.viz')) return
        const n = notes[keyOf(texOf(m))]
        if (n && n.status !== 'step' && m.getAttribute('data-fx') !== n.status) m.setAttribute('data-fx', n.status)
      })
    }
    paint()
    const mo = new MutationObserver(paint)
    mo.observe(el, { childList: true, subtree: true })
    return () => mo.disconnect()
  }, [root, notes])

  useEffect(() => {
    const el = root.current
    if (!el) return
    const over = (e: MouseEvent) => {
      const t = e.target as HTMLElement
      if (t.closest('.viz')) return  // formula widgets explain their own parts
      const math = (t.closest('.katex-display') ?? t.closest('.katex')) as HTMLElement | null
      if (!math) return
      const k = keyOf(texOf(math))
      if (!notes[k] && !pending) return
      window.clearTimeout(hide.current)
      const r = math.getBoundingClientRect()
      const inner = math.querySelector('.katex-html')?.getBoundingClientRect() ?? r
      const below = r.top < 300
      setAt({ key: k, top: below ? r.bottom + 6 : r.top - 6, left: Math.min(Math.max(12, inner.left), window.innerWidth - 392), below })
    }
    const out = (e: MouseEvent) => {
      const to = e.relatedTarget as Node | null
      if (to && card.current?.contains(to)) return
      if ((e.target as HTMLElement).closest('.katex')) hide.current = window.setTimeout(() => setAt(null), 250)
    }
    el.addEventListener('mouseover', over)
    el.addEventListener('mouseout', out)
    return () => { el.removeEventListener('mouseover', over); el.removeEventListener('mouseout', out) }
  }, [root, notes, pending])

  useEffect(() => {
    const close = () => setAt(null)
    window.addEventListener('scroll', close, true)
    return () => window.removeEventListener('scroll', close, true)
  }, [])

  if (!at) return null
  const n = notes[at.key] ?? null
  const f = n?.formula ?? null
  const writing = !!f && jobActive(s, 'formula_lesson', { concept_id: f.id })
  return (
    <div ref={card} className={`formula-card${at.below ? '' : ' above'} fx-card-${n?.status ?? 'none'}`} style={{ top: at.top, left: at.left }}
      role="tooltip" onMouseEnter={() => window.clearTimeout(hide.current)} onMouseLeave={() => { hide.current = window.setTimeout(() => setAt(null), 200) }}>
      {!n && <span className="muted small">Explaining the formulas of this lesson…</span>}
      {n && <>
        <strong>{n.name}</strong>
        {n.meaning && <div className="small"><Markdown inline>{n.meaning}</Markdown></div>}
        {n.symbols.length > 0 && (
          <table className="formula-symbols small"><tbody>
            {n.symbols.map((x, i) => <tr key={i}><td><Markdown inline>{`$${x.tex}$`}</Markdown></td><td><Markdown inline>{x.meaning}</Markdown></td></tr>)}
          </tbody></table>
        )}
        {n.status !== 'step' && (
          <div className={`formula-own small fx-own-${n.status}`}>
            {n.status === 'green' && f && <span>You know this formula in this form: <Link to={`/lesson/${f.id}`}>{f.title}</Link></span>}
            {f && f.missing > 0 && <span className="muted">It is built from {f.missing} block{f.missing > 1 ? 's' : ''} you have not learned yet:
              <Link to={`/lesson/${f.id}`}> see the formula tree</Link>.</span>}
            {n.status === 'orange' && f && <>
              <span>You know this formula in another form: <Link to={`/lesson/${f.id}`}>{f.title}</Link>.</span>
              {writing ? <span className="muted">Writing the formula lesson…</span>
                : <button className="btn btn-small" onClick={() => dispatch({ type: 'addFormulaForm', conceptId, key: at.key, formulaId: f.id })}>
                    Add this form to that lesson</button>}
            </>}
            {n.status === 'gray' && f && (f.here
              ? <span className="muted">This is the formula of this lesson.</span>
              : <span>{writing ? 'Writing its lesson… ' : 'Its lesson is not learned yet: '}<Link to={`/lesson/${f.id}`}>{f.title}</Link></span>)}
            {n.status === 'gray' && !f && <>
              <span className="muted">New to you.</span>
              <button className="btn btn-small" onClick={() => dispatch({ type: 'makeFormulaLesson', conceptId, key: at.key })}>
                Make a lesson about this formula</button>
            </>}
          </div>
        )}
        {n.ideas.length > 0 && (
          <div className="formula-ideas small">
            <div className="eyebrow">Where you met it</div>
            {n.ideas.map(i => (
              <div key={i.id} className="row">
                <i className={`state-dot state-${i.state}`} />
                {i.here ? <span>{i.title} <span className="muted">(this lesson)</span></span>
                  : i.lesson ? <Link to={`/lesson/${i.lesson}`}>{i.title}</Link>
                    : <button className="link" onClick={() => navigate('/map', { state: { focus: 'all', select: i.id } })}>{i.title}</button>}
                <span className="muted">· {STATE[i.state] ?? i.state}</span>
              </div>
            ))}
          </div>
        )}
      </>}
    </div>
  )
}
