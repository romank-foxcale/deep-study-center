import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { searchAll } from '../store'
import type { SearchHit } from '../types'

const KIND = { note: 'Your note', lesson: 'Lesson', card: 'Source card' }

/** Snippets come back with [[match]] markers; render them as <mark> without injecting HTML. */
function Snippet({ text }: { text: string }) {
  const plain = text.replace(/\*\*|__|`+|^#+\s*/gm, '')  // snippets are raw Markdown; drop the markup
  const parts = plain.split(/\[\[|\]\]/)
  return <span>{parts.map((p, i) => (i % 2 ? <mark key={i}>{p}</mark> : <span key={i}>{p}</span>))}</span>
}

export default function Search() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const [text, setText] = useState(q)
  const [hits, setHits] = useState<SearchHit[] | null>(null)
  useEffect(() => {
    setText(q)
    if (!q.trim()) { setHits(null); return }
    let live = true
    searchAll(q).then(h => live && setHits(h), () => live && setHits([]))
    return () => { live = false }
  }, [q])
  return (
    <div className="page page-narrow">
      <h1>Search</h1>
      <form className="row" onSubmit={e => { e.preventDefault(); setParams(text.trim() ? { q: text.trim() } : {}) }}>
        <input className="input search-input" type="search" value={text} onChange={e => setText(e.target.value)}
          placeholder="Search your notes, lessons and source cards" aria-label="Search" />
        <button className="btn btn-primary">Search</button>
      </form>
      {hits && hits.length === 0 && <p className="muted">No matches for “{q}”.</p>}
      {hits && hits.map((h, i) => (
        <Link key={i} to={`/lesson/${h.conceptId}`} className="card card-link search-hit">
          <div className="row row-between"><strong>{h.title}</strong><span className="pill">{KIND[h.kind]}</span></div>
          <p className="small"><Snippet text={h.snippet} /></p>
        </Link>
      ))}
    </div>
  )
}
