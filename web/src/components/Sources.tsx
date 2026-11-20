import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
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

/** All the learner's PDFs: rename, kind, open, delete, and "Learn" (a book goal built on this source).
 * Which goal uses which source is chosen on the goal page (GoalSources). */
export function SourcesTable() {
  const { s, dispatch } = useStore()
  const navigate = useNavigate()
  const [editing, setEditing] = useState<{ id: string; title: string } | null>(null)
  const goalTitle = (id: string) => s.goals.find(g => g.id === id)?.title ?? id
  if (s.sources.length === 0) {
    return <p className="muted">No sources yet. Add a book, article or post as a PDF. Then learn it as a book goal, or use it
      for a goal on that goal's home page.</p>
  }
  const save = () => {
    if (editing) dispatch({ type: 'editSource', id: editing.id, title: editing.title })
    setEditing(null)
  }
  return (
    <table className="table">
      <thead><tr><th>Title</th><th>Kind</th><th>Pages</th><th>Status</th><th>Used in goals</th><th /></tr></thead>
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
          <td className="small">{src.goalIds.length
            ? src.goalIds.map(g => <div key={g} className="src-goal" title={goalTitle(g)}>{goalTitle(g)}</div>)
            : <span className="muted">—</span>}</td>
          <td><div className="row src-actions">
            {src.status === 'error'
              ? <button className="btn btn-small" onClick={() => dispatch({ type: 'rereadSource', id: src.id })}>Read again</button>
              : <button className="btn btn-small btn-primary" disabled={src.status !== 'ready'}
                  title="Make a book goal from this source: its 80/20 core, with its own roadmap"
                  onClick={() => navigate('/goal/book', { state: { sourceIds: [src.id] } })}>Learn</button>}
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

const DRAG = 'text/x-dsc-goal-source'

/** On the goal page: which of the learner's sources this goal uses. Tick a box or drag a source between the lists. */
export function GoalSources() {
  const { s, dispatch } = useStore()
  const [over, setOver] = useState<'used' | 'unused' | null>(null)
  const goal = s.goal
  if (!goal) return null
  const used = s.sources.filter(x => x.goalIds.includes(goal.id))
  const unused = s.sources.filter(x => !x.goalIds.includes(goal.id))
  const set = (id: string, on: boolean) => dispatch({ type: 'linkSource', sourceId: id, goalId: goal.id, on })
  const list = (zone: 'used' | 'unused', items: SourceDoc[], empty: string) => (
    <div className={`src-zone ${over === zone ? 'src-zone-over' : ''}`}
      onDragOver={e => { if (e.dataTransfer.types.includes(DRAG)) { e.preventDefault(); setOver(zone) } }}
      onDragLeave={() => setOver(null)}
      onDrop={e => { e.preventDefault(); setOver(null); const id = e.dataTransfer.getData(DRAG); if (id) set(id, zone === 'used') }}>
      <div className="eyebrow">{zone === 'used' ? `Used for this goal (${items.length})` : `Not used (${items.length})`}</div>
      {items.length === 0 && <p className="muted small">{empty}</p>}
      {items.map(src => (
        <label key={src.id} className="src-item" draggable onDragStart={e => e.dataTransfer.setData(DRAG, src.id)}>
          <span className="src-grip" aria-hidden>⠿</span>
          <input type="checkbox" checked={zone === 'used'} onChange={e => set(src.id, e.target.checked)} />
          <span className="src-name">{src.title}<span className="muted small"> · {src.kind}{src.pages ? `, ${src.pages} p.` : ''}</span></span>
          {src.status !== 'ready' && <SourceStatus src={src} />}
        </label>
      ))}
    </div>
  )
  return (
    <section className="card">
      <div className="row row-between">
        <h2 className="h-small">Sources for this goal</h2>
        <span className="row"><AddSources link label="Add PDF to this goal" /><Link className="btn" to="/library?tab=mine">All sources</Link></span>
      </div>
      <p className="muted small">Research for this goal bases its cards on the pages of the used sources and cites them as
        “Title, p. N”. Tick a box or drag a source between the lists.</p>
      <div className="src-zones">
        {list('used', used, 'Drag a source here, or tick it in the other list.')}
        {list('unused', unused, s.sources.length ? 'All your sources are used.' : 'No sources yet. Add a PDF.')}
      </div>
    </section>
  )
}
