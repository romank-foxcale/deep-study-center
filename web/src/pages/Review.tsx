import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useStore } from '../store'
import InlineCheck from '../components/InlineCheck'

/** Spaced reviews: one check per due concept, graded by the engine, scheduled by FSRS. */
export default function Review() {
  const { s, dispatch } = useStore()
  const due = s.reviews.filter(r => r.isDue)
  // Pick one check per concept, rotating by day so reviews aren't the same question every time.
  const items = useMemo(() => due.map(r => {
    const card = s.cards.find(c => c.conceptId === r.conceptId)
    const checks = (card?.sections ?? []).flatMap(sec => sec.check ? [sec.check] : [])
    const day = Math.floor(Date.now() / 86_400_000)
    return { review: r, check: checks.length ? checks[day % checks.length] : null }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keep the question stable while answering
  }), [due.map(r => r.conceptId).join()])

  return (
    <div className="page page-narrow">
      <h1>Reviews</h1>
      <p className="lead">Recall from memory, no peeking. Passing a review a day after learning confirms mastery; FSRS spaces the next one.</p>
      {items.length === 0 && <p className="muted">Nothing due. <Link to="/">Back home</Link></p>}
      {items.map(({ review, check }) => {
        const concept = s.concepts.find(c => c.id === review.conceptId)
        return (
          <div key={review.conceptId} className="card">
            <h3>{concept?.title}</h3>
            {check
              ? <InlineCheck check={check} label="Review" onAnswer={choice => dispatch({ type: 'review', conceptId: review.conceptId, checkId: check.id, choice })} />
              : <p className="muted">This card has no review question yet.</p>}
          </div>
        )
      })}
    </div>
  )
}
