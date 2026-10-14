import { useState } from 'react'
import type { McqCheck } from '../types'
import Markdown from './Markdown'

interface Props {
  check: McqCheck
  previous?: { choice: number; correct: boolean }
  onAnswer: (choice: number, correct: boolean) => void
}

export default function InlineCheck({ check, previous, onAnswer }: Props) {
  const [choice, setChoice] = useState<number | null>(previous?.choice ?? null)
  const done = previous !== undefined
  return (
    <div className="check">
      <div className="check-label">Check yourself</div>
      <Markdown>{check.prompt}</Markdown>
      <div className="check-options" role="radiogroup">
        {check.options.map((o, i) => {
          const cls = ['check-option']
          if (choice === i) cls.push('selected')
          if (done && i === check.answer) cls.push('correct')
          if (done && choice === i && i !== check.answer) cls.push('wrong')
          return (
            <button key={i} className={cls.join(' ')} disabled={done} onClick={() => setChoice(i)} role="radio" aria-checked={choice === i}>
              <Markdown inline>{o}</Markdown>
            </button>
          )
        })}
      </div>
      {!done && (
        <button className="btn btn-primary" disabled={choice === null} onClick={() => choice !== null && onAnswer(choice, choice === check.answer)}>
          Check answer
        </button>
      )}
      {done && (
        <div className={previous!.correct ? 'check-result ok' : 'check-result bad'}>
          <strong>{previous!.correct ? 'Correct.' : 'Not quite.'}</strong> <Markdown inline>{check.explanation}</Markdown>
        </div>
      )}
    </div>
  )
}
