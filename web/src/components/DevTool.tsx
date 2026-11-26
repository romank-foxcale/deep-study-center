// Developer tool (only when the app runs from its source code): select an element or an area of the app,
// write a comment, and a coding agent (Claude Code, in the repository) changes the source code.
// Start: Alt+D or "Comment on the UI" in the sidebar. Click = one element; drag = an area. Esc stops.
import { useCallback, useEffect, useRef, useState } from 'react'
import { PICK_EVENT, fetchInfo, type DevInfo } from './devtoolApi'

type Rect = { left: number; top: number; width: number; height: number }
type Target = Record<string, unknown> & { kind: 'element' | 'area'; rect: Rect }

// ---------------------------------------------------------------- what was selected

const isDevUi = (el: Element | null) => !!el?.closest('[data-devtool]')

function rectOf(el: Element): Rect {
  const r = el.getBoundingClientRect()
  return { left: r.left, top: r.top, width: r.width, height: r.height }
}

/** React component names around a DOM node (from React's internal fiber; best in dev builds). */
function componentsOf(el: Element): string[] {
  const key = Object.keys(el).find(k => k.startsWith('__reactFiber$'))
  type Fiber = { type?: unknown; return?: Fiber | null }
  let f = key ? (el as unknown as Record<string, Fiber>)[key] : null
  const names: string[] = []
  while (f && names.length < 6) {
    const t = f.type as { displayName?: string; name?: string; type?: { name?: string }; render?: { name?: string } } | string | undefined
    if (t && typeof t !== 'string') {
      const n = t.displayName || t.name || t.type?.name || t.render?.name
      if (n && /^[A-Z]/.test(n) && !names.includes(n)) names.push(n)
    }
    f = f.return ?? null
  }
  return names
}

function cssPath(el: Element): string {
  const parts: string[] = []
  for (let e: Element | null = el; e && e !== document.body && parts.length < 7; e = e.parentElement) {
    let p = e.tagName.toLowerCase()
    if (e.id) { parts.unshift(`${p}#${e.id}`); break }
    const cls = [...e.classList].slice(0, 3).join('.')
    if (cls) p += `.${cls}`
    const sibs = e.parentElement ? [...e.parentElement.children].filter(c => c.tagName === e!.tagName) : []
    if (sibs.length > 1) p += `:nth-of-type(${sibs.indexOf(e) + 1})`
    parts.unshift(p)
  }
  return parts.join(' > ')
}

function textOf(el: Element, n: number): string {
  return ((el as HTMLElement).innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, n)
}

function describe(el: Element, full: boolean) {
  const attrs: Record<string, string> = {}
  for (const a of el.attributes) {
    if (a.name.startsWith('data-') || ['aria-label', 'title', 'href', 'role', 'type', 'name', 'placeholder'].includes(a.name)) attrs[a.name] = a.value.slice(0, 200)
  }
  return {
    tag: el.tagName.toLowerCase(), id: el.id || undefined, classes: [...el.classList], text: textOf(el, full ? 400 : 120),
    attributes: attrs, components: componentsOf(el), cssPath: cssPath(el),
    ...(full ? { html: el.outerHTML.slice(0, 1500), rect: rectOf(el) } : {}),
  }
}

function elementAt(x: number, y: number): Element | null {
  return document.elementsFromPoint(x, y).find(e => !isDevUi(e) && e !== document.documentElement && e !== document.body) ?? null
}

/** The outermost elements fully inside the area (not their children), at most 15. */
function elementsIn(r: Rect): Element[] {
  const inside = (e: Element) => {
    const b = e.getBoundingClientRect()
    return b.width > 0 && b.height > 0 && b.left >= r.left - 2 && b.top >= r.top - 2 &&
      b.right <= r.left + r.width + 2 && b.bottom <= r.top + r.height + 2
  }
  const found: Element[] = []
  const walk = (e: Element) => {
    for (const c of e.children) {
      if (isDevUi(c)) continue
      if (inside(c)) { found.push(c) } else walk(c)
      if (found.length >= 15) return
    }
  }
  walk(document.body)
  return found
}

// ---------------------------------------------------------------- the tool

type Mode = { kind: 'off' } | { kind: 'pick' } | { kind: 'comment'; target: Target }

export default function DevTool() {
  const [info, setInfo] = useState<DevInfo | null>(null)
  const [mode, setMode] = useState<Mode>({ kind: 'off' })
  const [hover, setHover] = useState<Rect | null>(null)
  const [drag, setDrag] = useState<Rect | null>(null)
  const [comment, setComment] = useState('')
  const [sendError, setSendError] = useState('')
  const [open, setOpen] = useState(true)
  const start = useRef<{ x: number; y: number } | null>(null)
  const modeRef = useRef<Mode['kind']>('off')
  useEffect(() => { modeRef.current = mode.kind }, [mode.kind])

  const refresh = useCallback(() => fetchInfo().then(i => i && setInfo(i)), [])
  useEffect(() => { refresh() }, [refresh])

  const busy = info?.tasks.some(t => t.status === 'queued' || t.status === 'running') ?? false
  useEffect(() => {
    if (!busy) return
    const t = setInterval(refresh, 1500)
    return () => clearInterval(t)
  }, [busy, refresh])

  const stop = useCallback(() => { setMode({ kind: 'off' }); setHover(null); setDrag(null); start.current = null; setSendError('') }, [])

  useEffect(() => {
    if (!info?.enabled) return
    const onPick = () => { setComment(''); setMode({ kind: 'pick' }) }
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey && !e.ctrlKey && !e.metaKey && e.code === 'KeyD') {
        e.preventDefault()
        setMode(m => (m.kind === 'off' ? { kind: 'pick' } : { kind: 'off' }))
        setComment(''); setHover(null); setDrag(null)
      } else if (e.key === 'Escape' && modeRef.current !== 'off') {
        e.preventDefault()
        setMode({ kind: 'off' }); setHover(null); setDrag(null)
      }
    }
    window.addEventListener(PICK_EVENT, onPick)
    window.addEventListener('keydown', onKey, true)
    return () => { window.removeEventListener(PICK_EVENT, onPick); window.removeEventListener('keydown', onKey, true) }
  }, [info?.enabled])

  if (!info?.enabled) return null

  const onMove = (e: React.MouseEvent) => {
    if (start.current) {
      const s = start.current
      const r = { left: Math.min(s.x, e.clientX), top: Math.min(s.y, e.clientY), width: Math.abs(e.clientX - s.x), height: Math.abs(e.clientY - s.y) }
      if (r.width > 6 || r.height > 6) { setDrag(r); setHover(null); return }
    }
    const el = elementAt(e.clientX, e.clientY)
    setHover(el ? rectOf(el) : null)
  }
  const onDown = (e: React.MouseEvent) => { e.preventDefault(); start.current = { x: e.clientX, y: e.clientY } }
  const onUp = (e: React.MouseEvent) => {
    e.preventDefault()
    start.current = null
    if (drag && (drag.width > 6 || drag.height > 6)) {
      const els = elementsIn(drag)
      const centre = elementAt(drag.left + drag.width / 2, drag.top + drag.height / 2)
      setMode({ kind: 'comment', target: { kind: 'area', rect: drag, elements: els.map(x => describe(x, false)), atCentre: centre ? describe(centre, false) : null } })
    } else {
      const el = elementAt(e.clientX, e.clientY)
      if (!el) return
      setMode({ kind: 'comment', target: { kind: 'element', ...describe(el, true), rect: rectOf(el) } })
    }
    setDrag(null); setHover(null)
  }

  const send = async () => {
    if (mode.kind !== 'comment' || !comment.trim()) return
    setSendError('')
    const r = await fetch('/api/dev/change', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ comment, target: mode.target, page: location.pathname + location.search, title: document.title,
        viewport: { width: innerWidth, height: innerHeight } }),
    })
    if (!r.ok) { setSendError((await r.json().catch(() => null))?.detail ?? `Error ${r.status}`); return }
    setInfo(await r.json()); setOpen(true); stop(); setComment('')
  }

  const box = (r: Rect, cls: string) => <div className={cls} style={{ left: r.left, top: r.top, width: r.width, height: r.height }} />
  const sel = mode.kind === 'comment' ? mode.target.rect : null
  const popLeft = sel ? Math.min(Math.max(8, sel.left), innerWidth - 376) : 0
  const popTop = sel ? (sel.top + sel.height + 220 < innerHeight ? sel.top + sel.height + 8 : Math.max(8, sel.top - 212)) : 0

  return (
    <div data-devtool>
      {mode.kind === 'pick' && (
        <div className="dev-catcher" onMouseMove={onMove} onMouseDown={onDown} onMouseUp={onUp} onMouseLeave={() => setHover(null)}>
          <div className="dev-hint">Click an element or drag an area. <kbd>Esc</kbd> stops.</div>
        </div>
      )}
      {hover && mode.kind === 'pick' && box(hover, 'dev-box')}
      {drag && box(drag, 'dev-box dev-box-area')}
      {sel && box(sel, 'dev-box dev-box-chosen')}
      {mode.kind === 'comment' && (
        <div className="dev-pop card" style={{ left: popLeft, top: popTop }}>
          <div className="eyebrow">Change this {mode.target.kind}</div>
          <textarea className="input" rows={4} autoFocus value={comment} onChange={e => setComment(e.target.value)}
            placeholder="What must change here?" onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) send() }} />
          {!info.agent && <div className="small bad">The claude CLI is not on PATH: the request will fail.</div>}
          {sendError && <div className="small bad">{sendError}</div>}
          <div className="dev-pop-actions">
            <span className="muted small">Ctrl+Enter sends. Claude Code ({info.model}) edits the code.</span>
            <button className="btn btn-small" onClick={stop}>Cancel</button>
            <button className="btn btn-small btn-primary" disabled={!comment.trim()} onClick={send}>Send</button>
          </div>
        </div>
      )}
      {info.tasks.length > 0 && (
        <div className="dev-panel card">
          <button className="dev-panel-head link" onClick={() => setOpen(o => !o)}>
            Developer requests {busy ? '· working…' : ''} <span className="muted">{open ? '▾' : '▸'}</span>
          </button>
          {open && info.tasks.slice(0, 6).map(t => <TaskRow key={t.id} t={t} servesBuilt={info.servesBuilt} />)}
        </div>
      )}
    </div>
  )
}

function TaskRow({ t, servesBuilt }: { t: DevInfo['tasks'][number]; servesBuilt: boolean }) {
  const [more, setMore] = useState(false)
  const last = t.progress[t.progress.length - 1]
  return (
    <div className={`dev-task dev-task-${t.status}`}>
      <div className="dev-task-top">
        <span className="pill">{t.status}</span>
        <span className="dev-task-comment" title={t.comment}>{t.comment}</span>
        <button className="link small" onClick={() => setMore(m => !m)}>{more ? 'less' : 'more'}</button>
      </div>
      <div className="muted small">{t.page} · {t.target}</div>
      {(t.status === 'running' || t.status === 'queued') && last && <div className="muted small">{last}</div>}
      {t.error && <pre className="dev-task-error small">{t.error}</pre>}
      {t.status === 'done' && servesBuilt && t.changed.some(p => p.startsWith('web/')) &&
        <button className="btn btn-small" onClick={() => location.reload()}>Reload the page</button>}
      {more && (
        <div className="small">
          {t.summary && <p className="dev-task-summary">{t.summary}</p>}
          {t.changed.length > 0 && <div>Changed: {t.changed.map(p => <code key={p}>{p} </code>)}</div>}
          {t.progress.length > 0 && <ul className="muted">{t.progress.map((p, i) => <li key={i}>{p}</li>)}</ul>}
        </div>
      )}
    </div>
  )
}
