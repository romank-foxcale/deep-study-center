import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useStore } from '../store'
import type { ChatMessage } from '../types'

const QUESTIONS = [
  "What's the ultimate goal? Dream big; we'll break it down together.",
  'What do you already know that’s related? (math, programming, ML, courses you took. Rough is fine.)',
  'Why do you want this, and what would “done” look like? A project, a role, a paper?',
  'How many hours a week can you give it, and is there a deadline?',
  'Tell me a bit about you so examples come from your world, and how you like to be taught (pictures or formulas first, questions or explanations first). Anything that never works for you?',
]

export default function GoalSetup() {
  const { s, dispatch } = useStore()
  const [log, setLog] = useState<ChatMessage[]>([{ role: 'tutor', text: QUESTIONS[0] }])
  const [answers, setAnswers] = useState<string[]>([])
  const [text, setText] = useState('')
  const [submitted, setSubmitted] = useState<{ at: string; goalBefore?: string } | null>(null)
  const logRef = useRef<HTMLDivElement>(null)
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight }) }, [log.length, s.jobs])

  const send = (answer = text) => {
    if (!answer.trim()) return
    const next = answers.length + 1
    const reply = next < QUESTIONS.length ? QUESTIONS[next]
      : 'Thanks, that’s everything I need. I’ll research the field, keep only the best sources, and build your roadmap. You can change anything afterwards.'
    setLog(l => [...l, { role: 'me', text: answer }, { role: 'tutor', text: reply }])
    setAnswers(a => [...a, answer]); setText('')
  }
  const doneAsking = answers.length >= QUESTIONS.length

  const build = () => {
    setSubmitted({ at: new Date().toISOString(), goalBefore: s.goal?.id })
    dispatch({ type: 'createGoal', answers: QUESTIONS.map((q, i) => ({ q, a: answers[i] ?? '' })) })
  }

  const jobs = submitted
    ? s.jobs.filter(j => ['outline', 'research_module', 'fact_check', 'placement_bank'].includes(j.kind) && j.updatedAt >= submitted.at.slice(0, 19))
    : []
  const created = submitted && s.goal && s.goal.id !== submitted.goalBefore

  return (
    <div className="page page-narrow">
      <h1>New goal</h1>
      <p className="lead">A short conversation, then agents research the field and build your roadmap. You can skip any question.</p>
      <div className="chat chat-page">
        <div className="chat-log" ref={logRef}>
          {log.map((m, i) => <div key={i} className={`msg ${m.role}`}>{m.text}</div>)}
          {submitted && (
            <div className="pipeline">
              {jobs.length === 0 && <div className="pipe-step active"><span className="pipe-dot" />Starting…</div>}
              {[...jobs].reverse().map(j => (
                <div key={j.id} className={`pipe-step ${j.status === 'done' ? 'done' : j.status === 'failed' ? 'failed' : 'active'}`}>
                  <span className="pipe-dot" />
                  <span>{j.label}{j.status === 'failed' ? `: failed (${j.error})` : ''}
                    {j.progress.length > 0 && j.status !== 'failed' && <span className="muted small"> · {j.progress.slice(-1)[0]}</span>}</span>
                </div>
              ))}
              {created && <p>Your roadmap is ready. <Link to="/placement" className="link">Take the placement quiz →</Link> to skip
                what you already know, or <Link to="/roadmap" className="link">open the roadmap</Link>. The first module's lessons appear
                when its research finishes.</p>}
            </div>
          )}
        </div>
        {!doneAsking ? (
          <div className="chat-input">
            <textarea className="input" rows={3} value={text} placeholder="Your answer…" onChange={e => setText(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
            <div className="col">
              <button className="btn btn-primary" onClick={() => send()}>Send</button>
              {answers.length > 0 && <button className="btn" onClick={() => send('(skipped)')}>Skip</button>}
            </div>
          </div>
        ) : !submitted && (
          <button className="btn btn-primary" onClick={build}>Build my roadmap</button>
        )}
      </div>
    </div>
  )
}
