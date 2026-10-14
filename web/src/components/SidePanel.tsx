import { useEffect, useRef, useState } from 'react'
import { jobActive, useStore } from '../store'
import type { SourceCard } from '../types'
import Markdown from './Markdown'

export type Tab = 'tutor' | 'notes' | 'source' | 'feedback'

interface Props {
  conceptId: string
  card?: SourceCard | null
  tab: Tab
  setTab: (t: Tab) => void
  draft: { tab: Tab; text: string; quote?: string } | null
  clearDraft: () => void
  currentSection?: string
}

export default function SidePanel({ conceptId, card, tab, setTab, draft, clearDraft, currentSection }: Props) {
  return (
    <aside className="side">
      <div className="tabs" role="tablist">
        {(['tutor', 'notes', 'source', 'feedback'] as Tab[]).map(t => (
          <button key={t} role="tab" aria-selected={tab === t} className={`tab ${tab === t ? 'on' : ''}`} onClick={() => setTab(t)}>
            {{ tutor: 'Tutor', notes: 'Notes', source: 'Source card', feedback: 'Feedback log' }[t]}
          </button>
        ))}
      </div>
      <div className="side-body">
        {tab === 'tutor' && <Tutor conceptId={conceptId} draft={draft?.tab === 'tutor' ? draft.text : ''} clearDraft={clearDraft} section={currentSection} />}
        {tab === 'notes' && <Notes conceptId={conceptId} quote={draft?.tab === 'notes' ? draft.quote : undefined} clearDraft={clearDraft} />}
        {tab === 'source' && <SourceCardView card={card} />}
        {tab === 'feedback' && <FeedbackLog conceptId={conceptId} />}
      </div>
    </aside>
  )
}

function Tutor({ conceptId, draft, clearDraft, section }: { conceptId: string; draft: string; clearDraft: () => void; section?: string }) {
  const { s, dispatch } = useStore()
  const [text, setText] = useState('')
  const thread = s.chats[conceptId] ?? []
  const thinking = jobActive(s, 'tutor', { concept_id: conceptId })
  const log = useRef<HTMLDivElement>(null)
  useEffect(() => { if (draft) { setText(draft); clearDraft() } }, [draft, clearDraft])
  // Scroll the log itself; scrollIntoView would also scroll the page.
  useEffect(() => { log.current?.scrollTo({ top: log.current.scrollHeight }) }, [thread.length, thinking])
  const send = () => {
    if (!text.trim()) return
    dispatch({ type: 'chat', conceptId, text, sectionHeading: section })
    setText('')
  }
  return (
    <div className="chat">
      <div className="chat-log" ref={log}>
        <div className="msg tutor">I know this lesson, your notes and how you like to learn. I'll guide you with questions and hints rather than hand you answers. Ask me anything.</div>
        {thread.map((m, i) => <div key={i} className={`msg ${m.role}`}>{m.role === 'tutor' ? <Markdown>{m.text}</Markdown> : m.text}</div>)}
        {thinking && <div className="msg tutor muted">Thinking…</div>}
      </div>
      <div className="chat-input">
        <textarea className="input" rows={3} value={text} placeholder="Ask the tutor…" onChange={e => setText(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
        <button className="btn btn-primary" onClick={send}>Send</button>
      </div>
      <p className="muted small">Runs on the provider set for “Tutor chat” in Settings.</p>
    </div>
  )
}

function Notes({ conceptId, quote, clearDraft }: { conceptId: string; quote?: string; clearDraft: () => void }) {
  const { s, dispatch } = useStore()
  const [text, setText] = useState('')
  const [q, setQ] = useState<string | undefined>()
  useEffect(() => { if (quote) { setQ(quote); clearDraft() } }, [quote, clearDraft])
  const notes = s.notes.filter(n => n.conceptId === conceptId)
  const add = () => {
    if (!text.trim()) return
    dispatch({ type: 'addNote', conceptId, text, quote: q })
    setText(''); setQ(undefined)
  }
  return (
    <div className="notes">
      {q && <blockquote className="quote">“{q}” <button className="link" onClick={() => setQ(undefined)}>remove</button></blockquote>}
      <textarea className="input" rows={4} value={text} placeholder="Write a note (Markdown and $math$ work)… Tip: select text in the lesson to quote it."
        onChange={e => setText(e.target.value)} />
      <button className="btn btn-primary" onClick={add} disabled={!text.trim()}>Save note</button>
      <div className="note-list">
        {notes.length === 0 && <p className="muted">No notes yet. The tutor can read your notes, and they're searchable across all lessons.</p>}
        {notes.map(n => (
          <div key={n.id} className="note">
            {n.quote && <blockquote className="quote">“{n.quote}”</blockquote>}
            <Markdown>{n.text}</Markdown>
            <div className="row row-between">
              <span className="muted small">{new Date(n.ts).toLocaleString()}</span>
              <button className="link" onClick={() => dispatch({ type: 'deleteNote', id: n.id })}>Delete</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function SourceCardView({ card }: { card?: SourceCard | null }) {
  if (!card) return <p className="muted">No source card yet. Research runs about one module ahead of you.</p>
  return (
    <div className="card-view">
      <p className="muted small">
        Knowledge center #1: the canonical material, the same for every learner. Your lesson is rendered from this.
      </p>
      <div className="row">
        <span className="pill">v{card.version}</span>
        <span className={`pill ${card.factCheck === 'passed' ? 'pill-ok' : 'pill-warn'}`}>fact-check: {card.factCheck}</span>
        <span className="pill">Bloom: {card.bloom}</span>
      </div>
      {card.factIssues && card.factIssues.length > 0 && (
        <div className="banner"><span>Fact-check notes: {card.factIssues.join(' · ')}</span></div>
      )}
      <h4>Core idea</h4><Markdown>{card.core}</Markdown>
      <h4>Formal</h4><Markdown>{card.formal}</Markdown>
      <h4>Why it works</h4><Markdown>{card.why}</Markdown>
      <h4>Angles</h4>
      <ul>{card.angles.map(a => <li key={a.id}><strong>{a.label}</strong>: {a.summary}</li>)}</ul>
      <h4>Example bank</h4>
      <ul>{card.examples.map(e => <li key={e.label}>{e.label} <span className="muted">· {e.domain}</span></li>)}</ul>
      <h4>Misconceptions</h4>
      <ul>{card.misconceptions.map(m => <li key={m}>{m}</li>)}</ul>
      <h4>Canonical sources</h4>
      <ul className="sources">
        {card.sources.map(src => (
          <li key={src.url}><a href={src.url} target="_blank" rel="noreferrer">{src.title}</a> <span className="pill">{src.kind}</span><div className="muted small">{src.why}</div></li>
        ))}
      </ul>
    </div>
  )
}

function FeedbackLog({ conceptId }: { conceptId: string }) {
  const { s } = useStore()
  const items = s.feedback.filter(f => f.conceptId === conceptId)
  if (!items.length) return <p className="muted">No feedback on this lesson yet. Use “Give feedback” any time, even before you've answered anything.</p>
  return <FeedbackList items={items} />
}

export function FeedbackList({ items }: { items: ReturnType<typeof useStore>['s']['feedback'] }) {
  return (
    <div className="fb-list">
      {items.map(f => (
        <div key={f.id} className="fb">
          <div className="row row-between">
            <span>{f.tags.join(' · ') || 'Comment'}</span>
            <span className="muted small">{new Date(f.ts).toLocaleString()}</span>
          </div>
          {f.text && <p className="fb-text">“{f.text}”</p>}
          <ul className="effects">{f.effects.map((e, i) => <li key={i}>{e}</li>)}</ul>
        </div>
      ))}
    </div>
  )
}
