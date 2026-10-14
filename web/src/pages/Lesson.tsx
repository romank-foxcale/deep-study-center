import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { isStale, useStore } from '../store'
import { tracks, vectorSections } from '../data/mock'
import type { Angle, LessonSection } from '../types'
import Markdown from '../components/Markdown'
import InlineCheck from '../components/InlineCheck'
import CodeExercise from '../components/CodeExercise'
import FeedbackDialog from '../components/FeedbackDialog'
import SidePanel, { SourceCardView, type Tab } from '../components/SidePanel'
import StateBadge, { MasteryBar } from '../components/StateBadge'

/** Prototype: only "Vectors" has full lesson sections; the backend renders the rest. */
const SECTIONS: Record<string, LessonSection[]> = { 'c-vectors': vectorSections }

const angleOf = (sec: LessonSection, chosen?: Angle): Angle => {
  const avail = Object.keys(sec.variants) as Angle[]
  return chosen && avail.includes(chosen) ? chosen : avail[0]
}

export default function Lesson() {
  const { id = '' } = useParams()
  const { s, dispatch } = useStore()
  const concept = s.concepts.find(c => c.id === id)
  const module = s.modules.find(m => m.id === concept?.moduleId)
  const track = tracks.find(t => t.id === module?.trackId)
  const card = s.cards.find(c => c.conceptId === id)
  const rendition = s.renditions.find(r => r.conceptId === id)
  const sections = SECTIONS[id] ?? []
  const stale = isStale(rendition, s)
  const studied = !!rendition?.studied || ['learned', 'mastered', 'rusty'].includes(concept?.state ?? '')

  const [tab, setTab] = useState<Tab>('tutor')
  const [draft, setDraft] = useState<{ tab: Tab; text: string; quote?: string } | null>(null)
  const clearDraft = useCallback(() => setDraft(null), [])
  const [feedbackFor, setFeedbackFor] = useState<{ sectionId?: string; label: string; angle?: Angle; available?: Angle[] } | null>(null)
  const [toast, setToast] = useState('')
  const [current, setCurrent] = useState<string | undefined>()
  const [selection, setSelection] = useState<{ text: string; top: number; left: number } | null>(null)
  const article = useRef<HTMLElement>(null)

  const refresh = useCallback(() => {
    dispatch({
      type: 'refresh', conceptId: id, sectionIds: sections.map(x => x.id),
      variants: Object.fromEntries(sections.map(x => [x.id, Object.keys(x.variants) as Angle[]])),
    })
  }, [dispatch, id, sections])

  // Not-yet-studied lessons are re-rendered when opened if the playbook or card changed.
  // Only on open: changes made while reading apply to the targeted section alone, so the
  // text doesn't shift under the learner.
  const openedFor = useRef<string | null>(null)
  useEffect(() => {
    if (openedFor.current === id) return
    openedFor.current = id
    if (stale && rendition && !studied && sections.length) {
      refresh()
      setToast(`Re-rendered for you with playbook v${s.playbook.version}.`)
    }
  }, [id, stale, studied, rendition, sections.length, refresh, s.playbook.version])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(''), 5000)
    return () => clearTimeout(t)
  }, [toast])

  useEffect(() => {
    const hide = () => setSelection(null)
    window.addEventListener('scroll', hide, true)
    return () => window.removeEventListener('scroll', hide, true)
  }, [])

  if (!concept) return <div className="page"><p>Lesson not found. <Link to="/roadmap">Back to the roadmap</Link></p></div>

  const onMouseUp = () => {
    const sel = window.getSelection()
    const text = sel?.toString().trim() ?? ''
    if (!sel || text.length < 3 || !article.current?.contains(sel.anchorNode)) { setSelection(null); return }
    const r = sel.getRangeAt(0).getBoundingClientRect()
    setSelection({ text: text.slice(0, 300), top: Math.max(8, r.top - 44), left: r.left + r.width / 2 })
  }

  const correct = Object.entries(s.answers).filter(([k, v]) => k.startsWith(id + ':') && v.correct).length
  const idx = s.concepts.findIndex(c => c.id === id)
  const nextConcept = s.concepts.slice(idx + 1).find(c => c.moduleId === concept.moduleId)

  return (
    <div className="lesson-layout">
      <article className="lesson" ref={article} onMouseUp={onMouseUp}>
        <div className="crumbs"><Link to="/roadmap">{track?.title}</Link> › {module?.title}</div>
        <header className="lesson-head">
          <h1>{concept.title}</h1>
          <p className="lead">{concept.objective}</p>
          <div className="row">
            <StateBadge state={concept.state} />
            <MasteryBar value={concept.mastery} />
            <span className="muted small">~{concept.minutes} min</span>
            {rendition && <span className="muted small">Rendered from card v{rendition.cardVersion} · playbook v{rendition.playbookVersion}</span>}
            <span className="spacer" />
            <button className="btn" onClick={() => setFeedbackFor({ label: 'this lesson' })}>Give feedback</button>
          </div>
        </header>

        {stale && studied && rendition && (
          <div className="banner">
            <span>Your playbook changed since you studied this (v{rendition.playbookVersion} → v{s.playbook.version}).</span>
            <button className="btn btn-primary" onClick={() => { refresh(); setToast('Refreshed for current you.') }}>Refresh for current me</button>
          </div>
        )}

        {sections.length === 0 && (
          <div className="placeholder">
            {card ? (
              <>
                <p><strong>Your version of this lesson hasn't been rendered yet.</strong> In the full app it's written for you from the source card below when you open the lesson. The prototype only has the full “Vectors” lesson.</p>
                <SourceCardView card={card} />
              </>
            ) : (
              <p><strong>Not researched yet.</strong> Deep research runs about one module ahead of you, so this lesson will be ready before you need it.</p>
            )}
          </div>
        )}

        {sections.map(sec => {
          const angle = angleOf(sec, rendition?.sectionAngles[sec.id])
          const multi = Object.keys(sec.variants).length > 1
          return (
            <section key={sec.id} className="lesson-section" onMouseEnter={() => setCurrent(sec.heading)}>
              <div className="section-head">
                <h2>{sec.heading}</h2>
                <div className="section-tools">
                  {multi && <span className="pill" title="Teaching angle used for this section">{angle}</span>}
                  {multi && (
                    <button className="btn btn-small" onClick={() => dispatch({ type: 'explainDifferently', conceptId: id, sectionId: sec.id, available: Object.keys(sec.variants) as Angle[] })}>
                      Explain differently
                    </button>
                  )}
                  <button className="btn btn-small" onClick={() => setFeedbackFor({ sectionId: sec.id, label: `“${sec.heading}”`, angle, available: Object.keys(sec.variants) as Angle[] })}>Feedback</button>
                </div>
              </div>
              <Markdown>{sec.variants[angle] ?? ''}</Markdown>
              {sec.check && (
                <InlineCheck key={sec.check.id} check={sec.check} previous={s.answers[`${id}:${sec.check.id}`]}
                  onAnswer={(choice, ok) => dispatch({ type: 'answer', conceptId: id, checkId: sec.check!.id, angle, choice, correct: ok })} />
              )}
              {sec.code && (
                <CodeExercise exercise={sec.code} passed={!!s.answers[`${id}:${sec.code.id}`]?.correct}
                  onResult={ok => dispatch({ type: 'answer', conceptId: id, checkId: sec.code!.id, angle, choice: ok ? 1 : 0, correct: ok })} />
              )}
            </section>
          )
        })}

        {sections.length > 0 && (
          <footer className="gate">
            <h3>Mastery</h3>
            <p className="muted">The engine decides, not a “mark complete” button: P(learned) ≥ 0.95 and at least 3 correct answers, then a spaced review confirms it.</p>
            <div className="row">
              <MasteryBar value={concept.mastery} /><span>P(learned) = {concept.mastery.toFixed(2)}</span>
              <span>· correct answers: {correct}/3</span>
              <StateBadge state={concept.state} />
            </div>
            <div className="row">
              {!studied && <button className="btn" onClick={() => dispatch({ type: 'markStudied', conceptId: id })}>I've read it</button>}
              {nextConcept && <Link className="btn btn-primary" to={`/lesson/${nextConcept.id}`}>Next: {nextConcept.title} →</Link>}
            </div>
          </footer>
        )}
      </article>

      <SidePanel conceptId={id} card={card} tab={tab} setTab={setTab} draft={draft} clearDraft={clearDraft} currentSection={current} />

      {selection && (
        <div className="sel-toolbar" style={{ top: selection.top, left: selection.left }} onMouseDown={e => e.preventDefault()}>
          <button onClick={() => { setTab('notes'); setDraft({ tab: 'notes', text: '', quote: selection.text }); setSelection(null) }}>Add note</button>
          <button onClick={() => { setTab('tutor'); setDraft({ tab: 'tutor', text: `About “${selection.text}”: ` }); setSelection(null) }}>Ask tutor</button>
        </div>
      )}

      {feedbackFor && (
        <FeedbackDialog target={feedbackFor.label} onClose={() => setFeedbackFor(null)}
          onSubmit={(tags, text) => {
            dispatch({ type: 'feedback', conceptId: id, sectionId: feedbackFor.sectionId, angle: feedbackFor.angle, available: feedbackFor.available, tags, text })
            setFeedbackFor(null); setTab('feedback')
          }} />
      )}

      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  )
}
