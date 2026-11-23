import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useStore } from '../store'
import { AddSources, EMPTY_QUERY, SourceFilter, SourcesTable, type SourceQuery } from '../components/Sources'
import type { SourceKind } from '../types'

/** Sources (SPEC §40): every PDF and link of the learner, with its type and status. */
export default function Library() {
  const { s, dispatch } = useStore()
  const [q, setQ] = useState<SourceQuery>(EMPTY_QUERY)
  const counts: Partial<Record<SourceKind, number>> = {}
  for (const x of s.sources) counts[x.kind] = (counts[x.kind] ?? 0) + 1
  return (
    <div className="page page-wide">
      <div className="row row-between">
        <div><div className="eyebrow">Library</div><h1>Sources</h1></div>
        <AddSources />
      </div>
      <p className="lead">Your books, articles, documents, web pages and videos. Click a title to open it. To study a book, use
        <Link to="/books"> Books</Link>.</p>
      <SourceFilter q={q} onChange={setQ} counts={counts} />

      {s.cardProposals.map(p => {
        const concept = s.concepts.find(c => c.id === p.conceptId)
        return (
          <div key={p.id} className="card card-warn">
            <div className="eyebrow">Proposed update · {concept?.title} · v{p.baseVersion} → v{p.baseVersion + 1}</div>
            <p>{p.summary}</p>
            <ul>{p.changes.map((c, i) => <li key={i}>{c}</li>)}</ul>
            <details>
              <summary>What changes</summary>
              <div className="diff-table">
                {p.diff.map((d, i) => (
                  <div key={i} className="diff-row">
                    <div className="diff-field">{d.field}</div>
                    <div className="diff-before">{d.before || '—'}</div>
                    <div className="diff-after">{d.after || '—'}</div>
                  </div>
                ))}
              </div>
            </details>
            <p className="muted small">Approving creates the next version of the card (fact-checked again); lessons built on it are re-rendered for you.</p>
            <div className="row">
              <button className="btn btn-primary" onClick={() => dispatch({ type: 'decideCardProposal', id: p.id, approve: true })}>Approve update</button>
              <button className="btn" onClick={() => dispatch({ type: 'decideCardProposal', id: p.id, approve: false })}>Keep current card</button>
            </div>
          </div>
        )
      })}

      <SourcesTable q={q} />
    </div>
  )
}
