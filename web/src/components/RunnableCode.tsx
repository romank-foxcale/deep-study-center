// A Python code block inside lesson text that the learner can edit and run in the browser (Pyodide).
// All blocks of one lesson share one namespace, like notebook cells: running a block first runs the earlier blocks
// of the lesson that have not run yet, so names they define (u, v, np, ...) exist.

import { useEffect, useRef, useState } from 'react'
import CodeEditor from './CodeEditor'
import { namespaceFor, pyodideLoaded, resetNamespace, runPython } from './pyodide'

type Status = 'idle' | 'loading' | 'running'

// The blocks of each lesson on the page, in page order, and which of them have run in the current namespace.
interface Block { el: HTMLElement; code: () => string; ran: boolean }
const blocks = new Map<string, Set<Block>>()

function inPageOrder(lesson: string): Block[] {
  return [...(blocks.get(lesson) ?? [])].sort((a, b) =>
    a.el.compareDocumentPosition(b.el) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1)
}

export default function RunnableCode({ source, lesson }: { source: string; lesson: string }) {
  const original = source.replace(/\n$/, '')
  const [code, setCode] = useState(original)
  const [output, setOutput] = useState<{ text: string; error: boolean } | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  const box = useRef<HTMLDivElement>(null)
  const self = useRef<Block | null>(null)
  const current = useRef(code)
  current.current = code

  useEffect(() => {
    const b: Block = { el: box.current!, code: () => current.current, ran: false }
    self.current = b
    const set = blocks.get(lesson) ?? new Set<Block>()
    set.add(b)
    blocks.set(lesson, set)
    return () => { set.delete(b) }
  }, [lesson])

  async function run() {
    setStatus(pyodideLoaded() ? 'running' : 'loading')
    setOutput(null)
    try {
      const ns = await namespaceFor(lesson)
      setStatus('running')
      const all = inPageOrder(lesson)
      for (const b of all.slice(0, all.indexOf(self.current!))) {
        if (!b.ran) {
          try { await runPython(b.code(), ns) } catch { /* an earlier block's own error shows when it is run */ }
          b.ran = true
        }
      }
      const out = await runPython(code, ns)
      self.current!.ran = true
      setOutput({ text: out || '(no output)', error: false })
    } catch (e) {
      setOutput({ text: (e as Error).message, error: true })
    } finally {
      setStatus('idle')
    }
  }

  function restart() {
    resetNamespace(lesson)
    for (const b of blocks.get(lesson) ?? []) b.ran = false
    setCode(original)
    setOutput(null)
  }

  return (
    <div className="runnable" ref={box}>
      <CodeEditor value={code} onChange={setCode} onRun={() => { if (status === 'idle') run() }} label="Python code you can edit and run" />
      <div className="runnable-bar">
        <button className="btn btn-small btn-run" onClick={run} disabled={status !== 'idle'} title="Run (Ctrl+Enter)">▶ Run</button>
        {code !== original && <button className="link small" onClick={() => setCode(original)}>Undo my changes</button>}
        <button className="link small" onClick={restart} title="Forget all variables of this lesson's code and restore this block">Restart</button>
        <span className="muted small">
          {status === 'loading' ? 'Loading Python (first run only, about 10 MB)…' : status === 'running' ? 'Running…' : 'Python · runs in your browser'}
        </span>
      </div>
      {output && <pre className={`code-output ${output.error ? 'bad' : ''}`}>{output.text}</pre>}
    </div>
  )
}
