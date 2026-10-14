import { useState } from 'react'
import type { Answer, McqCheck } from '../types'
import Markdown from './Markdown'

interface Props {
  check: McqCheck
  previous?: Answer
  /** Graded on the server; the key arrives with `previous` once answered. */
  onAnswer: (choice: number) => void
  label?: string
}

export default function InlineCheck({ check, previous, onAnswer, label = 'Check yourself' }: Props) {
  const [choice, setChoice] = useState<number | null>(previous?.choice ?? null)
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
        <button className="btn btn-primary" disabled={choice === null} onClick={() => choice !== null && onAnswer(choice)}>
          Check answer
        </button>
      )}
      {done && (
        <div className={previous.correct ? 'check-result ok' : 'check-result bad'}>
          <strong>{previous.correct ? 'Correct.' : 'Not quite.'}</strong>{' '}
          {previous.explanation && <Markdown inline>{previous.explanation}</Markdown>}
        </div>
      )}
    </div>
  )
}
