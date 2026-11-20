import { useState } from 'react'
import type { Answer, McqCheck } from '../types'
import Markdown from './Markdown'
import ThinkingInput, { NO_REASONING, ReasoningShown, type Reasoning } from './ThinkingInput'

interface Props {
  check: McqCheck
  previous?: Answer
  /** Graded on the server; the key arrives with `previous` once answered. */
  onAnswer: (choice: number, reasoning: Reasoning) => void
  /** Undo a mis-click: the answer is voided and the question can be answered again. */
  onUndo?: () => void
  label?: string
}

export default function InlineCheck({ check, previous, onAnswer, onUndo, label = 'Check yourself' }: Props) {
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
          <ReasoningShown thinking={previous.thinking} confidence={previous.confidence} />
          {onUndo && <div><button className="link small" onClick={() => { setChoice(null); setReasoning(NO_REASONING); onUndo() }}>Undo this answer</button></div>}
        </div>
      )}
    </div>
  )
}
