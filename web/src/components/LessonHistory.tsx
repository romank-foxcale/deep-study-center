// Lesson versions and a GitHub-style diff for prose (SPEC §11): pick any two versions, see per section what
// was deleted (red) and inserted (green), and why: each change with its reason, method and feedback ids.

import { useEffect, useState } from 'react'
import { getLessonDiff, useStore } from '../store'
import type { LessonDiff, LessonVersion } from '../types'

interface Props {
  conceptId: string
  versions: LessonVersion[]
  head: number
  /** Version to compare first (with its parent); defaults to the shown version. */
  focus?: number
  onClose: () => void
}

const sourceLabel = (v: LessonVersion) => v.source === 'apply' ? 'Applied feedback' : v.parent ? 'Re-rendered' : 'First render'

export default function LessonHistory({ conceptId, versions, head, focus, onClose }: Props) {
  const { dispatch } = useStore()
  const start = versions.find(v => v.version === (focus ?? head)) ?? versions[0]
  // Default: the version against its parent; a first version is compared with the newest other one.
  const other = versions.find(v => v.version !== start.version)?.version ?? start.version
  const [b, setB] = useState(start.parent !== null ? start.version : other)
  const [a, setA] = useState(start.parent ?? start.version)
  const [diff, setDiff] = useState<LessonDiff | null>(null)
  const [error, setError] = useState('')
  const [showSame, setShowSame] = useState(false)

  useEffect(() => {
    let live = true
    if (a === b) return
    getLessonDiff(conceptId, a, b).then(d => { if (live) { setDiff(d); setError('') } }, e => live && setError((e as Error).message))
    return () => { live = false }
  }, [conceptId, a, b])

  const compare = (v: LessonVersion) => { setB(v.version); setA(v.parent ?? v.version) }
  const restore = async (v: number) => { if (await dispatch({ type: 'revertLesson', conceptId, version: v })) onClose() }
  const shown = a === b ? null : diff
  const sections = shown?.sections.filter(sec => showSame || sec.status !== 'same') ?? []
  const fbText = (id: number) => shown?.feedback.find(f => f.id === id)

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal-wide" role="dialog" aria-label="Lesson versions" onClick={e => e.stopPropagation()}>
        <div className="row row-between">
          <h3>Lesson versions</h3>
          <button className="btn btn-small" onClick={onClose}>Close</button>
        </div>
        <p className="muted small">Every version is kept. “Show this version” switches the lesson to it; nothing is lost.
          Going back from applied feedback tells the system that this way of applying it did not work for you.</p>

        <div className="history">
          <ol className="version-list">
            {versions.map(v => (
              <li key={v.version} className={`version ${v.version === head ? 'version-head' : ''} ${v.version === b ? 'version-b' : ''}`}>
                <div className="row row-between">
                  <strong>v{v.version}</strong>
                  {v.version === head ? <span className="pill pill-ok">shown</span> : <span className={`pill ${v.source === 'apply' ? 'pill-accent' : ''}`}>{sourceLabel(v)}</span>}
                </div>
                <div className="small">{v.summary}</div>
                <div className="muted small">
                  {new Date(v.ts).toLocaleString()} · card v{v.cardVersion} · playbook v{v.playbookVersion}
                  {v.parent ? ` · from v${v.parent}` : ''}
                  {v.feedbackIds.length > 0 && ` · feedback ${v.feedbackIds.map(i => '#' + i).join(', ')}`}
                </div>
                <div className="row">
                  {v.parent !== null && <button className="link small" onClick={() => compare(v)}>What changed</button>}
                  {v.version !== head && <button className="link small" onClick={() => restore(v.version)}>Show this version</button>}
                </div>
              </li>
            ))}
          </ol>

          <div className="diff-pane">
            <div className="row diff-pick">
              <label className="small">From <select className="input input-small" value={a} onChange={e => setA(Number(e.target.value))}>
                {versions.map(v => <option key={v.version} value={v.version}>v{v.version}</option>)}
              </select></label>
              <span aria-hidden>→</span>
              <label className="small">To <select className="input input-small" value={b} onChange={e => setB(Number(e.target.value))}>
                {versions.map(v => <option key={v.version} value={v.version}>v{v.version}</option>)}
              </select></label>
              <span className="spacer" />
              <label className="small"><input type="checkbox" checked={showSame} onChange={e => setShowSame(e.target.checked)} /> Show unchanged sections</label>
            </div>
            <div className="pd-legend small"><span className="pd-del">deleted</span> <span className="pd-ins">inserted</span></div>
            {a === b && <p className="muted">Pick two different versions to compare.</p>}
            {error && <p className="error">{error}</p>}
            {shown && sections.length === 0 && <p className="muted">No section changed between v{a} and v{b}.</p>}
            {sections.map(sec => (
              <section key={sec.id} className={`pd-section pd-${sec.status}`}>
                <header className="pd-head">
                  <strong>{sec.heading}</strong>
                  {sec.status !== 'same' && <span className="small"><span className="pd-count-ins">+{sec.inserted}</span> <span className="pd-count-del">−{sec.deleted}</span> words</span>}
                  {sec.angleA !== sec.angleB && <span className="pill">{sec.angleA ?? '–'} → {sec.angleB ?? '–'}</span>}
                </header>
                <div className="pd-text">
                  {sec.tokens.map(([op, t], i) => op === 'eq' ? <span key={i}>{t}</span>
                    : op === 'del' ? <del key={i} className="pd-del">{t}</del> : <ins key={i} className="pd-ins">{t}</ins>)}
                </div>
                {sec.changes.length > 0 && (
                  <ul className="pd-notes">
                    {sec.changes.map((c, i) => (
                      <li key={i} className={c.undone ? 'pd-undone' : ''}>
                        <span className="pill">v{c.version}{c.undone ? ' · undone' : ''}</span>{' '}
                        <strong>Why:</strong> {c.why} <strong>How:</strong> {c.how}
                        {c.technique && <span className="muted"> · {c.technique}</span>}
                        {c.feedbackIds.map(id => {
                          const f = fbText(id)
                          return <div key={id} className="muted small">#{id}{f ? `: ${f.text ? `“${f.text}”` : f.tags.join(', ')}${f.deleted ? ' (deleted)' : ''}` : ''}</div>
                        })}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
