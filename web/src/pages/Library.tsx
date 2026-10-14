import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useStore } from '../store'

export default function Library() {
  const { s, dispatch } = useStore()
  const [tab, setTab] = useState<'goal' | 'shared'>('goal')
  const shared = new Set(s.library.map(l => l.sourceConcept))
  const exported = s.ankiExport?.split('|')
  return (
    <div className="page">
      <h1>Source library</h1>
      <p className="lead">Knowledge center #1: canonical, fact-checked concept cards, the same for every learner. Cards change only when
        the content should, never because of taste. Good cards can go into a shared library that research reuses across goals.</p>
      <div className="row">
        <div className="tabs tabs-inline" role="tablist">
          <button role="tab" aria-selected={tab === 'goal'} className={`tab ${tab === 'goal' ? 'on' : ''}`} onClick={() => setTab('goal')}>This goal ({s.cards.length})</button>
          <button role="tab" aria-selected={tab === 'shared'} className={`tab ${tab === 'shared' ? 'on' : ''}`} onClick={() => setTab('shared')}>Shared library ({s.library.length})</button>
        </div>
        <span className="spacer" />
        <a className="btn" href="/api/export/anki" download>Export Anki deck</a>
        {exported && <span className="muted small">last export: {exported[1]} cards, {new Date(exported[0]).toLocaleDateString()}</span>}
      </div>
      <p className="muted small">The Anki deck holds the questions and explain-back prompts of the concepts you've learned.</p>

      {tab === 'goal' && (
        <table className="table">
          <thead><tr><th>Concept</th><th>Version</th><th>Fact-check</th><th>Canonical sources</th><th /></tr></thead>
          <tbody>
            {s.cards.map(c => {
              const concept = s.concepts.find(x => x.id === c.conceptId)
              return (
                <tr key={c.conceptId}>
                  <td><Link to={`/lesson/${c.conceptId}`}>{concept?.title}</Link></td>
                  <td>v{c.version}</td>
                  <td><span className={`pill ${c.factCheck === 'passed' ? 'pill-ok' : 'pill-warn'}`}>{c.factCheck}</span></td>
                  <td>{c.sources.map(src => <div key={src.url}><a href={src.url} target="_blank" rel="noreferrer">{src.title}</a></div>)}</td>
                  <td>
                    {shared.has(c.conceptId)
                      ? <span className="pill pill-ok">shared</span>
                      : <button className="btn btn-small" disabled={c.factCheck !== 'passed'}
                          title={c.factCheck !== 'passed' ? 'Only fact-checked cards can be shared' : undefined}
                          onClick={() => dispatch({ type: 'promoteCard', conceptId: c.conceptId })}>Add to shared library</button>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      {tab === 'shared' && (s.library.length === 0
        ? <p className="muted">Nothing shared yet. Add fact-checked cards from “This goal”; research for any goal reuses them instead of rewriting.</p>
        : (
          <table className="table">
            <thead><tr><th>Concept</th><th>Objective</th><th>Version</th><th>Reused</th></tr></thead>
            <tbody>{s.library.map(l => (
              <tr key={l.key}><td>{l.title}</td><td className="small">{l.objective}</td><td>v{l.version}</td><td>{l.uses}×</td></tr>
            ))}</tbody>
          </table>
        ))}
      <p className="muted small">{s.modules.reduce((n, m) => n + (m.research === 'ready' ? 0 : m.plannedConcepts ?? 0), 0)} more concepts are outlined and will get cards as you approach them.</p>
    </div>
  )
}
