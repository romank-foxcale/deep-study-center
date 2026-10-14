import { Link } from 'react-router-dom'
import { useStore } from '../store'

export default function Library() {
  const { s } = useStore()
  return (
    <div className="page">
      <h1>Source library</h1>
      <p className="lead">Knowledge center #1: canonical, fact-checked concept cards, the same for every learner and reusable across goals. Cards change only when the content should, never because of taste.</p>
      <table className="table">
        <thead><tr><th>Concept</th><th>Version</th><th>Fact-check</th><th>Angles</th><th>Canonical sources</th></tr></thead>
        <tbody>
          {s.cards.map(c => {
            const concept = s.concepts.find(x => x.id === c.conceptId)
            return (
              <tr key={c.conceptId}>
                <td><Link to={`/lesson/${c.conceptId}`}>{concept?.title}</Link></td>
                <td>v{c.version}</td>
                <td><span className={`pill ${c.factCheck === 'passed' ? 'pill-ok' : 'pill-warn'}`}>{c.factCheck}</span></td>
                <td>{c.angles.map(a => a.label).join(', ')}</td>
                <td>{c.sources.map(src => <div key={src.url}><a href={src.url} target="_blank" rel="noreferrer">{src.title}</a></div>)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="muted small">{s.modules.reduce((n, m) => n + (m.research === 'ready' ? 0 : m.plannedConcepts ?? 0), 0)} more concepts are outlined and will get cards as you approach them.</p>
    </div>
  )
}
