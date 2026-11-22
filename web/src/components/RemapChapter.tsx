import { useState } from 'react'
import { useStore } from '../store'
import type { BookChapter } from '../types'

/** Map one chapter again (SPEC §31): its lessons and their written text are made anew; answers, notes and feedback stay.
 * A reference chapter (glossary, reading list) can be cut into lessons after all. Asks inside the page first. */
export default function RemapChapter({ bookId, ch, busy }: { bookId: string; ch: BookChapter; busy?: boolean }) {
  const { dispatch } = useStore()
  const [asking, setAsking] = useState(false)
  const reference = ch.kind === 'reference'
  if (busy || !ch.mapped) return null
  if (!asking) return (
    <button className="link small" onClick={() => setAsking(true)}
      title={reference ? 'Cut this reference chapter into lessons' : 'Cut this chapter into lessons again'}>
      {reference ? 'Make lessons from it' : 'Map this chapter again'}</button>
  )
  return (
    <span className="row small remap-ask">
      <span className="muted">{reference
        ? 'Cut this chapter into lessons? It is usually looked up, not studied.'
        : `Cut “${ch.title}” into lessons again? Its saved lessons are written again when you open them. Your answers, notes and feedback stay.`}</span>
      <button className="btn btn-small" onClick={async () => {
        setAsking(false)
        await dispatch({ type: 'bookRemapChapter', bookId, chapter: ch.chapter, asLessons: reference })
      }}>{reference ? 'Make lessons' : 'Map again'}</button>
      <button className="link small" onClick={() => setAsking(false)}>Cancel</button>
    </span>
  )
}
