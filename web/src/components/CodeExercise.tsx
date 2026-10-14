import { useState } from 'react'
import type { CodeExercise as Ex } from '../types'
import Markdown from './Markdown'

const PYODIDE_URL = 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js'

interface Pyodide {
  runPythonAsync: (code: string) => Promise<unknown>
  setStdout: (o: { batched: (s: string) => void }) => void
  setStderr: (o: { batched: (s: string) => void }) => void
}
declare global {
  interface Window { loadPyodide?: (opts?: object) => Promise<Pyodide> }
}

let pyodidePromise: Promise<Pyodide> | null = null

/** Loads Pyodide once, on first use (about 10 MB, cached by the browser afterwards). */
function getPyodide(): Promise<Pyodide> {
  if (!pyodidePromise) {
    pyodidePromise = new Promise<void>((resolve, reject) => {
      const s = document.createElement('script')
      s.src = PYODIDE_URL
      s.onload = () => resolve()
      s.onerror = () => reject(new Error('Could not load Pyodide'))
      document.head.appendChild(s)
    }).then(() => window.loadPyodide!())
    pyodidePromise.catch(() => { pyodidePromise = null })
  }
  return pyodidePromise
}

interface Props {
  exercise: Ex
  passed: boolean
  onResult: (passed: boolean) => void
}

export default function CodeExercise({ exercise, passed, onResult }: Props) {
  const [code, setCode] = useState(exercise.starter)
  const [output, setOutput] = useState('')
  const [status, setStatus] = useState<'idle' | 'loading' | 'running'>('idle')

  async function run(withTests: boolean) {
    setStatus(pyodidePromise ? 'running' : 'loading')
    setOutput('')
    try {
      const py = await getPyodide()
      setStatus('running')
      let out = ''
      py.setStdout({ batched: s => { out += s + '\n' } })
      py.setStderr({ batched: s => { out += s + '\n' } })
      await py.runPythonAsync(withTests ? `${code}\n\n${exercise.tests}` : code)
      setOutput(out || '(no output)')
      if (withTests) onResult(true)
    } catch (e) {
      const msg = String(e instanceof Error ? e.message : e)
      // Show only the last line of a Python traceback, which names the failing assertion.
      const last = msg.trim().split('\n').filter(Boolean).pop() ?? msg
      setOutput(last)
      if (withTests) onResult(false)
    } finally {
      setStatus('idle')
    }
  }

  return (
    <div className="exercise">
      <div className="check-label">Exercise · runs in your browser (Pyodide)</div>
      <Markdown>{exercise.prompt}</Markdown>
      <textarea
        className="code-editor"
        value={code}
        spellCheck={false}
        onChange={e => setCode(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Tab') {
            e.preventDefault()
            const t = e.currentTarget, { selectionStart: a, selectionEnd: b } = t
            setCode(code.slice(0, a) + '    ' + code.slice(b))
            requestAnimationFrame(() => { t.selectionStart = t.selectionEnd = a + 4 })
          }
        }}
        rows={Math.max(10, code.split('\n').length + 1)}
      />
      <div className="row">
        <button className="btn" onClick={() => run(false)} disabled={status !== 'idle'}>Run</button>
        <button className="btn btn-primary" onClick={() => run(true)} disabled={status !== 'idle'}>Run tests</button>
        {status === 'loading' && <span className="muted">Loading Python (first run only)…</span>}
        {status === 'running' && <span className="muted">Running…</span>}
        {passed && <span className="pill pill-ok">Passed</span>}
      </div>
      {output && <pre className={`code-output ${/Error/.test(output) ? 'bad' : ''}`}>{output}</pre>}
    </div>
  )
}
