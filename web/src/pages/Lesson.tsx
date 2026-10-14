import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getLesson, openLesson, useStore } from '../store'
import type { Angle, LessonView } from '../types'
import Markdown from '../components/Markdown'
import InlineCheck from '../components/InlineCheck'
import CodeExercise from '../components/CodeExercise'
import FeedbackDialog from '../components/FeedbackDialog'
import SidePanel, { SourceCardView, type Tab } from '../components/SidePanel'
import StateBadge, { MasteryBar } from '../components/StateBadge'

export default function Lesson() {
  const { id = '' } = useParams()
  const { s, dispatch, reload } = useStore()
  const concept = s.concepts.find(c => c.id === id)
  const module = s.modules.find(m => m.id === concept?.moduleId)
  const track = s.tracks.find(t => t.id === module?.trackId)

  const [view, setView] = useState<LessonView | null>(null)
  const [loadError, setLoadError] = useState('')
  const [tab, setTab] = useState<Tab>('tutor')
  const [draft, setDraft] = useState<{ tab: Tab; text: string; quote?: string } | null>(null)
  const clearDraft = useCallback(() => setDraft(null), [])
  const [feedbackFor, setFeedbackFor] = useState<{ sectionId?: string; label: string; angle?: Angle; available?: Angle[] } | null>(null)
  const [toast, setToast] = useState('')
  const [current, setCurrent] = useState<string | undefined>()
  const [selection, setSelection] = useState<{ text: string; top: number; left: number } | null>(null)
  const article = useRef<HTMLElement>(null)

  // Opening the lesson applies playbook changes (re-renders if it isn't studied yet).
  useEffect(() => {
    let live = true
    setView(null)
    openLesson(id).then(v => {
      if (!live) return
      setView(v)
      if (v.rendering) reload()
      if (v.refreshed) setToast(`Re-rendered for you with playbook v${s.playbook.version}.`)
    }, e => live && setLoadError((e as Error).message))
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only on open
  }, [id])

  // Every new snapshot (after an action or a poll while jobs run) re-reads the lesson.
  useEffect(() => {
    let live = true
    if (view) getLesson(id).then(v => live && setView(v), () => {})
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed on the snapshot
  }, [s])

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

  const sections = view?.sections ?? []
  const rendition = view?.rendition
  const correct = Object.entries(s.answers).filter(([k, v]) => k.startsWith(id + ':') && v.correct).length
  const siblings = s.concepts.filter(c => c.moduleId === concept.moduleId)
  const nextConcept = siblings[siblings.findIndex(c => c.id === id) + 1]

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

        {loadError && <p className="error">{loadError}</p>}
        {!view && !loadError && <p className="muted">Opening…</p>}

        {rendition?.stale && rendition.studied && (
          <div className="banner">
            <span>Your playbook changed since you studied this (v{rendition.playbookVersion} → v{s.playbook.version}).</span>
            <button className="btn btn-primary" onClick={() => { dispatch({ type: 'refresh', conceptId: id }); setToast('Refreshing for current you…') }}>Refresh for current me</button>
          </div>
        )}
        {view?.renderError && (
          <div className="banner banner-bad">
            <span>Couldn't render this lesson: {view.renderError}</span>
            <button className="btn" onClick={() => dispatch({ type: 'refresh', conceptId: id })}>Try again</button>
          </div>
        )}

        {view && !view.card && (
          <div className="placeholder">
            <p><strong>Not researched yet.</strong> Deep research runs about one module ahead of you.</p>
            {module && module.research !== 'researching' && (
              <button className="btn btn-primary" onClick={() => dispatch({ type: 'researchModule', moduleId: module.id })}>Research this module now</button>
            )}
            {module?.research === 'researching' && <p className="muted">Researching this module…</p>}
          </div>
        )}
        {view?.card && sections.length === 0 && <SourceCardView card={view.card} />}

        {sections.map(sec => {
          const multi = sec.angles.length > 1
          return (
            <section key={sec.id} className="lesson-section" onMouseEnter={() => setCurrent(sec.heading)}>
              <div className="section-head">
                <h2>{sec.heading}</h2>
                <div className="section-tools">
                  {multi && <span className="pill" title="Teaching angle used for this section">{sec.angle}</span>}
                  {multi && (
                    <button className="btn btn-small" disabled={sec.pending}
                      onClick={() => dispatch({ type: 'explainDifferently', conceptId: id, sectionId: sec.id })}>
                      Explain differently
                    </button>
                  )}
                  <button className="btn btn-small" onClick={() => setFeedbackFor({ sectionId: sec.id, label: `“${sec.heading}”`, angle: sec.angle, available: sec.angles })}>Feedback</button>
                </div>
              </div>
              {sec.body
                ? <div className={sec.pending ? 'rendering' : ''}><Markdown>{sec.body}</Markdown></div>
                : <div className="skeleton" aria-busy={sec.pending}>{sec.pending ? `Writing this section for you (${sec.angle})…` : 'Not rendered yet.'}</div>}
              {sec.approximate && <p className="muted small">{sec.pending ? 'Showing the closest earlier version while your new one is written.' : 'Closest earlier version.'}</p>}
              {sec.check && (
                <InlineCheck key={sec.check.id} check={sec.check} previous={s.answers[`${id}:${sec.check.id}`]}
                  onAnswer={choice => dispatch({ type: 'answer', conceptId: id, checkId: sec.check!.id, angle: sec.angle, choice })} />
              )}
              {sec.code && (
                <CodeExercise exercise={sec.code} passed={!!s.answers[`${id}:${sec.code.id}`]?.correct}
                  onResult={ok => dispatch({ type: 'answer', conceptId: id, checkId: sec.code!.id, angle: sec.angle, correct: ok })} />
              )}
            </section>
          )
        })}

        {sections.length > 0 && (
          <footer className="gate">
            <h3>Mastery</h3>
            <p className="muted">The engine decides, not a “mark complete” button: P(learned) ≥ 0.95 and at least 3 different items correct, then a spaced review a day later confirms it.</p>
            <div className="row">
              <MasteryBar value={concept.mastery} /><span>P(learned) = {concept.mastery.toFixed(2)}</span>
              <span>· correct answers: {correct}</span>
              <StateBadge state={concept.state} />
            </div>
            <div className="row">
              {!rendition?.studied && <button className="btn" onClick={() => dispatch({ type: 'markStudied', conceptId: id })}>I've read it</button>}
              {nextConcept && <Link className="btn btn-primary" to={`/lesson/${nextConcept.id}`}>Next: {nextConcept.title} →</Link>}
            </div>
          </footer>
        )}
      </article>

      <SidePanel conceptId={id} card={view?.card} tab={tab} setTab={setTab} draft={draft} clearDraft={clearDraft} currentSection={current} />

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
