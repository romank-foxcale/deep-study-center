// Change log of a lesson (SPEC §11): the whole lesson, section by section, as a diff between two versions in the style
// of word-processor suggestions: deleted text red with a line through it, inserted text green, with why each change
// was made. "Show only changed sections" hides the rest.

import { useEffect, useState } from 'react'
import { getLessonDiff, useStore } from '../store'
import type { LessonDiff, LessonVersion } from '../types'
import Markdown from './Markdown'
import DiffMarkdown from './DiffMarkdown'

interface Props {
  conceptId: string
  versions: LessonVersion[]
  head: number
  /** Version to compare first (with its parent); defaults to the shown version. */
  focus?: number
  onClose: () => void
}

const sourceLabel = (v: LessonVersion) => v.source === 'apply' ? 'applied feedback' : v.parent ? 're-rendered' : 'first render'

export default function LessonHistory({ conceptId, versions, head, focus, onClose }: Props) {
  const { dispatch } = useStore()
  const start = versions.find(v => v.version === (focus ?? head)) ?? versions[0]
  // Default: the version against its parent, else against the version just before it (older → newer);
  // the first version is compared with the next one.
  const older = [...versions].map(v => v.version).filter(v => v < start.version).sort((x, y) => y - x)[0]
  const newer = versions.map(v => v.version).filter(v => v > start.version).sort((x, y) => x - y)[0]
  const from = start.parent ?? older ?? start.version
  const [a, setA] = useState(from === start.version ? start.version : from)
  const [b, setB] = useState(from === start.version ? (newer ?? start.version) : start.version)
  const [diff, setDiff] = useState<LessonDiff | null>(null)
  const [error, setError] = useState('')
  const [onlyChanged, setOnlyChanged] = useState(false)

  useEffect(() => {
    let live = true
    if (a === b) return
    getLessonDiff(conceptId, a, b).then(d => { if (live) { setDiff(d); setError('') } }, e => live && setError((e as Error).message))
    return () => { live = false }
  }, [conceptId, a, b])

  const restore = async (v: number) => { if (await dispatch({ type: 'revertLesson', conceptId, version: v })) onClose() }
  const shown = a === b ? null : diff
  const sections = shown?.sections.filter(sec => !onlyChanged || sec.status !== 'same') ?? []
  const changed = shown?.sections.filter(sec => sec.status !== 'same').length ?? 0
  const fbText = (id: number) => shown?.feedback.find(f => f.id === id)
  const vb = versions.find(v => v.version === b)
  const option = (v: LessonVersion) => <option key={v.version} value={v.version}>v{v.version} · {sourceLabel(v)}{v.version === head ? ' (shown)' : ''}</option>

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal-wide" role="dialog" aria-label="Change log" onClick={e => e.stopPropagation()}>
        <div className="row row-between">
          <h3>Change log</h3>
          <button className="btn btn-small" onClick={onClose}>Close</button>
        </div>
        <p className="muted small">The whole lesson, section by section: deleted text is red, inserted text is green. Every version is
          kept; going back from applied feedback tells the system that this way of applying it did not work for you.</p>

        <div className="row diff-pick">
          <label className="small">From <select className="input input-small" value={a} onChange={e => setA(Number(e.target.value))}>
            {versions.map(option)}
          </select></label>
          <span aria-hidden>→</span>
          <label className="small">To <select className="input input-small" value={b} onChange={e => setB(Number(e.target.value))}>
            {versions.map(option)}
          </select></label>
          <span className="spacer" />
          <label className="small"><input type="checkbox" checked={onlyChanged} onChange={e => setOnlyChanged(e.target.checked)} /> Show only changed sections</label>
        </div>

        {vb && (
          <div className="pd-version small">
            <span><strong>v{vb.version}:</strong> {vb.summary}</span>
            <span className="muted">{new Date(vb.ts).toLocaleString()}
              {vb.feedbackIds.length > 0 && ` · feedback ${vb.feedbackIds.map(i => '#' + i).join(', ')}`}</span>
            {vb.version === head ? <span className="pill pill-ok">shown in the lesson</span>
              : <button className="btn btn-small" onClick={() => restore(vb.version)}>Show v{vb.version} in the lesson</button>}
          </div>
        )}

        {shown && (
          <div className="pd-legend small">
            <span className="pd-del">deleted</span> <span className="pd-ins">inserted</span>
            <span className="muted">{changed} of {shown.sections.length} sections changed</span>
          </div>
        )}
        {a === b && <p className="muted">Pick two different versions to compare.</p>}
        {error && <p className="error">{error}</p>}
        {shown && sections.length === 0 && <p className="muted">No section changed between v{a} and v{b}.</p>}

        <div className="diff-pane">
          {sections.map(sec => {
            const same = sec.status === 'same'
            return (
              <section key={sec.id} className={`pd-section pd-${sec.status}`}>
                <header className="pd-head">
                  <strong>{sec.heading}</strong>
                  {!same && <span className="small"><span className="pd-count-ins">+{sec.inserted}</span> <span className="pd-count-del">−{sec.deleted}</span> words</span>}
                  {sec.angleA !== sec.angleB && <span className="pill">{sec.angleA ?? '–'} → {sec.angleB ?? '–'}</span>}
                </header>
                <div className="pd-text">
                  {same ? <Markdown>{sec.tokens.map(([, t]) => t).join('')}</Markdown> : <DiffMarkdown tokens={sec.tokens} />}
                </div>
                {sec.changes.length > 0 && (
                  <ul className="pd-notes">
                    {sec.changes.map((c, i) => (
                      <li key={i} className={c.undone ? 'pd-undone' : ''}>
                        <span className="pill">v{c.version}{c.undone ? ' · undone' : ''}</span>{' '}
                        <strong>Why:</strong> {c.why} <strong>How:</strong> {c.how}
                        {c.technique && <span className="muted"> · {c.technique}</span>}
                        {c.relatedBecause && <div className="small"><strong>Also changed here because:</strong> {c.relatedBecause}</div>}
                        {c.feedbackIds.map(id => {
                          const f = fbText(id)
                          return <div key={id} className="muted small">#{id}{f ? `: ${f.text ? `“${f.text}”` : f.tags.join(', ')}${f.deleted ? ' (deleted)' : ''}` : ''}</div>
                        })}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            )
          })}
        </div>
      </div>
    </div>
  )
}
