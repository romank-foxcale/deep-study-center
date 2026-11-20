import { useRef, useState } from 'react'
import { uploadSource, useStore } from '../store'
import type { SourceDoc } from '../types'

const KINDS: SourceDoc['kind'][] = ['book', 'article', 'post', 'other']
const STATUS: Record<SourceDoc['status'], { label: string; cls: string; title: string }> = {
  reading: { label: 'reading…', cls: 'pill', title: 'The text of each page is read in the background' },
  ready: { label: 'ready', cls: 'pill pill-ok', title: 'Research can use and cite its pages' },
  no_text: { label: 'no text', cls: 'pill pill-warn', title: 'A scanned PDF without a text layer. Research cannot read it.' },
  error: { label: 'error', cls: 'pill pill-warn', title: 'The file could not be read. Click "Read again".' },
}

/** "Add PDF" button. Uploads one or more PDFs; calls onAdded with the new source ids. */
export function AddSources({ link, onAdded, label = 'Add PDF' }: { link: boolean; onAdded?: (ids: string[]) => void; label?: string }) {
  const { s, reload } = useStore()
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pick = async (files: FileList | null) => {
    if (!files?.length) return
    setBusy(true); setError('')
    const before = new Set(s.sources.map(x => x.id))
    let added: string[] = []
    try {
      for (const f of Array.from(files)) {
        const next = await uploadSource(f, { link })
        added = next.sources.filter(x => !before.has(x.id)).map(x => x.id)
      }
      onAdded?.(added)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
      await reload()
    }
  }
  return (
    <span className="row">
      <input ref={input} type="file" accept="application/pdf,.pdf" multiple hidden onChange={e => pick(e.target.files)} />
      <button className="btn" disabled={busy} onClick={() => input.current?.click()}>{busy ? 'Uploading…' : label}</button>
      {error && <span className="error small">{error}</span>}
    </span>
  )
}

export function SourceStatus({ src }: { src: SourceDoc }) {
  const st = STATUS[src.status] ?? STATUS.error
  return <span className={st.cls} title={st.title}>{st.label}</span>
}

/** The learner's PDFs: rename, kind, use for the current goal, open, delete. */
export function SourcesTable() {
  const { s, dispatch } = useStore()
  const [editing, setEditing] = useState<{ id: string; title: string } | null>(null)
  const goalId = s.goal?.id
  if (s.sources.length === 0) {
    return <p className="muted">No sources yet. Add a book, article or post as a PDF. Research then bases its cards on the
      pages that match each step, and cites them with a page number.</p>
  }
  const save = () => {
    if (editing) dispatch({ type: 'editSource', id: editing.id, title: editing.title })
    setEditing(null)
  }
  return (
    <table className="table">
      <thead><tr><th>Title</th><th>Kind</th><th>Pages</th><th>Status</th>{goalId && <th>Use for this goal</th>}<th /></tr></thead>
      <tbody>{s.sources.map(src => (
        <tr key={src.id}>
          <td>
            {editing?.id === src.id
              ? <input className="input" autoFocus value={editing.title} onChange={e => setEditing({ ...editing, title: e.target.value })}
                  onBlur={save} onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') setEditing(null) }} />
              : <a href={`/api/sources/${src.id}/file`} target="_blank" rel="noreferrer">{src.title}</a>}
            <div className="muted small">{[src.author, src.outline ? `${src.outline} chapters` : ''].filter(Boolean).join(' · ') || src.filename}</div>
          </td>
          <td>
            <select className="input input-small" value={src.kind} onChange={e => dispatch({ type: 'editSource', id: src.id, kind: e.target.value as SourceDoc['kind'] })}>
              {KINDS.map(k => <option key={k} value={k}>{k}</option>)}
            </select>
          </td>
          <td>{src.pages || '—'}</td>
          <td><SourceStatus src={src} /></td>
          {goalId && <td><input type="checkbox" aria-label={`Use ${src.title} for this goal`} checked={src.goalIds.includes(goalId)}
            onChange={e => dispatch({ type: 'linkSource', sourceId: src.id, goalId, on: e.target.checked })} /></td>}
          <td><div className="row">
            {src.status === 'error' && <button className="btn btn-small" onClick={() => dispatch({ type: 'rereadSource', id: src.id })}>Read again</button>}
            <button className="btn btn-small" onClick={() => setEditing({ id: src.id, title: src.title })}>Rename</button>
            <button className="btn btn-small" onClick={() => {
              if (window.confirm(`Delete “${src.title}”? The PDF and its pages are removed. Cards that cite it keep their text.`)) {
                dispatch({ type: 'deleteSource', id: src.id })
              }
            }}>Delete</button>
          </div></td>
        </tr>
      ))}</tbody>
    </table>
  )
}
