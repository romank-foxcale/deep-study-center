import { useState, type DragEvent } from 'react'
import { useLocation } from 'react-router-dom'
import { useStore } from '../store'
import type { SourceDoc } from '../types'
import { AddSources, SourceStatus } from '../components/Sources'
import BuildProgress from '../components/BuildProgress'

const WHY = 'Why do you want to understand these sources? What should they give you (a decision, a skill, a talk, an exam)?'
const TIME = 'How many hours a week can you give it, and is there a deadline?'
const DRAG_TYPE = 'text/x-dsc-source'

/** Book goal (SPEC §18): the 80/20 core of one or more of the learner's sources, picked into a goal basket. */
export default function BookGoal() {
  const { s, dispatch } = useStore()
  const location = useLocation()
  const preset = ((location.state as { sourceIds?: string[] } | null)?.sourceIds ?? []).filter(id => s.sources.some(x => x.id === id))
  const [basket, setBasket] = useState<string[]>(preset)
  const [why, setWhy] = useState('')
  const [time, setTime] = useState('')
  const [layout, setLayout] = useState<'ohtani' | 'list'>('ohtani')
  const [over, setOver] = useState(false)
  const [submitted, setSubmitted] = useState<{ at: string; goalBefore?: string } | null>(null)

  const add = (id: string) => setBasket(b => b.includes(id) ? b : [...b, id])
  const remove = (id: string) => setBasket(b => b.filter(x => x !== id))
  const chosen = basket.map(id => s.sources.find(x => x.id === id)).filter((x): x is SourceDoc => !!x)
  const waiting = chosen.filter(x => x.status === 'reading')
  const unreadable = chosen.filter(x => x.status === 'no_text' || x.status === 'error')
  const canBuild = chosen.length > 0 && waiting.length === 0 && unreadable.length === 0
  const pages = chosen.reduce((n, x) => n + x.pages, 0)

  const drop = (e: DragEvent) => {
    e.preventDefault(); setOver(false)
    const id = e.dataTransfer.getData(DRAG_TYPE)
    if (id) add(id)
  }
  const build = () => {
    setSubmitted({ at: new Date().toISOString(), goalBefore: s.goal?.id })
    dispatch({ type: 'createGoal', kind: 'book', layout, sourceIds: basket,
      answers: [{ q: WHY, a: why.trim() || '(skipped)' }, { q: TIME, a: time.trim() || '(skipped)' }] })
  }

  if (submitted) {
    return (
      <div className="page page-narrow">
        <h1>Understand your sources</h1>
        <p className="lead">An agent ranks every chapter of {chosen.length === 1 ? `“${chosen[0].title}”` : `your ${chosen.length} sources`} by
          how much it carries, keeps the core and builds your roadmap from it. The roadmap lists what was left out; you can bring any
          of it back.</p>
        <BuildProgress since={submitted.at} goalBefore={submitted.goalBefore} />
      </div>
    )
  }

  return (
    <div className="page">
      <h1>Understand your sources</h1>
      <p className="lead">No time to read whole books? Pick one or more sources. You get the ~20% of each that carries ~80% of its value:
        its key concepts, arguments and frameworks, in the order that builds understanding, with lessons that cite the pages.</p>

      <div className="basket-wrap">
        <section className="card">
          <div className="row row-between">
            <h3 className="basket-title">Your sources</h3>
            <AddSources link={false} label="Add PDF" onAdded={ids => ids.forEach(add)} />
          </div>
          <p className="muted small">Tick a source, or drag it into the basket.</p>
          {s.sources.length === 0 && <p className="muted">No sources yet. Add a book, article or post as a PDF.</p>}
          <ul className="basket-list">
            {s.sources.map(src => (
              <li key={src.id} className={`basket-item ${basket.includes(src.id) ? 'in' : ''}`} draggable
                onDragStart={e => { e.dataTransfer.setData(DRAG_TYPE, src.id); e.dataTransfer.effectAllowed = 'copy' }}>
                <label>
                  <input type="checkbox" checked={basket.includes(src.id)} onChange={e => e.target.checked ? add(src.id) : remove(src.id)} />
                  <span>{src.title} <span className="muted small">{src.kind}{src.pages ? `, ${src.pages} pages` : ''}</span></span>
                </label>
                <SourceStatus src={src} />
              </li>
            ))}
          </ul>
        </section>

        <section className={`card basket ${over ? 'over' : ''}`} aria-label="Goal basket"
          onDragOver={e => { if (e.dataTransfer.types.includes(DRAG_TYPE)) { e.preventDefault(); setOver(true) } }}
          onDragLeave={() => setOver(false)} onDrop={drop}>
          <h3 className="basket-title">Goal basket</h3>
          {chosen.length === 0
            ? <p className="muted basket-empty">Drop sources here.</p>
            : (
              <>
                <ul className="basket-list">
                  {chosen.map(src => (
                    <li key={src.id} className="basket-item">
                      <span>{src.title} <span className="muted small">{src.pages ? `${src.pages} pages` : ''}</span></span>
                      <span className="row"><SourceStatus src={src} />
                        <button className="btn btn-small" aria-label={`Remove ${src.title}`} onClick={() => remove(src.id)}>Remove</button></span>
                    </li>
                  ))}
                </ul>
                <p className="muted small">{chosen.length} source{chosen.length > 1 ? 's' : ''}, {pages} pages.
                  {pages > 0 && ` The core is usually 20-30% of the pages.`}</p>
              </>
            )}
        </section>
      </div>

      <section className="card book-questions">
        <label className="field">
          <span>{WHY}</span>
          <textarea className="input" rows={2} value={why} onChange={e => setWhy(e.target.value)}
            placeholder="For example: I want to use its ideas in my product decisions" />
        </label>
        <label className="field">
          <span>{TIME}</span>
          <input className="input" value={time} onChange={e => setTime(e.target.value)} placeholder="For example: 3 hours a week, done by March" />
        </label>
        <p className="muted small">Your background and how you like to learn come from your earlier goals.</p>
        <div className="layout-pick">
          <fieldset>
            <legend className="small muted">Roadmap shape</legend>
            <label><input type="radio" name="layout" checked={layout === 'ohtani'} onChange={() => setLayout('ohtani')} />
              <span><strong>Ohtani table</strong> <span className="muted small">8 areas × 8 steps of the core ideas, plus 8 steps that merge
              neighbouring areas.</span></span></label>
            <label><input type="radio" name="layout" checked={layout === 'list'} onChange={() => setLayout('list')} />
              <span><strong>Classic roadmap</strong> <span className="muted small">Tracks of modules, sized to the core ideas. Smaller for one
              short book.</span></span></label>
          </fieldset>
          {waiting.length > 0 && <p className="muted small">Wait until {waiting.map(x => `“${x.title}”`).join(', ')} is read.</p>}
          {unreadable.length > 0 && <p className="error small">Remove {unreadable.map(x => `“${x.title}”`).join(', ')}: the app cannot read
            its text (a scan without a text layer, or a broken file).</p>}
          <button className="btn btn-primary" disabled={!canBuild} onClick={build}>
            {chosen.length === 0 ? 'Choose a source first' : 'Find the core and build my roadmap'}</button>
        </div>
      </section>
    </div>
  )
}
