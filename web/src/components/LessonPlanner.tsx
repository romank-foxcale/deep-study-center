import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { getLessonPlan, useStore } from '../store'
import Markdown from './Markdown'
import type { LessonPlanGraph, LessonPlanNode, LessonPlanView } from '../types'

// The lesson plan graph (SPEC §42). A book lesson is planned before it is written: what you hold (green), the
// foundations to lay (orange), the reasoning steps (blue), the formulas (lime) and the goal (gold), each with the form it
// will be shown in. Watch it being made and send notes; then cut what you know, ask for another form, add notes,
// re-plan, and approve. Approving writes the lesson from the plan.

const W = 196, H = 86, GX = 22, GY = 46
const KIND: Record<string, string> = { held: 'You hold it', foundation: 'Foundation', step: 'Step', formula: 'Formula', goal: 'Goal' }
const FORM: Record<string, string> = {
  example: 'Worked example', interactive: 'Interactive', figure: 'Figure', text: 'Short text', derivation: 'Derivation', none: 'Not taught again',
}

/** Levels from the bottom: a node with nothing it needs is level 0; else one above the highest node it needs. The goal is
 *  drawn at the top, what you hold at the bottom. */
function layout(plan: LessonPlanGraph) {
  const need = new Map(plan.nodes.map(n => [n.key, plan.edges.filter(e => e[1] === n.key).map(e => e[0])]))
  const level = new Map<string, number>()
  const lv = (k: string, seen: Set<string>): number => {
    if (level.has(k)) return level.get(k)!
    if (seen.has(k)) return 0
    seen.add(k)
    const v = Math.max(-1, ...(need.get(k) ?? []).map(x => lv(x, seen))) + 1
    level.set(k, v)
    return v
  }
  plan.nodes.forEach(n => lv(n.key, new Set()))
  const top = Math.max(0, ...level.values())
  const rows: string[][] = Array.from({ length: top + 1 }, () => [])
  plan.nodes.forEach(n => rows[top - level.get(n.key)!].push(n.key))
  const widest = Math.max(1, ...rows.map(r => r.length))
  const w = widest * (W + GX) - GX
  const at = new Map<string, { x: number; y: number }>()
  rows.forEach((row, i) => {
    const x0 = (w - (row.length * (W + GX) - GX)) / 2
    row.forEach((k, j) => at.set(k, { x: x0 + j * (W + GX), y: i * (H + GY) }))
  })
  return { at, w, h: rows.length * (H + GY) - GY }
}

export default function LessonPlanner({ conceptId, readOnly = false, onWrite }: { conceptId: string; readOnly?: boolean; onWrite?: () => void }) {
  const { s, dispatch } = useStore()
  const [v, setV] = useState<LessonPlanView | null>(null)
  const [sel, setSel] = useState<string | null>(null)
  const [steer, setSteer] = useState('')
  const [planNote, setPlanNote] = useState('')
  const [sent, setSent] = useState('')
  const job = s.jobs.find(j => j.kind === 'lesson_graph' && j.input?.concept_id === conceptId && (j.status === 'queued' || j.status === 'running'))
  const tick = `${job?.id ?? ''}:${job?.progress.length ?? 0}:${s.jobs.length}`
  const reload = () => getLessonPlan(conceptId).then(setV, () => {})
  useEffect(() => { reload() }, [conceptId, tick])  // eslint-disable-line react-hooks/exhaustive-deps

  const plan = v?.plan ?? null
  const planning = !!v?.job || plan?.status === 'planning'
  const shown = plan && plan.nodes.length ? plan : plan?.shown ?? null
  const old = !!shown && shown !== plan  // the last finished version, while a new one is made
  const geo = useMemo(() => (shown ? layout(shown) : null), [shown])
  const pendingOn = (key: string, kind?: string) => (v?.notes ?? []).some(n => n.used === null && n.node === key && (!kind || n.kind === kind))
  const node = shown?.nodes.find(n => n.key === sel) ?? null

  const box = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {  // long math in a node is made smaller until it fits
    box.current?.querySelectorAll<HTMLElement>('.lp-title').forEach(el => {
      const m = el.querySelector<HTMLElement>('.katex')
      if (!m) return
      m.style.fontSize = ''
      const k = Math.min(1, (el.clientWidth - 2) / Math.max(1, m.getBoundingClientRect().width))
      if (k < 1) m.style.fontSize = `${Math.max(0.55, k)}em`
    })
  })

  const note = async (kind: 'cut' | 'other' | 'note' | 'plan' | 'steer', text = '', key = '') => {
    if (await dispatch({ type: 'lessonPlanNote', conceptId, kind, text, node: key })) reload()
  }

  if (!v) return <div className="placeholder"><p className="muted">Loading the plan…</p></div>

  return (
    <div className={`lp${readOnly ? ' lp-readonly' : ''}`}>
      {!readOnly && <div className="row row-between lp-head">
        <div>
          <div className="eyebrow">{planning ? 'Planning this lesson' : plan?.status === 'approved' ? `Plan v${plan.version} · approved`
            : plan?.status === 'failed' ? 'The plan failed' : `Plan v${plan?.version ?? 1} · review it`}</div>
          <p className="muted small">Nothing is written until you approve. Cut what you know, ask for another form, add notes.</p>
        </div>
        <div className="row">
          {plan?.status !== 'approved' && <>
            <button className="btn" disabled={planning || !v.pending} onClick={() => dispatch({ type: 'planLesson', conceptId }).then(reload)}
              title="Make a new version of the plan with your notes">Re-plan with my notes{v.pending ? ` (${v.pending})` : ''}</button>
            <button className="btn btn-primary" disabled={planning || plan?.status !== 'ready'}
              onClick={async () => { if (await dispatch({ type: 'approveLessonPlan', conceptId })) { reload(); onWrite?.() } }}>Approve and write</button>
          </>}
        </div>
      </div>}

      {planning && (
        <div className="card lp-live">
          <div className="row"><span className="lp-pulse" aria-hidden /> <strong>{v.job?.status === 'queued' ? 'Waiting to plan…' : 'Making the plan'}</strong>
            <span className="muted small">· about a minute</span></div>
          <ul className="lp-progress small">{(v.job?.progress ?? []).map((p, i) => <li key={i}>✓ {p}</li>)}</ul>
          <label className="small muted" htmlFor="lp-steer">Steer the plan now: your note goes into the next version, which starts by itself.</label>
          <div className="row lp-steer">
            <input id="lp-steer" className="input" value={steer} placeholder="For example: I know logs well. Use a coin-flip example."
              onChange={e => setSteer(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && steer.trim()) { note('steer', steer); setSteer(''); setSent('Sent.') } }} />
            <button className="btn btn-small" disabled={!steer.trim()} onClick={() => { note('steer', steer); setSteer(''); setSent('Sent.') }}>Send</button>
            {sent && <span className="small muted">{sent}</span>}
          </div>
        </div>
      )}
      {plan?.status === 'failed' && !planning && (
        <div className="banner banner-bad"><span>The plan could not be made: {plan.error || 'unknown error'}.</span>
          <button className="btn" onClick={() => dispatch({ type: 'planLesson', conceptId }).then(reload)}>Try again</button></div>
      )}

      {shown && geo && <>
        {shown.approach && <div className="card lp-approach">
          <div className="eyebrow">The approach</div>
          <Markdown>{shown.approach}</Markdown>
          {shown.goal && <div className="small lp-goal-line"><strong>Goal:</strong> <Markdown inline>{shown.goal}</Markdown></div>}
          {!!shown.removed?.length && <p className="small muted">Left out since the version before: {shown.removed.join(', ')}.</p>}
        </div>}
        <div className={`lp-layout${old ? ' lp-old' : ''}`}>
          {old && <p className="small muted">This is version {shown.version}. The new version replaces it when it is ready.</p>}
          <div className="lp-canvas card" ref={box}>
            <div className="lp-world" style={{ width: geo.w, height: geo.h }}>
              <svg className="lp-edges" width={geo.w} height={geo.h} aria-hidden>
                {shown.edges.map(([a, b]) => {
                  const p = geo.at.get(a), q = geo.at.get(b)
                  if (!p || !q) return null
                  const x1 = p.x + W / 2, y1 = p.y, x2 = q.x + W / 2, y2 = q.y + H
                  const hot = sel && (a === sel || b === sel)
                  return <path key={`${a}>${b}`} className={hot ? 'hot' : ''} d={`M ${x1} ${y1} C ${x1} ${(y1 + y2) / 2}, ${x2} ${(y1 + y2) / 2}, ${x2} ${y2}`} />
                })}
              </svg>
              {shown.nodes.map(n => {
                const p = geo.at.get(n.key)!
                const cut = pendingOn(n.key, 'cut')
                return (
                  <div key={n.key} role="button" tabIndex={0} style={{ left: p.x, top: p.y, width: W, height: H }}
                    className={`lp-node lp-${n.kind}${sel === n.key ? ' selected' : ''}${cut ? ' cut' : ''}${pendingOn(n.key) && !cut ? ' noted' : ''}`}
                    onClick={() => setSel(sel === n.key ? null : n.key)} onKeyDown={e => { if (e.key === 'Enter') setSel(n.key) }}
                    aria-label={`${KIND[n.kind]}: ${n.title}`}>
                    <div className="lp-kind">{KIND[n.kind]}{n.change && <span className={`lp-change lp-${n.change}`}>{n.change}</span>}</div>
                    <div className="lp-title"><Markdown inline>{n.title}</Markdown></div>
                    <div className="lp-form">{FORM[n.form] ?? n.form}{n.pages ? ` · p. ${n.pages}` : ''}</div>
                  </div>
                )
              })}
            </div>
          </div>
          <aside className="lp-panel card">
            {node ? <NodePanel n={node} readOnly={readOnly || plan?.status === 'approved'} cut={pendingOn(node.key, 'cut')}
              notes={(v.notes ?? []).filter(x => x.node === node.key && x.used === null).map(x => x.text || (x.kind === 'cut' ? 'I know this' : 'Show it another way'))}
              onNote={(kind, text) => note(kind, text, node.key)} />
              : <p className="muted small">Click a node to see what it adds and how it will be shown.</p>}
            {!readOnly && plan?.status !== 'approved' && <div className="lp-plan-note">
              <div className="eyebrow">A note for the whole plan</div>
              <textarea className="input" rows={3} value={planNote} placeholder="For example: fewer steps, more numbers."
                onChange={e => setPlanNote(e.target.value)} />
              <button className="btn btn-small" disabled={!planNote.trim()} onClick={() => { note('plan', planNote); setPlanNote('') }}>Add note</button>
              {(v.notes ?? []).filter(x => x.used === null && !x.node).map(x => <p key={x.id} className="small muted">• {x.text}</p>)}
            </div>}
          </aside>
        </div>
        <div className="lp-legend small muted">
          {Object.entries(KIND).map(([k, t]) => <span key={k}><i className={`lp-swatch lp-${k}`} />{t}</span>)}
          <span>An arrow: hold this first.</span>
        </div>
      </>}
    </div>
  )
}

function NodePanel({ n, readOnly, cut, notes, onNote }: {
  n: LessonPlanNode; readOnly: boolean; cut: boolean; notes: string[]; onNote: (kind: 'cut' | 'other' | 'note', text?: string) => void
}) {
  const [text, setText] = useState('')
  useEffect(() => setText(''), [n.key])
  return (
    <div className="lp-node-panel">
      <div className="eyebrow">{KIND[n.kind]}</div>
      <h3><Markdown inline>{n.title}</Markdown></h3>
      {n.says && <div className="small lp-says-full"><Markdown>{n.says}</Markdown></div>}
      <p className="small muted">Shown as: {FORM[n.form] ?? n.form}{n.whyForm ? ` (${n.whyForm})` : ''}{n.pages ? ` · book p. ${n.pages}` : ''}</p>
      {!readOnly && n.kind !== 'goal' && <div className="row">
        <button className={`btn btn-small${cut ? ' btn-primary' : ''}`} onClick={() => onNote('cut')}
          title="Leave it out: you know it already. Press again to take it back.">{cut ? 'Cut: I know this' : 'I know this'}</button>
        {n.kind !== 'held' && <button className="btn btn-small" onClick={() => onNote('other', text.trim())}
          title="Ask for another form (add a note to say which)">Show it another way</button>}
      </div>}
      {!readOnly && <>
        <textarea className="input" rows={2} value={text} placeholder="A note for this node" onChange={e => setText(e.target.value)} />
        <button className="btn btn-small" disabled={!text.trim()} onClick={() => { onNote('note', text.trim()); setText('') }}>Add note</button>
      </>}
      {notes.length > 0 && <ul className="small muted lp-notes">{notes.map((t, i) => <li key={i}>💬 {t}</li>)}</ul>}
    </div>
  )
}
