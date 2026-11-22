import { Link } from 'react-router-dom'
import { useStore } from '../store'
import BookShelf from '../components/BookShelf'
import { AddSources } from '../components/Sources'

/** Books (SPEC §30): your shelf. Pick a book and say "teach me this book". */
export default function Books() {
  const { s } = useStore()
  return (
    <div className="page">
      <div className="row row-between">
        <div><div className="eyebrow">Library</div><h1>Books</h1></div>
        <div className="row"><Link className="btn" to="/library">Manage PDFs</Link><AddSources link={false} label="Add a PDF" /></div>
      </div>
      <p className="lead">Pick a book and say “teach me this book”. DSC reads it chapter by chapter, joins its ideas to what you already
        know, and teaches it one part at a time with the book's own pages.</p>
      {s.studyBooks.length === 0 && s.sources.every(x => x.status !== 'ready')
        ? <div className="card"><p>No books yet. Add a PDF to start.</p></div>
        : <BookShelf />}
    </div>
  )
}
