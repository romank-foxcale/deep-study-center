// The feedback log with its actions (SPEC §11): select items and apply them to their lesson, correct an
// item's kind, edit or delete it, and see its status (pending, applied in vN, reverted, sent to the card check).

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { FEEDBACK_TAGS, KIND_LABELS, jobActive, useStore } from '../store'
import type { Feedback, FeedbackKind } from '../types'

const KINDS: FeedbackKind[] = ['lesson', 'me', 'fact']

/** Items you would usually want to apply: not yet applied, reverted, or edited since they were applied. */
const wantsApply = (f: Feedback) =>
  f.status.state === 'pending' || f.status.state === 'reverted' || (f.status.state === 'applied' && f.status.changedSinceApplied)

const selectable = (f: Feedback) => f.status.state !== 'routed' && f.status.state !== 'done'

export function StatusPill({ f, onShow }: { f: Feedback; onShow?: (version: number) => void }) {
  const st = f.status
  if (st.state === 'applied') {
    return (
      <span className="row-inline">
        <button className="pill pill-ok pill-button" disabled={!onShow} onClick={() => onShow?.(st.version!)}
          title="Show what this version changed">applied in v{st.version}</button>
        {st.changedSinceApplied && <span className="pill pill-warn" title="You edited it after it was applied">changed since</span>}
      </span>
    )
  }
  if (st.state === 'reverted') return <span className="pill pill-bad" title={`You went back from v${st.version}`}>reverted (v{st.version})</span>
  if (st.state === 'routed') return <span className="pill pill-warn">sent to the card check</span>
  if (st.state === 'done') return <span className="pill" title={st.note ?? ''}>done at once</span>
  return <span className="pill">pending</span>
}

interface ListProps {
  items: Feedback[]
  /** Set when every item belongs to this lesson: enables selection and Apply. */
  conceptId?: string
  /** Opens the version history at a version (the lesson page passes this). */
  onShowVersion?: (version: number) => void
}

export default function FeedbackItems({ items, conceptId, onShowVersion }: ListProps) {
  const { s, dispatch } = useStore()
  const [picked, setPicked] = useState<Set<number> | null>(null)  // null = the default selection
  const selected = picked ?? new Set(items.filter(wantsApply).map(f => f.id))
  const applying = conceptId ? jobActive(s, 'apply_feedback', { concept_id: conceptId }) : false
  const chosen = items.filter(f => selected.has(f.id) && selectable(f))
  const facts = chosen.filter(f => f.kind === 'fact').length

  const toggle = (id: number) => {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setPicked(next)
  }
  const apply = async () => {
    if (!conceptId || !chosen.length) return
    if (await dispatch({ type: 'applyFeedback', conceptId, ids: chosen.map(f => f.id) })) setPicked(null)
  }

  return (
    <div className="fb-list">
      {conceptId && (
        <div className="fb-apply">
          <div className="row row-between">
            <span className="small">{applying ? 'Applying your feedback… a new lesson version is being written.' : `${chosen.length} selected`}</span>
            <button className="btn btn-small btn-primary" disabled={!chosen.length || applying} onClick={apply}>
              Apply {chosen.length || ''} to this lesson
            </button>
          </div>
          <p className="muted small">
            Apply writes the next version of this lesson for the selected items. It changes only explanations, examples,
            angle and pace, never facts, checks or exercises. You can compare versions and go back at any time.
            {facts > 0 && ` ${facts} selected item${facts > 1 ? 's say' : ' says'} the material may be wrong: ${facts > 1 ? 'they go' : 'it goes'} to the card check instead.`}
          </p>
        </div>
      )}
      {items.map(f => (
        <FeedbackItem key={f.id} f={f} selectable={!!conceptId && selectable(f)} selected={selected.has(f.id)}
          onToggle={() => toggle(f.id)} onShowVersion={onShowVersion}
          lessonTitle={conceptId ? undefined : s.concepts.find(c => c.id === f.conceptId)?.title} />
      ))}
    </div>
  )
}

function FeedbackItem({ f, selectable, selected, onToggle, onShowVersion, lessonTitle }: {
  f: Feedback; selectable: boolean; selected: boolean; onToggle: () => void
  onShowVersion?: (version: number) => void; lessonTitle?: string
}) {
  const { s, dispatch } = useStore()
  const [editing, setEditing] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const card = s.cards.find(c => c.conceptId === f.conceptId)
  const section = card?.sections.find(x => x.id === f.sectionId)?.heading
  const target = section ? `“${section}”` : 'whole lesson'

  return (
    <div className={`fb ${selected && selectable ? 'fb-selected' : ''}`}>
      <div className="fb-head">
        {selectable && <input type="checkbox" checked={selected} onChange={onToggle} aria-label={`Select feedback ${f.id}`} />}
        <div className="fb-title">
          <span>{f.tags.join(' · ') || 'Comment'}</span>
          <span className="muted small">
            {' '}· {lessonTitle ? <><Link to={`/lesson/${f.conceptId}`}>{lessonTitle}</Link>, </> : null}{target} · #{f.id}
          </span>
        </div>
        <StatusPill f={f} onShow={onShowVersion} />
      </div>
      {editing ? <EditFeedback f={f} onDone={() => setEditing(false)} /> : (
        <>
          {f.text && <p className="fb-text">“{f.text}”</p>}
          <div className="row fb-tools">
            <label className="small fb-kind">
              <span className="muted">Kind</span>
              <select className="input input-small" value={f.kind} aria-label={`Kind of feedback ${f.id}`}
                onChange={e => dispatch({ type: 'editFeedback', id: f.id, kind: e.target.value as FeedbackKind })}>
                {KINDS.map(k => <option key={k} value={k}>{KIND_LABELS[k]}</option>)}
              </select>
              <span className="muted" title="Who chose the kind">{f.kindSource === 'learner' ? 'set by you' : f.kindSource === 'agent' ? 'proposed by the agent' : 'first guess'}</span>
            </label>
            <span className="spacer" />
            <button className="link small" onClick={() => setEditing(true)}>Edit</button>
            {confirmDelete ? (
              <span className="small">Delete? <button className="link" onClick={() => dispatch({ type: 'deleteFeedback', id: f.id })}>Yes</button>
                {' / '}<button className="link" onClick={() => setConfirmDelete(false)}>No</button></span>
            ) : <button className="link small" onClick={() => setConfirmDelete(true)}>Delete</button>}
          </div>
          <details className="effects-box">
            <summary className="muted small">What it changed</summary>
            <ul className="effects">{f.effects.map((e, i) => <li key={i}>{e}</li>)}</ul>
          </details>
          <div className="muted small">{new Date(f.ts).toLocaleString()}{f.updatedAt && ` · edited ${new Date(f.updatedAt).toLocaleString()}`}</div>
        </>
      )}
    </div>
  )
}

const tagId = (label: string) => FEEDBACK_TAGS.find(t => t.label === label)?.id ?? label

function EditFeedback({ f, onDone }: { f: Feedback; onDone: () => void }) {
  const { dispatch } = useStore()
  const [tags, setTags] = useState<string[]>(f.tags.map(tagId).filter(t => FEEDBACK_TAGS.some(x => x.id === t)))
  const [text, setText] = useState(f.text)
  const [kind, setKind] = useState<FeedbackKind>(f.kind)
  const toggle = (id: string) => setTags(t => t.includes(id) ? t.filter(x => x !== id) : [...t, id])
  const save = async () => {
    if (await dispatch({ type: 'editFeedback', id: f.id, tags, text, kind: kind !== f.kind ? kind : undefined })) onDone()
  }
  return (
    <div className="fb-edit">
      <div className="chips">
        {FEEDBACK_TAGS.map(t => <button key={t.id} className={`chip ${tags.includes(t.id) ? 'on' : ''}`} onClick={() => toggle(t.id)}>{t.label}</button>)}
      </div>
      <textarea className="input" rows={3} value={text} onChange={e => setText(e.target.value)} aria-label="Feedback text" />
      <KindPicker value={kind} onChange={setKind} />
      <p className="muted small">Saving replaces this item's playbook signals and replays the playbook.
        {f.status.state === 'applied' && ' The lesson keeps v' + f.status.version + ' until you apply it again.'}</p>
      <div className="row row-end">
        <button className="btn btn-small" onClick={onDone}>Cancel</button>
        <button className="btn btn-small btn-primary" disabled={!tags.length && !text.trim()} onClick={save}>Save</button>
      </div>
    </div>
  )
}

export function KindPicker({ value, onChange, allowAuto }: {
  value: FeedbackKind | 'auto'; onChange: (k: FeedbackKind) => void; allowAuto?: (k: 'auto') => void
}) {
  return (
    <div className="kind-picker" role="radiogroup" aria-label="Kind of feedback">
      {allowAuto && (
        <label><input type="radio" checked={value === 'auto'} onChange={() => allowAuto('auto')} /> Let the agent decide</label>
      )}
      {KINDS.map(k => (
        <label key={k} title={{ lesson: 'Changes only this lesson', me: 'Also changes your playbook, so all lessons adapt', fact: 'Goes to the fact check of the source card' }[k]}>
          <input type="radio" checked={value === k} onChange={() => onChange(k)} /> {KIND_LABELS[k]}
        </label>
      ))}
    </div>
  )
}
