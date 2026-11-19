import { Link } from 'react-router-dom'
import { useStore } from '../store'
import type { BookCut } from '../types'

const RANK = { core: 'core', supporting: 'supporting', skip: 'left out' }

/** A book goal's 80/20 cut: what each source contributes, and what was left out (with "Bring back"). */
export default function BookCuts() {
  const { s, dispatch } = useStore()
  if (s.goal?.kind !== 'book' || s.bookCuts.length === 0) return null
  const step = (c: BookCut) => s.modules.find(m => m.id === c.moduleId)?.title
  const cut = s.bookCuts.filter(c => c.status === 'cut')
  const kept = s.bookCuts.filter(c => c.status !== 'cut')
  const bySource = (items: BookCut[]) => [...new Set(items.map(c => c.sourceTitle))].map(t => ({ title: t, items: items.filter(c => c.sourceTitle === t) }))
  return (
    <section className="card">
      <div className="eyebrow">The 80/20 cut</div>
      <p className="muted small">An agent ranked every chapter of your sources. Your roadmap teaches only the core and supporting
        chapters. {cut.length > 0 ? `${cut.length} chapter${cut.length > 1 ? 's were' : ' was'} left out; bring one back if you need it.` : ''}</p>
      <div className="grid-2">
        <div>
          <h4>Left out ({cut.length})</h4>
          {cut.length === 0 && <p className="muted small">Nothing left out.</p>}
          {bySource(cut).map(g => (
            <div key={g.title}>
              <div className="small"><strong>{g.title}</strong></div>
              <ul className="cut-list">
                {g.items.map(c => (
                  <li key={c.id} className="cut-item">
                    <span>{c.chapter}{c.pages && <span className="muted small"> · pp. {c.pages}</span>}
                      <div className="muted small">{c.why}</div></span>
                    <button className="btn btn-small" title={step(c) ? `Adds it to “${step(c)}”` : undefined}
                      onClick={() => dispatch({ type: 'restoreCut', id: c.id })}>Bring back</button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div>
          <h4>Kept ({kept.length})</h4>
          {bySource(kept).map(g => (
            <details key={g.title} open={kept.length <= 12}>
              <summary className="small"><strong>{g.title}</strong> <span className="muted">({g.items.length})</span></summary>
              <ul className="cut-list">
                {g.items.map(c => (
                  <li key={c.id}>
                    {c.chapter}{c.pages && <span className="muted small"> · pp. {c.pages}</span>}{' '}
                    <span className={`pill ${c.rank === 'core' ? 'pill-ok' : ''}`}>{c.status === 'restored' ? 'brought back' : RANK[c.rank]}</span>
                    {step(c) && <span className="muted small"> → {c.conceptId
                      ? <Link to={`/lesson/${c.conceptId}`}>{step(c)}</Link> : step(c)}</span>}
                    <div className="muted small">{c.why}</div>
                  </li>
                ))}
              </ul>
            </details>
          ))}
        </div>
      </div>
    </section>
  )
}
