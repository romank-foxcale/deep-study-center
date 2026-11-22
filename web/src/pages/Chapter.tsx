import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getBook, useStore } from '../store'
import Markdown from '../components/Markdown'
import type { BookView } from '../types'
import { KNOWN, LessonList, pageRange } from './Book'

/** One chapter of a book (SPEC §31): its summary and its lessons by topic, with what each covers. */
export default function Chapter() {
  const { id = '', n = '1' } = useParams()
  const { s, dispatch } = useStore()
  const navigate = useNavigate()
  const [v, setV] = useState<BookView | null>(null)
  const [missing, setMissing] = useState(false)
  const [going, setGoing] = useState<string | null | undefined>(undefined)

  useEffect(() => { getBook(id).then(setV, () => setMissing(true)) }, [id, s])
  useEffect(() => {
    if (going !== undefined && s.lastPractice && s.lastPractice !== going) navigate(`/practice/${s.lastPractice}`)
  }, [s.lastPractice, going, navigate])

  if (missing) return <div className="page"><p>Book not found. <Link to="/books">Back to Books</Link></p></div>
  if (!v) return <div className="page"><p className="muted">Loading…</p></div>
  const ch = v.chapters.find(c => c.chapter === Number(n))
  if (!ch) return <div className="page"><p>Chapter not found. <Link to={`/book/${v.id}`}>Back to the book</Link></p></div>
  const prev = v.chapters.find(c => c.chapter === ch.chapter - 1)
  const nextCh = v.chapters.find(c => c.chapter === ch.chapter + 1)
  const known = ch.lessons.filter(x => KNOWN.has(x.state)).length
  const first = ch.lessons.find(x => x.conceptId === v.next) ?? ch.lessons.find(x => !KNOWN.has(x.state)) ?? ch.lessons[0]

  return (
    <div className="page chapter">
      <div className="eyebrow"><Link to="/books">Books</Link> › <Link to={`/book/${v.id}`}>{v.title}</Link></div>
      <h1>{ch.title}</h1>
      <div className="row small muted">
        <span>pp. {pageRange(ch.pages)}</span>
        <span>{ch.lessons.length} lessons</span>
        <span><b className="text">{known}</b> known</span>
      </div>
      {ch.summary && <div className="card chapter-summary"><div className="eyebrow">The chapter in short</div><Markdown>{ch.summary}</Markdown></div>}
      {!ch.mapped && <p className="muted">This chapter is not cut into lessons yet: the book is still being mapped.</p>}
      {ch.writing && <p className="muted">Writing this chapter's lessons from the book's pages…</p>}
      <LessonList lessons={ch.lessons} next={v.next} full />
      <div className="row">
        {first && <Link className="btn btn-primary" to={`/lesson/${first.conceptId}`}>{KNOWN.has(first.state) ? 'Read it again' : first.started ? 'Continue' : 'Start the chapter'}</Link>}
        {known > 0 && <button className="btn" onClick={() => { setGoing(s.lastPractice); void dispatch({ type: 'bookHomework', bookId: v.id, chapter: ch.chapter }) }}
          title="Recall practice on this chapter's lessons">Homework</button>}
        <span className="spacer" />
        {prev && <Link className="btn" to={`/book/${v.id}/chapter/${prev.chapter}`}>← {prev.title}</Link>}
        {nextCh && <Link className="btn" to={`/book/${v.id}/chapter/${nextCh.chapter}`}>{nextCh.title} →</Link>}
      </div>
    </div>
  )
}
