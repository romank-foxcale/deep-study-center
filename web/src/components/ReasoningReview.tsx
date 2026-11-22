import type { ReactNode } from 'react'
import type { ReasoningReview as Review } from '../types'
import Markdown from './Markdown'
import { confidenceLabel } from './ThinkingInput'

const VERDICT: Record<string, string> = {
  right: 'Your reasoning holds', right_with_gaps: 'Right answer, but a step is off', wrong: 'Where your reasoning went off',
  unclear: 'Your reasoning',
}
const MARK: Record<string, string> = { right: 'right', partly: 'partly right', wrong: 'wrong' }

/** Your thinking with the parts the tutor marked, numbered in place (green right, amber partly, red wrong). */
function Marked({ text, parts }: { text: string; parts: Review['parts'] }) {
  const hits: { at: number; end: number; n: number; mark: string }[] = []
  const low = text.toLowerCase()
  parts.forEach((p, n) => {
    const at = low.indexOf(p.quote.toLowerCase())
    if (at >= 0 && !hits.some(h => at < h.end && at + p.quote.length > h.at)) hits.push({ at, end: at + p.quote.length, n, mark: p.mark })
  })
  hits.sort((a, b) => a.at - b.at)
  const out: ReactNode[] = []
  let pos = 0
  for (const h of hits) {
    if (h.at > pos) out.push(text.slice(pos, h.at))
    out.push(<mark key={h.n} className={`rr-mark rr-${h.mark}`} title={MARK[h.mark]}>{text.slice(h.at, h.end)}<sup>{h.n + 1}</sup></mark>)
    pos = h.end
  }
  out.push(text.slice(pos))
  return <p className="rr-thinking">“{out}”</p>
}

/** The tutor's reading of your reasoning on one answer (SPEC §32): what is right or off in each part and why, the wrong
 * assumption, what would follow if it were true, and how it really works. */
export default function ReasoningReview({ review, thinking, confidence }: { review: Review; thinking: string; confidence?: number | null }) {
  const sure = confidence !== null && confidence !== undefined
    ? <span className="pill">{Math.round(confidence * 100)}% · {confidenceLabel(confidence)}</span> : null
  if (review.status === 'pending') return (
    <div className="rr small">{sure} <span className="muted">The tutor is reading your reasoning…</span>
      <p className="rr-thinking muted">“{thinking}”</p></div>
  )
  if (review.status === 'failed') return (
    <div className="rr small">{sure} <span className="muted">The tutor could not read your reasoning this time.</span>
      <p className="rr-thinking muted">“{thinking}”</p></div>
  )
  return (
    <div className={`rr rr-v-${review.verdict}`}>
      <div className="rr-head"><span className="eyebrow">{VERDICT[review.verdict] ?? 'Your reasoning'}</span>{sure}</div>
      {review.summary && <p className="rr-summary"><Markdown inline>{review.summary}</Markdown></p>}
      <Marked text={thinking} parts={review.parts} />
      {review.parts.length > 0 && (
        <ol className="rr-parts">
          {review.parts.map((p, i) => (
            <li key={i} className={`rr-part rr-part-${p.mark}`}>
              <span className={`pill small rr-pill-${p.mark}`}>{MARK[p.mark]}</span> <em>“{p.quote}”</em>
              <div><Markdown inline>{p.note}</Markdown></div>
            </li>
          ))}
        </ol>
      )}
      {review.assumption && (
        <div className="rr-block rr-assume">
          <div className="eyebrow">Your assumption</div>
          <Markdown>{review.assumption}</Markdown>
          {review.follow.length > 0 && <>
            <div className="eyebrow">If it worked your way</div>
            <ol className="rr-follow">{review.follow.map((f, i) => <li key={i}><Markdown inline>{f}</Markdown></li>)}</ol>
          </>}
        </div>
      )}
      {review.truth && (
        <div className="rr-block rr-truth">
          <div className="eyebrow">How it really works</div>
          <Markdown>{review.truth}</Markdown>
        </div>
      )}
      {review.takeaway && <p className="rr-takeaway"><strong>Remember:</strong> <Markdown inline>{review.takeaway}</Markdown></p>}
    </div>
  )
}
