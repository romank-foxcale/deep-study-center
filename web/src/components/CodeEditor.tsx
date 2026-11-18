// An IDE-style Python editor: highlighted code with a transparent text field on top (same font and padding), so the
// learner types into normal text while the colors stay under it. Grows with its code; long lines scroll sideways.

import { useLayoutEffect, useRef } from 'react'
import { highlightPython } from './highlight'

interface Props {
  value: string
  onChange: (code: string) => void
  /** Ctrl/Cmd+Enter */
  onRun?: () => void
  minRows?: number
  label?: string
}

export default function CodeEditor({ value, onChange, onRun, minRows = 1, label = 'Python code' }: Props) {
  const ta = useRef<HTMLTextAreaElement>(null)
  const pre = useRef<HTMLPreElement>(null)

  useLayoutEffect(() => {
    const t = ta.current
    if (!t) return
    t.style.height = 'auto'
    t.style.height = `${Math.max(t.scrollHeight, pre.current?.scrollHeight ?? 0)}px`
  }, [value])

  const lines = Math.max(minRows, value.split('\n').length)
  return (
    <div className="ide">
      <div className="ide-gutter" aria-hidden>{Array.from({ length: lines }, (_, i) => <div key={i}>{i + 1}</div>)}</div>
      <div className="ide-code">
        <pre ref={pre} className="ide-highlight" aria-hidden>
          {highlightPython(value).map((t, i) => <span key={i} className={`tk-${t.kind}`}>{t.text}</span>)}
          {'\n'}
        </pre>
        <textarea ref={ta} className="ide-input" value={value} spellCheck={false} wrap="off" aria-label={label} rows={lines}
          onChange={e => onChange(e.target.value)}
          onScroll={e => { if (pre.current) pre.current.scrollLeft = e.currentTarget.scrollLeft }}
          onKeyDown={e => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && onRun) { e.preventDefault(); onRun() }
            if (e.key === 'Tab') {
              e.preventDefault()
              const t = e.currentTarget, { selectionStart: a, selectionEnd: z } = t
              onChange(value.slice(0, a) + '    ' + value.slice(z))
              requestAnimationFrame(() => { t.selectionStart = t.selectionEnd = a + 4 })
            }
          }} />
      </div>
    </div>
  )
}
