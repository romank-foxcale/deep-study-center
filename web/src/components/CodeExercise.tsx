import { useState } from 'react'
import type { CodeExercise as Ex } from '../types'
import CodeEditor from './CodeEditor'
import Markdown from './Markdown'
import { pyodideLoaded, runPython } from './pyodide'

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
    setStatus(pyodideLoaded() ? 'running' : 'loading')
    setOutput('')
    try {
      const out = await runPython(withTests ? `${code}\n\n${exercise.tests}` : code)
      setOutput(out || '(no output)')
      if (withTests) onResult(true)
    } catch (e) {
      setOutput((e as Error).message)  // the last traceback line names the failing assertion
      if (withTests) onResult(false)
    } finally {
      setStatus('idle')
    }
  }

  return (
    <div className="exercise">
      <div className="check-label">Exercise · runs in your browser (Pyodide)</div>
      <Markdown>{exercise.prompt}</Markdown>
      <CodeEditor value={code} onChange={setCode} onRun={() => { if (status === 'idle') run(false) }} minRows={8} label="Exercise code" />
      <div className="row">
        <button className="btn btn-run" onClick={() => run(false)} disabled={status !== 'idle'} title="Run (Ctrl+Enter)">▶ Run</button>
        <button className="btn btn-primary" onClick={() => run(true)} disabled={status !== 'idle'}>Run tests</button>
        {status === 'loading' && <span className="muted">Loading Python (first run only)…</span>}
        {status === 'running' && <span className="muted">Running…</span>}
        {passed && <span className="pill pill-ok">Passed</span>}
      </div>
      {output && <pre className={`code-output ${/Error/.test(output) ? 'bad' : ''}`}>{output}</pre>}
    </div>
  )
}
