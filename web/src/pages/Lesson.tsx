import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getLesson, jobActive, openLesson, postActivity, useStore } from '../store'
import type { Angle, LessonView } from '../types'
import Markdown from '../components/Markdown'
import InlineCheck from '../components/InlineCheck'
import CodeExercise from '../components/CodeExercise'
import ExplainBack from '../components/ExplainBack'
import LocalExercise from '../components/LocalExercise'
import Viz from '../components/viz/Viz'
import FeedbackDialog from '../components/FeedbackDialog'
import LessonHistory from '../components/LessonHistory'
import SidePanel, { SourceCardView, type Tab } from '../components/SidePanel'
import StateBadge, { MasteryBar } from '../components/StateBadge'
import { formulaAt, refFromSelection, sectionOf } from '../components/selection'
import type { FeedbackRef } from '../types'

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
  const [feedbackFor, setFeedbackFor] = useState<{ sectionId?: string; label: string; angle?: Angle; available?: Angle[]; reference?: FeedbackRef } | null>(null)
  const [toast, setToast] = useState('')
  const [history, setHistory] = useState<{ focus?: number } | null>(null)
  const [newVersion, setNewVersion] = useState<number | null>(null)
  const lastHead = useRef<number | null>(null)
  const [current, setCurrent] = useState<string | undefined>()
  const [selection, setSelection] = useState<{ text: string; ref: FeedbackRef | null; top: number; left: number } | null>(null)
  const [mathTool, setMathTool] = useState<{ ref: FeedbackRef; top: number; left: number } | null>(null)
  const mathHide = useRef(0)
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

  // Time actually spent: a heartbeat every 30 s while the lesson is visible and you've interacted recently.
  useEffect(() => {
    let lastInput = Date.now()
    const mark = () => { lastInput = Date.now() }
    const events = ['pointerdown', 'keydown', 'scroll', 'pointermove'] as const
    events.forEach(e => window.addEventListener(e, mark, { passive: true }))
    const t = setInterval(() => {
      if (document.visibilityState === 'visible' && Date.now() - lastInput < 120_000) postActivity(id, 30).catch(() => {})
    }, 30_000)
    return () => { clearInterval(t); events.forEach(e => window.removeEventListener(e, mark)) }
  }, [id])

  // A finished apply job moves the head to a new "apply" version: offer to show what changed.
  useEffect(() => {
    const h = view?.head ?? null
    const top = view?.versions[0]
    if (lastHead.current !== null && h !== null && h > lastHead.current && top?.version === h && top.source === 'apply') setNewVersion(h)
    if (view) lastHead.current = h
  }, [view])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(''), 5000)
    return () => clearTimeout(t)
  }, [toast])

  useEffect(() => {
    const hide = () => { setSelection(null); setMathTool(null) }
    window.addEventListener('scroll', hide, true)
    return () => window.removeEventListener('scroll', hide, true)
  }, [])

  if (!concept) return <div className="page"><p>Lesson not found. <Link to="/roadmap">Back to the roadmap</Link></p></div>

  const onMouseUp = () => {
    const sel = window.getSelection()
    const text = sel?.toString().trim() ?? ''
    if (!sel || text.length < 3 || !article.current?.contains(sel.anchorNode)) { setSelection(null); return }
    const r = sel.getRangeAt(0).getBoundingClientRect()
    setSelection({ text: text.slice(0, 300), ref: refFromSelection(sel), top: Math.max(8, r.top - 44), left: r.left + r.width / 2 })
    setMathTool(null)
  }

  // Hovering a formula in the lesson text offers feedback or a note about exactly that formula. The toolbar
  // stays a moment after the mouse leaves the formula, so it can be reached.
  const onMouseMove = (e: React.MouseEvent) => {
    const t = e.target as Element
    const k = t.closest('button') ? null : formulaAt(t)
    const quote = k?.querySelector('annotation[encoding="application/x-tex"]')?.textContent?.trim() ?? ''
    if (!k || !k.closest('.lesson-section') || quote.length < 3) {
      if (mathTool && !mathHide.current) mathHide.current = window.setTimeout(() => { setMathTool(null); mathHide.current = 0 }, 700)
      return
    }
    window.clearTimeout(mathHide.current); mathHide.current = 0
    if (mathTool?.ref.quote === quote) return
    const r = k.getBoundingClientRect()
    setMathTool({ ref: { kind: 'formula', quote, sectionId: sectionOf(k) }, top: Math.max(8, r.top - 40), left: r.left + r.width / 2 })
  }
  const sectionTitle = (sid?: string | null) => sections.find(x => x.id === sid)?.heading
  const feedbackOn = (ref: FeedbackRef) => {
    const sec = sections.find(x => x.id === ref.sectionId)
    setFeedbackFor({ sectionId: ref.sectionId ?? undefined, label: sec ? `a part of “${sec.heading}”` : 'a part of this lesson',
      angle: sec?.angle, available: sec?.angles, reference: ref })
  }
  const noteOn = (ref: FeedbackRef) => {
    setTab('notes')
    setDraft({ tab: 'notes', text: '', quote: ref.kind === 'formula' ? `$${ref.quote}$` : ref.kind === 'viz' ? `Graph in “${sectionTitle(ref.sectionId) ?? 'this lesson'}”: ${ref.quote}` : ref.quote })
  }

  const sections = view?.sections ?? []
  const rendition = view?.rendition
  const correct = Object.entries(s.answers).filter(([k, v]) => k.startsWith(id + ':') && v.correct).length
  const siblings = s.concepts.filter(c => c.moduleId === concept.moduleId)
  const nextConcept = siblings[siblings.findIndex(c => c.id === id) + 1]

  return (
    <div className="lesson-layout">
      <article className="lesson" ref={article} onMouseUp={onMouseUp} onMouseMove={onMouseMove}>
        <div className="crumbs"><Link to="/roadmap">{track?.title}</Link> › {module?.title}</div>
        <header className="lesson-head">
          <h1>{concept.title}</h1>
          <p className="lead">{concept.objective}</p>
          <div className="row">
            <StateBadge state={concept.state} />
            <MasteryBar value={concept.mastery} />
            <span className="muted small">~{concept.minutes} min</span>
            {rendition && <span className="muted small">Rendered from card v{rendition.cardVersion} · playbook v{rendition.playbookVersion}</span>}
            {view && view.head !== null && (
              <button className="pill pill-button" onClick={() => setHistory({})} title="Lesson versions: compare and go back">
                Version v{view.head}{view.versions.length > 1 ? ` of ${view.versions.length}` : ''} · history
              </button>
            )}
            <span className="spacer" />
            <button className="btn" onClick={() => setFeedbackFor({ label: 'this lesson' })}>Give feedback</button>
          </div>
        </header>

        {loadError && <p className="error">{loadError}</p>}
        {!view && !loadError && <p className="muted">Opening…</p>}

        {view?.applying && <div className="banner"><span>Applying your feedback: the next version of this lesson is being written.</span></div>}
        {newVersion !== null && !view?.applying && (
          <div className="banner banner-ok">
            <span>Your feedback is applied: this is v{newVersion}.</span>
            <span className="row">
              <button className="btn btn-primary" onClick={() => { setHistory({ focus: newVersion }); setNewVersion(null) }}>See what changed</button>
              <button className="btn" onClick={() => setNewVersion(null)}>Dismiss</button>
            </span>
          </div>
        )}
        {view?.remedial && (
          <div className="banner banner-accent">
            <span><strong>This lesson seems hard going</strong> ({view.remedial.reasons.join(', ')}).
              An extra lesson, “{view.remedial.title}”, can take on exactly what got in the way, in smaller steps and from another angle.
              It is researched and fact-checked like any lesson.</span>
            <span className="row">
              <button className="btn btn-primary" onClick={() => dispatch({ type: 'addRemedial', conceptId: id })}>Add “{view.remedial.title}”</button>
              <button className="btn" onClick={() => dispatch({ type: 'dismissRemedial', conceptId: id })}>Not now</button>
            </span>
          </div>
        )}
        {view && view.extraLessons.filter(x => x.id !== id).length > 0 && (
          <p className="small">Extra lessons for this: {view.extraLessons.filter(x => x.id !== id).map((x, i) => (
            <span key={x.id}>{i > 0 && ' · '}<Link to={`/lesson/${x.id}`}>{x.title}</Link></span>
          ))}</p>
        )}
        {rendition?.stale && (rendition.studied || rendition.shaped) && (
          <div className="banner">
            <span>Your playbook changed since {rendition.studied ? 'you studied this' : 'you shaped this lesson'} (v{rendition.playbookVersion} → v{s.playbook.version}).
              {rendition.shaped && ' Refreshing keeps the text you shaped where the angle and style stay the same; earlier versions stay in the history.'}</span>
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
            <section key={sec.id} className="lesson-section" data-section-id={sec.id} onMouseEnter={() => setCurrent(sec.heading)}>
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
              {sec.viz && (
                <div className="viz-block">
                  <Viz key={`${sec.id}-viz`} spec={sec.viz} />
                  <div className="viz-tools">
                    <button className="link small" onClick={() => feedbackOn({ kind: 'viz', quote: sec.viz!.caption, sectionId: sec.id })}>Feedback on this graph</button>
                    <button className="link small" onClick={() => noteOn({ kind: 'viz', quote: sec.viz!.caption, sectionId: sec.id })}>Note</button>
                  </div>
                </div>
              )}
              {sec.approximate && <p className="muted small">{sec.pending ? 'Showing the closest earlier version while your new one is written.' : 'Closest earlier version.'}</p>}
              {sec.check && (
                <InlineCheck key={sec.check.id} check={sec.check} previous={s.answers[`${id}:${sec.check.id}`]}
                  onAnswer={choice => dispatch({ type: 'answer', conceptId: id, checkId: sec.check!.id, angle: sec.angle, choice })}
                  onUndo={() => dispatch({ type: 'undoAnswer', conceptId: id, itemId: sec.check!.id })} />
              )}
              {sec.code?.runtime === 'local' && (
                <LocalExercise key={sec.code.id} conceptId={id} exercise={sec.code} angle={sec.angle}
                  passed={!!s.answers[`${id}:${sec.code.id}`]?.correct} />
              )}
              {sec.code && sec.code.runtime !== 'local' && (
                <CodeExercise exercise={sec.code} passed={!!s.answers[`${id}:${sec.code.id}`]?.correct}
                  onResult={ok => dispatch({ type: 'answer', conceptId: id, checkId: sec.code!.id, angle: sec.angle, correct: ok })} />
              )}
              {sec.explain && (
                <ExplainBack key={sec.explain.id} item={sec.explain} grading={s.gradings[`${id}:${sec.explain.id}`]}
                  inProgress={jobActive(s, 'grade', { concept_id: id })}
                  onSubmit={answer => dispatch({ type: 'explain', conceptId: id, itemId: sec.explain!.id, angle: sec.angle, answer })}
                  onUndo={() => dispatch({ type: 'undoAnswer', conceptId: id, itemId: sec.explain!.id })} />
              )}
            </section>
          )
        })}

        {sections.length > 0 && (
          <footer className="gate">
            <h3>Mastery</h3>
            <p className="muted">The engine decides, not a “mark complete” button: P(learned) ≥ 0.95, at least 3 different items correct, and your explain-back passed; then a spaced review a day later confirms it.</p>
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

      <SidePanel conceptId={id} card={view?.card} tab={tab} setTab={setTab} draft={draft} clearDraft={clearDraft} currentSection={current}
        onShowVersion={v => setHistory({ focus: v })} />

      {history && view && view.head !== null && view.versions.length > 0 && (
        <LessonHistory conceptId={id} versions={view.versions} head={view.head} focus={history.focus} onClose={() => setHistory(null)} />
      )}

      {selection && (
        <div className="sel-toolbar" style={{ top: selection.top, left: selection.left }} onMouseDown={e => e.preventDefault()}>
          <button onClick={() => { if (selection.ref) noteOn(selection.ref); else { setTab('notes'); setDraft({ tab: 'notes', text: '', quote: selection.text }) } setSelection(null) }}>Add note</button>
          {selection.ref && <button onClick={() => { feedbackOn(selection.ref!); setSelection(null); window.getSelection()?.removeAllRanges() }}>Feedback on this</button>}
          <button onClick={() => { setTab('tutor'); setDraft({ tab: 'tutor', text: `About “${selection.text}”: ` }); setSelection(null) }}>Ask tutor</button>
        </div>
      )}

      {mathTool && !selection && (
        <div className="sel-toolbar" style={{ top: mathTool.top, left: mathTool.left }} onMouseDown={e => e.preventDefault()}
          onMouseEnter={() => { window.clearTimeout(mathHide.current); mathHide.current = 0 }} onMouseLeave={() => setMathTool(null)}>
          <button onClick={() => { feedbackOn(mathTool.ref); setMathTool(null) }}>Feedback on formula</button>
          <button onClick={() => { noteOn(mathTool.ref); setMathTool(null) }}>Note</button>
        </div>
      )}

      {feedbackFor && (
        <FeedbackDialog target={feedbackFor.label} reference={feedbackFor.reference} onClose={() => setFeedbackFor(null)}
          onSubmit={(tags, text, kind) => {
            dispatch({ type: 'feedback', conceptId: id, sectionId: feedbackFor.sectionId, angle: feedbackFor.angle, available: feedbackFor.available, tags, text, kind, ref: feedbackFor.reference })
            setFeedbackFor(null); setTab('feedback')
          }} />
      )}

      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  )
}
