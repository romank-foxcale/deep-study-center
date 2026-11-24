import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { addLinkSource, uploadSource, useStore } from '../store'
import type { SourceDoc, SourceKind } from '../types'

// The learner's sources (SPEC §17, §40): PDF files and links, with a type, a status, a filter and a duplicate check.

export const KINDS: { id: SourceKind; label: string }[] = [
  { id: 'book', label: 'Book' }, { id: 'article', label: 'Article' }, { id: 'web', label: 'Internet source' },
  { id: 'video', label: 'Video' }, { id: 'custom', label: 'Custom' },
]
export const kindLabel = (k: string) => KINDS.find(x => x.id === k)?.label ?? k

/** The status the learner sees: error (red), uploading (gray), uploaded (yellow), ready (green: its lessons are made). */
export function sourceStatus(src: SourceDoc): { label: string; cls: string; title: string } {
  if (src.status === 'error') return { label: 'error', cls: 'pill pill-bad', title: src.url ? 'The link could not be read. Click "Read again".' : 'The file could not be read. Click "Read again".' }
  if (src.status === 'no_text') return { label: 'error: no text', cls: 'pill pill-bad', title: src.url ? 'No text was found on this page, or the video has no captions.' : 'A scanned PDF without a text layer. DSC cannot read it.' }
  if (src.status === 'reading') return src.url ? { label: 'reading', cls: 'pill', title: 'The page text or the video captions are being read' } : { label: 'uploading', cls: 'pill', title: 'The pages are being read' }
  if (src.mapped) return { label: 'ready', cls: 'pill pill-ok', title: '"Teach me this" made its lessons' }
  return { label: src.url ? 'read' : 'uploaded', cls: 'pill pill-warn', title: 'Read. Use "Teach me this" to make its lessons.' }
}

export function SourceStatus({ src }: { src: SourceDoc }) {
  const st = sourceStatus(src)
  return <span className={st.cls} title={st.title}>{st.label}</span>
}

/** Where a click on the title goes: the PDF, or the link (a web page, a video). */
export const sourceUrl = (src: SourceDoc) => src.url || `/api/sources/${src.id}/file`

const norm = (t: string) => t.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()

/** Search words and the chosen types. A source matches when every word is in its title, author, file name, address
 *  or type. */
export interface SourceQuery { text: string; kinds: SourceKind[] }
export const EMPTY_QUERY: SourceQuery = { text: '', kinds: [] }
export function matches(q: SourceQuery, kind: string, ...fields: string[]): boolean {
  if (q.kinds.length && !q.kinds.includes(kind as SourceKind)) return false
  const hay = norm([...fields, kindLabel(kind)].join(' '))
  return norm(q.text).split(' ').filter(Boolean).every(w => hay.includes(w))
}

/** The search box and the type chips (Books and Sources pages). */
export function SourceFilter({ q, onChange, counts }: { q: SourceQuery; onChange: (q: SourceQuery) => void; counts?: Partial<Record<SourceKind, number>> }) {
  const toggle = (k: SourceKind) => onChange({ ...q, kinds: q.kinds.includes(k) ? q.kinds.filter(x => x !== k) : [...q.kinds, k] })
  return (
    <div className="src-filter" role="search">
      <input className="input" type="search" placeholder="Search by title, author, file name or link" aria-label="Search sources"
        value={q.text} onChange={e => onChange({ ...q, text: e.target.value })} />
      <div className="row" role="group" aria-label="Type">
        {KINDS.map(k => (
          <button key={k.id} className={`chip ${q.kinds.includes(k.id) ? 'on' : ''}`} aria-pressed={q.kinds.includes(k.id)} onClick={() => toggle(k.id)}>
            {k.label}{counts?.[k.id] != null ? <span className="muted"> {counts[k.id]}</span> : null}</button>
        ))}
        {(q.kinds.length > 0 || q.text) && <button className="link small" onClick={() => onChange(EMPTY_QUERY)}>Clear</button>}
      </div>
    </div>
  )
}

async function sha256(file: File): Promise<string> {
  const d = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
  return [...new Uint8Array(d)].map(b => b.toString(16).padStart(2, '0')).join('')
}
const titleOf = (name: string) => name.replace(/\.pdf$/i, '').replace(/[_-]+/g, ' ').trim()
const isVideo = (url: string) => /(^|\.)(youtube\.com|youtu\.be|vimeo\.com)$/i.test((() => { try { return new URL(url).hostname } catch { return '' } })())

/** "Add source": a dialog for a PDF file or a link, with a name, a type, a duplicate check and the upload progress. */
export function AddSources({ link = false, onAdded, label = 'Add source' }: { link?: boolean; onAdded?: (ids: string[]) => void; label?: string }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button className="btn" onClick={() => setOpen(true)}>{label}</button>
      {open && <AddSourceDialog link={link} onClose={() => setOpen(false)} onAdded={onAdded} />}
    </>
  )
}

function AddSourceDialog({ link, onClose, onAdded }: { link: boolean; onClose: () => void; onAdded?: (ids: string[]) => void }) {
  const { s, reload } = useStore()
  const input = useRef<HTMLInputElement>(null)
  const [mode, setMode] = useState<'file' | 'link'>('file')
  const [file, setFile] = useState<File | null>(null)
  const [hash, setHash] = useState<string | null>(null)
  const [url, setUrl] = useState('')
  const [title, setTitle] = useState('')
  const [kind, setKind] = useState<SourceKind>('book')
  const [progress, setProgress] = useState<number | null>(null)
  const [error, setError] = useState('')

  const pick = async (f: File | undefined) => {
    setError(''); setHash(null)
    if (!f) return
    setFile(f); setTitle(titleOf(f.name))
    setHash(await sha256(f).catch(() => ''))
  }
  const sameFile = hash ? s.sources.find(x => x.sha256 && x.sha256 === hash) : undefined
  const sameLink = mode === 'link' && url.trim() ? s.sources.find(x => x.url && x.url === url.trim()) : undefined
  const sameName = title.trim() ? s.sources.find(x => norm(x.title) === norm(title)) : undefined
  const blocked = mode === 'file' ? (!file || hash === null || !!sameFile) : (!/^https?:\/\/\S+$/i.test(url.trim()) || !!sameLink)
  const busy = progress !== null

  const submit = async () => {
    if (blocked || busy) return
    if (sameName && !window.confirm(`A source named “${sameName.title}” already exists. Add this one too?`)) return
    setError(''); setProgress(0)
    const before = new Set(s.sources.map(x => x.id))
    try {
      const next = mode === 'file'
        ? await uploadSource(file!, { kind, title: title.trim(), link, onProgress: setProgress })
        : await addLinkSource({ url: url.trim(), title: title.trim(), kind })
      onAdded?.(next.sources.filter(x => !before.has(x.id)).map(x => x.id))
      await reload()
      onClose()
    } catch (e) {
      setError((e as Error).message); setProgress(null)
    }
  }

  return (
    <div className="modal-backdrop" onClick={e => { if (e.target === e.currentTarget && !busy) onClose() }}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="add-src-title"
        onKeyDown={e => { if (e.key === 'Escape' && !busy) onClose() }}>
        <div className="modal-head"><h3 id="add-src-title">Add a source</h3>
          <p className="muted small">A PDF (a book, an article, a document), or a link to a web page or a video.</p></div>
        <div className="tabs tabs-inline" role="tablist">
          <button role="tab" aria-selected={mode === 'file'} className={`tab ${mode === 'file' ? 'on' : ''}`} disabled={busy}
            onClick={() => { setMode('file'); setKind('book'); setTitle(file ? titleOf(file.name) : '') }}>PDF file</button>
          <button role="tab" aria-selected={mode === 'link'} className={`tab ${mode === 'link' ? 'on' : ''}`} disabled={busy}
            onClick={() => { setMode('link'); setKind(isVideo(url) ? 'video' : 'web'); setTitle('') }}>Link</button>
        </div>
        {mode === 'file' ? (
          <div className="field">
            <input ref={input} type="file" accept="application/pdf,.pdf" hidden onChange={e => pick(e.target.files?.[0])} />
            <div className="row">
              <button className="btn" disabled={busy} onClick={() => input.current?.click()}>{file ? 'Choose another file' : 'Choose a PDF'}</button>
              {file && <span className="small">{file.name} · {(file.size / 1048576).toFixed(1)} MB</span>}
            </div>
            {file && hash === null && <span className="muted small">Checking for a duplicate…</span>}
            {sameFile && <span className="error small">This file is already in your sources as “{sameFile.title}”.</span>}
          </div>
        ) : (
          <label className="field"><span className="small">Address</span>
            <input className="input" type="url" placeholder="https://…" value={url} disabled={busy} autoFocus
              onChange={e => { setUrl(e.target.value); if (isVideo(e.target.value)) setKind('video') }} />
            {sameLink && <span className="error small">This link is already in your sources as “{sameLink.title}”.</span>}
          </label>
        )}
        <label className="field"><span className="small">Name</span>
          <input className="input" value={title} disabled={busy} placeholder={mode === 'link' ? 'The page or video title' : ''}
            onChange={e => setTitle(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') submit() }} />
          {sameName && !sameFile && !sameLink && <span className="warn small">A source with this name already exists. Check that it is not the same.</span>}
        </label>
        <label className="field"><span className="small">Type</span>
          <select className="input" value={kind} disabled={busy} onChange={e => setKind(e.target.value as SourceKind)}>
            {KINDS.map(k => <option key={k.id} value={k.id}>{k.label}</option>)}
          </select>
        </label>
        {progress !== null && mode === 'file' && (
          <div className="upload-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)}>
            <i style={{ width: `${Math.round(progress * 100)}%` }} /><span className="small">{progress < 1 ? `Uploading… ${Math.round(progress * 100)}%` : 'Saving…'}</span>
          </div>
        )}
        {error && <span className="error small">{error}</span>}
        <div className="row row-end">
          <button className="btn" disabled={busy} onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={blocked || busy} onClick={submit}>{mode === 'file' ? 'Upload' : 'Add link'}</button>
        </div>
      </div>
    </div>
  )
}

/** All the learner's sources: open, type, status, rename, delete, and "Teach me this book" for a PDF. */
export function SourcesTable({ q }: { q: SourceQuery }) {
  const { s, dispatch } = useStore()
  const navigate = useNavigate()
  const [editing, setEditing] = useState<{ id: string; title: string } | null>(null)
  const [waiting, setWaiting] = useState<string | null>(null)
  if (s.sources.length === 0) {
    return <p className="muted">No sources yet. Add a book, an article or a document as a PDF, or a link to a web page or a video.</p>
  }
  const rows = s.sources.filter(x => matches(q, x.kind, x.title, x.author, x.filename, x.url))
  if (rows.length === 0) return <p className="muted">No source matches the search.</p>
  const save = () => {
    if (editing) dispatch({ type: 'editSource', id: editing.id, title: editing.title })
    setEditing(null)
  }
  const bookOf = (id: string) => s.studyBooks.find(b => b.sourceId === id)
  const teach = async (id: string) => {
    setWaiting(id)
    if (await dispatch({ type: 'studyBook', sourceId: id })) navigate('/books')
    setWaiting(null)
  }
  return (
    <table className="table">
      <thead><tr><th>Title</th><th>Type</th><th>Pages</th><th>Status</th><th /></tr></thead>
      <tbody>{rows.map(src => {
        const book = bookOf(src.id)
        return (
          <tr key={src.id}>
            <td>
              {editing?.id === src.id
                ? <input className="input" autoFocus value={editing.title} onChange={e => setEditing({ ...editing, title: e.target.value })}
                    onBlur={save} onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') setEditing(null) }} />
                : <a href={sourceUrl(src)} target="_blank" rel="noreferrer" title={src.url ? `Open ${src.url}` : 'Open the PDF'}>{src.title}</a>}
              <div className="muted small src-sub">{[src.author, src.outline ? `${src.outline} chapters` : '', src.url ? src.url : ''].filter(Boolean).join(' · ') || src.filename}</div>
            </td>
            <td>
              <select className="input input-small" value={src.kind} aria-label={`Type of ${src.title}`}
                onChange={e => dispatch({ type: 'editSource', id: src.id, kind: e.target.value as SourceKind })}>
                {KINDS.map(k => <option key={k.id} value={k.id}>{k.label}</option>)}
              </select>
            </td>
            <td>{src.pages || '—'}</td>
            <td><SourceStatus src={src} /></td>
            <td><div className="row src-actions">
              {src.status === 'error' && <button className="btn btn-small" onClick={() => dispatch({ type: 'rereadSource', id: src.id })}>Read again</button>}
              {book && <Link className="btn btn-small btn-primary" to={`/book/${book.id}`}>Open</Link>}
              {!book && (src.url ? src.status !== 'no_text' && src.status !== 'error' : src.status === 'ready') && (
                <button className="btn btn-small btn-primary" disabled={waiting !== null} onClick={() => teach(src.id)}>
                  {waiting === src.id || (src.url && src.status === 'reading') ? 'Reading…' : 'Teach me this'}</button>
              )}
              <button className="btn btn-small" onClick={() => setEditing({ id: src.id, title: src.title })}>Rename</button>
              <DeleteSource src={src} />
            </div></td>
          </tr>
        )
      })}</tbody>
    </table>
  )
}

/** A trash-can button that deletes a source (and its lessons plan, when it was taught as a book). */
export function DeleteSource({ src, icon = false }: { src: SourceDoc; icon?: boolean }) {
  const { s, dispatch } = useStore()
  const book = s.studyBooks.find(b => b.sourceId === src.id)
  const go = (e: React.MouseEvent) => {
    e.preventDefault(); e.stopPropagation()
    const what = src.url ? 'The link is removed.' : book
      ? 'The PDF and its book (chapters and lessons) are removed. What you learned stays on the map.'
      : 'The PDF and its pages are removed.'
    if (window.confirm(`Delete “${src.title}”? ${what}`)) dispatch({ type: 'deleteSource', id: src.id })
  }
  return icon
    ? <button className="icon-btn" onClick={go} aria-label={`Delete ${src.title}`} title="Delete"><TrashIcon /></button>
    : <button className="btn btn-small" onClick={go}>Delete</button>
}

export const TrashIcon = () => (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />
  </svg>
)
