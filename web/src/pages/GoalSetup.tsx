import { useEffect, useRef, useState } from 'react'
import { useStore } from '../store'
import type { ChatMessage } from '../types'
import { AddSources, SourceStatus } from '../components/Sources'
import BuildProgress from '../components/BuildProgress'

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
  const [layout, setLayout] = useState<'ohtani' | 'list'>('ohtani')
  const [picked, setPicked] = useState<string[]>([])
  const logRef = useRef<HTMLDivElement>(null)
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight }) }, [log.length, s.jobs])

  const send = (answer = text) => {
    if (!answer.trim()) return
    const next = answers.length + 1
    const reply = next < QUESTIONS.length ? QUESTIONS[next]
      : 'Thanks, that’s everything I need. Choose the shape of your roadmap below. I’ll research the field, keep only the best sources, and build it. You can change anything afterwards.'
    setLog(l => [...l, { role: 'me', text: answer }, { role: 'tutor', text: reply }])
    setAnswers(a => [...a, answer]); setText('')
  }
  const doneAsking = answers.length >= QUESTIONS.length

  const build = () => {
    setSubmitted({ at: new Date().toISOString(), goalBefore: s.goal?.id })
    dispatch({ type: 'createGoal', layout, sourceIds: picked, answers: QUESTIONS.map((q, i) => ({ q, a: answers[i] ?? '' })) })
  }

  return (
    <div className="page page-narrow">
      <h1>New goal</h1>
      <p className="lead">A short conversation, then agents research the field and build your roadmap. You can skip any question.</p>
      <div className="chat chat-page">
        <div className="chat-log" ref={logRef}>
          {log.map((m, i) => <div key={i} className={`msg ${m.role}`}>{m.text}</div>)}
          {submitted && <BuildProgress since={submitted.at} goalBefore={submitted.goalBefore} />}
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
          <div className="layout-pick">
            <fieldset>
              <legend className="small muted">Roadmap shape</legend>
              <label><input type="radio" name="layout" checked={layout === 'ohtani'} onChange={() => setLayout('ohtani')} />
                <span><strong>Ohtani table</strong> <span className="muted small">8 areas × 8 steps around your goal, plus 8 steps that
                merge neighbouring areas. A grid you fill as you learn.</span></span></label>
              <label><input type="radio" name="layout" checked={layout === 'list'} onChange={() => setLayout('list')} />
                <span><strong>Classic roadmap</strong> <span className="muted small">3–7 tracks of modules, sized to the goal.</span></span></label>
            </fieldset>
            <fieldset>
              <legend className="small muted">Your own sources (optional)</legend>
              <p className="muted small">Books, articles or posts as PDF. The roadmap follows their chapters, and lessons cite their pages.</p>
              {s.sources.map(src => (
                <label key={src.id}>
                  <input type="checkbox" checked={picked.includes(src.id)}
                    onChange={e => setPicked(p => e.target.checked ? [...p, src.id] : p.filter(x => x !== src.id))} />
                  <span>{src.title} <span className="muted small">{src.kind}{src.pages ? `, ${src.pages} pages` : ''}</span> <SourceStatus src={src} /></span>
                </label>
              ))}
              <AddSources link={false} label="Add PDF" onAdded={ids => setPicked(p => [...p, ...ids])} />
            </fieldset>
            <button className="btn btn-primary" onClick={build}>{layout === 'ohtani' ? 'Build my Ohtani table' : 'Build my roadmap'}</button>
          </div>
        )}
      </div>
    </div>
  )
}
