import { useState } from 'react'
import { jobActive, runLocal, useStore } from '../store'
import type { Angle, CodeExercise, RunResult } from '../types'
import Markdown from './Markdown'

interface Props {
  conceptId: string
  exercise: CodeExercise
  angle: Angle
  passed: boolean
}

/** Exercise that runs on the learner's machine (e.g. PyTorch), after they review the test code. */
export default function LocalExercise({ conceptId, exercise, angle, passed }: Props) {
  const { s, dispatch, reload } = useStore()
  const [code, setCode] = useState(exercise.starter)
  const [result, setResult] = useState<RunResult | null>(null)
  const [busy, setBusy] = useState(false)
  const settingUp = jobActive(s, 'runner_setup')

  async function run(approve = false) {
    setBusy(true)
    try {
      const r = await runLocal({ conceptId, itemId: exercise.id, code, angle, approve })
      setResult(r)
      if (r.status === 'ran') reload()  // the server recorded the evidence
    } catch (e) {
      setResult({ status: 'blocked', problems: [(e as Error).message] })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="exercise">
      <div className="check-label">Exercise · runs on your machine ({s.runner.packages.join(', ')})</div>
      <Markdown>{exercise.prompt}</Markdown>
      <textarea className="code-editor" value={code} spellCheck={false} onChange={e => setCode(e.target.value)}
        rows={Math.max(10, code.split('\n').length + 1)} />
      <div className="row">
        <button className="btn btn-primary" onClick={() => run()} disabled={busy || settingUp}>Run tests</button>
        {busy && <span className="muted">Running…</span>}
        {passed && <span className="pill pill-ok">Passed</span>}
      </div>

      {result?.status === 'needs_setup' && (
        <div className="banner">
          <span>{settingUp ? 'Setting up local Python (numpy, torch)… this is a large download and can take several minutes.'
            : 'This exercise needs a local Python environment with PyTorch (about 1 GB download, one time).'}</span>
          {!settingUp && <button className="btn btn-primary" onClick={() => dispatch({ type: 'setupRunner' })}>Set it up</button>}
          {!settingUp && s.runner.setUp && <button className="btn" onClick={() => run()}>Run now</button>}
        </div>
      )}
      {result?.status === 'needs_approval' && (
        <div className="approval">
          <p><strong>Review the test code before it runs on your computer.</strong> It was written by an agent from web research.
            It runs together with your code, in a separate environment without network-related or file-system imports,
            but it is not a sandbox. Run it only if it looks like plain checks.</p>
          <pre className="code-output">{result.tests}</pre>
          <div className="row">
            <button className="btn btn-primary" onClick={() => run(true)}>Looks fine, approve and run</button>
            <button className="btn" onClick={() => setResult(null)}>Cancel</button>
          </div>
        </div>
      )}
      {result?.status === 'blocked' && (
        <pre className="code-output bad">{'Not run:\n' + result.problems.join('\n')}</pre>
      )}
      {result?.status === 'ran' && (
        <pre className={`code-output ${result.passed ? '' : 'bad'}`}>{result.output}</pre>
      )}
    </div>
  )
}
