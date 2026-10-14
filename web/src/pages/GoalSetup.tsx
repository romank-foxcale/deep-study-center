import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { ChatMessage } from '../types'

const QUESTIONS = [
  "What's the ultimate goal? Dream big; we'll break it down together.",
  'What do you already know that’s related? (math, programming, ML, courses you took. Rough is fine.)',
  'Why do you want this, and what would “done” look like? A project, a role, a paper?',
  'How many hours a week can you give it, and is there a deadline?',
  'Tell me a bit about you so examples come from your world, and how you like to be taught (pictures or formulas first, questions or explanations first). Anything that never works for you?',
]

const PIPELINE = [
  'Researchers ×5 (practitioner, theorist, educator, recent learner, explainer-scout)',
  'Source curator: dropping paraphrases, keeping canonical sources',
  'Curriculum architect: tracks → modules → concepts',
  'Graph critic: prerequisite gaps, ordering, coverage',
  'Deep research for your first module',
]

export default function GoalSetup() {
  const [log, setLog] = useState<ChatMessage[]>([{ role: 'tutor', text: QUESTIONS[0] }])
  const [text, setText] = useState('')
  const [step, setStep] = useState(0)
  const [building, setBuilding] = useState(-1)
  const logRef = useRef<HTMLDivElement>(null)
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight }) }, [log.length, building])

  useEffect(() => {
    if (building < 0 || building >= PIPELINE.length) return
    const t = setTimeout(() => setBuilding(b => b + 1), 900)
    return () => clearTimeout(t)
  }, [building])

  const send = (answer = text) => {
    if (!answer.trim()) return
    const next = step + 1
    const reply = next < QUESTIONS.length ? QUESTIONS[next]
      : 'Thanks, that’s everything I need. I’ll research the field, keep only the best sources, and build your roadmap. You can change anything afterwards.'
    setLog(l => [...l, { role: 'me', text: answer }, { role: 'tutor', text: reply }])
    setText(''); setStep(next)
  }
  const doneAsking = step >= QUESTIONS.length

  return (
    <div className="page page-narrow">
      <h1>New goal</h1>
      <p className="lead">A short conversation, then agents research the field and build your roadmap. You can skip any question.</p>
      <div className="chat chat-page">
        <div className="chat-log" ref={logRef}>
          {log.map((m, i) => <div key={i} className={`msg ${m.role}`}>{m.text}</div>)}
          {building >= 0 && (
            <div className="pipeline">
              {PIPELINE.map((p, i) => (
                <div key={p} className={`pipe-step ${i < building ? 'done' : i === building ? 'active' : ''}`}>
                  <span className="pipe-dot" />{p}
                </div>
              ))}
              {building >= PIPELINE.length && (
                <p>Roadmap ready (the prototype shows the demo AI roadmap). <Link to="/roadmap" className="link">Open the roadmap →</Link></p>
              )}
            </div>
          )}
        </div>
        {!doneAsking ? (
          <div className="chat-input">
            <textarea className="input" rows={3} value={text} placeholder="Your answer…" onChange={e => setText(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
            <div className="col">
              <button className="btn btn-primary" onClick={() => send()}>Send</button>
              <button className="btn" onClick={() => send('(skipped)')}>Skip</button>
            </div>
          </div>
        ) : building < 0 && (
          <button className="btn btn-primary" onClick={() => setBuilding(0)}>Build my roadmap</button>
        )}
      </div>
    </div>
  )
}
