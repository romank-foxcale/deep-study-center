import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useStore } from '../store'
import BookShelf from '../components/BookShelf'
import { AddSources, EMPTY_QUERY, SourceFilter, type SourceQuery } from '../components/Sources'

/** Books (SPEC §30, §40): your shelf. Pick a book and say "teach me this book". Search and filter by type. */
export default function Books() {
  const { s } = useStore()
  const [q, setQ] = useState<SourceQuery>(EMPTY_QUERY)
  const empty = s.studyBooks.length === 0 && s.sessions.length === 0 && s.sources.length === 0
  return (
    <div className="page">
      <div className="row row-between">
        <div><div className="eyebrow">Library</div><h1>Books</h1></div>
        <div className="row"><Link className="btn" to="/library">Manage sources</Link><AddSources /></div>
      </div>
      <p className="lead">Pick a book and say “teach me this book”. DSC reads it chapter by chapter, joins its ideas to what you already
        know, and cuts it into lessons by topic. Each lesson follows the book's pages and is saved, so you can read it again.</p>
      {empty
        ? <div className="card"><p>No books yet. Add a source to start.</p></div>
        : <><SourceFilter q={q} onChange={setQ} /><BookShelf q={q} /></>}
    </div>
  )
}
