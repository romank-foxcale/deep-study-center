import { useState } from 'react'
import type { Answer, McqCheck } from '../types'
import Markdown from './Markdown'
import ThinkingInput, { NO_REASONING, ReasoningShown, type Reasoning } from './ThinkingInput'
import ReasoningReview from './ReasoningReview'

interface Props {
  check: McqCheck
  previous?: Answer
  /** Graded on the server; the key arrives with `previous` once answered. */
  onAnswer: (choice: number, reasoning: Reasoning) => void
  /** Undo a mis-click: the answer is voided and the question can be answered again. */
  onUndo?: () => void
  /** Let the tutor read the thinking of this answer (when it has thinking and no review yet, or the review failed). */
  onReadReasoning?: () => void
  label?: string
}

export default function InlineCheck({ check, previous, onAnswer, onUndo, onReadReasoning, label = 'Check yourself' }: Props) {
  const [choice, setChoice] = useState<number | null>(previous?.choice ?? null)
  const [reasoning, setReasoning] = useState<Reasoning>(NO_REASONING)
  const done = previous !== undefined
  return (
    <div className="check">
      <div className="check-label">{label}</div>
      <Markdown>{check.prompt}</Markdown>
      <div className="check-options" role="radiogroup">
        {check.options.map((o, i) => {
          const cls = ['check-option']
          if (choice === i) cls.push('selected')
          if (done && i === previous.answer) cls.push('correct')
          if (done && previous.choice === i && !previous.correct) cls.push('wrong')
          return (
            <button key={i} className={cls.join(' ')} disabled={done} onClick={() => setChoice(i)} role="radio" aria-checked={choice === i}>
              <Markdown inline>{o}</Markdown>
            </button>
          )
        })}
      </div>
      {!done && (
        <>
          <ThinkingInput value={reasoning} onChange={setReasoning} />
          <button className="btn btn-primary" disabled={choice === null} onClick={() => choice !== null && onAnswer(choice, reasoning)}>
            Check answer
          </button>
        </>
      )}
      {done && (
        <div className={previous.correct ? 'check-result ok' : 'check-result bad'}>
          <strong>{previous.correct ? 'Correct.' : 'Not quite.'}</strong>{' '}
          {previous.correct && previous.score === 0.5 && <em>You marked it as a guess, so it counts as half. </em>}
          {previous.explanation && <Markdown inline>{previous.explanation}</Markdown>}
          {previous.review && previous.thinking
            ? <ReasoningReview review={previous.review} thinking={previous.thinking} confidence={previous.confidence} />
            : <ReasoningShown thinking={previous.thinking} confidence={previous.confidence} />}
          {onReadReasoning && (previous.thinking ?? '').trim().length >= 20 && (!previous.review || previous.review.status === 'failed') && (
            <div><button className="link small" onClick={onReadReasoning}>Let the tutor read my reasoning</button></div>
          )}
          {onUndo && <div><button className="link small" onClick={() => { setChoice(null); setReasoning(NO_REASONING); onUndo() }}>Undo this answer</button></div>}
        </div>
      )}
    </div>
  )
}
