import { useState } from 'react'
import { useStore } from '../store'
import { DictationArea } from '../components/ThinkingInput'

export default function Settings() {
  const { s, dispatch } = useStore()
  const running = (kind: string) => s.jobs.some(j => j.kind === kind && (j.status === 'queued' || j.status === 'running'))
  return (
    <div className="page">
      <h1>Settings</h1>

      <div className="card">
        <h2>Providers</h2>
        <p className="muted small">The app drives the agent CLIs you have installed and logged in, so it uses your subscriptions: no API keys,
          but each plan's rate limits apply. If a routed provider is missing or rate-limited, the job falls back to Claude.</p>
        <table className="table">
          <thead><tr><th>Provider</th><th>CLI</th><th>Status</th></tr></thead>
          <tbody>{s.providers.map(p => (
            <tr key={p.id}>
              <td>{p.id}</td><td><code>{p.cli}</code></td>
              <td>
                {p.detected ? <span className="pill pill-ok">detected</span> : <span className="pill">not found</span>}{' '}
                {!p.implemented && <span className="muted small">adapter coming in milestone 3</span>}
              </td>
            </tr>
          ))}</tbody>
        </table>
      </div>

      <div className="card">
        <h2>Lesson writing</h2>
        <p className="muted small">How a whole lesson is written (a new lesson, a refresh, a new style). One section
          (“Explain differently”) always takes one call.</p>
        <div className="layout-pick" role="radiogroup" aria-label="Lesson writing">
          <fieldset>
            <label><input type="radio" checked={s.settings.lessonWriting === 'steps'} onChange={() => dispatch({ type: 'setSetting', key: 'lessonWriting', value: 'steps' })} />
              <span><strong>In steps</strong> <span className="pill pill-ok small">recommended</span> <span className="muted small">A planner
                chooses each section's angle and what it needs, graphs and quiz questions are made for you, the text is written,
                and a reviewer checks the lesson against your guidelines and feedback (one round of fixes). 4–5 model calls per
                lesson: about 3–5 times the cost and time of one call.</span></span></label>
            <label><input type="radio" checked={s.settings.lessonWriting === 'single'} onChange={() => dispatch({ type: 'setSetting', key: 'lessonWriting', value: 'single' })} />
              <span><strong>One call</strong> <span className="muted small">Only the text writer (“Renditions”). Faster and cheaper; the
                lesson uses the card's graphs and quiz questions, and nothing checks it before you see it.</span></span></label>
          </fieldset>
        </div>
      </div>

      <div className="card">
        <div className="row row-between">
          <h2>Who does what</h2>
          {s.routes.some(r => r.recommended && (r.recommended.provider !== r.provider || r.recommended.model !== r.model)) &&
            <button className="btn btn-small" onClick={() => dispatch({ type: 'useRecommendedRoutes' })}>Use all recommended</button>}
        </div>
        <p className="muted small">The model for each job. Opus is the strongest and slowest; Sonnet is fast and good for long text;
          Haiku is the fastest and cheapest, for simple sorting. “Lesson planner”, “Lesson assets” and “Lesson review” run only when
          lessons are written in steps.</p>
        <table className="table">
          <thead><tr><th>Job</th><th>Provider</th><th>Model</th><th>Recommended</th></tr></thead>
          <tbody>
            {s.routes.map(r => {
              const p = s.providers.find(x => x.id === r.provider)
              return (
                <tr key={r.role}>
                  <td>{r.role}<div className="muted small">{r.description}</div></td>
                  <td>
                    <select className="input input-small" value={r.provider} aria-label={`${r.role} provider`}
                      onChange={e => {
                        const np = s.providers.find(x => x.id === e.target.value)!
                        dispatch({ type: 'route', role: r.role, provider: np.id, model: np.models[0] })
                      }}>
                      {s.providers.map(x => <option key={x.id} value={x.id}>{x.id}</option>)}
                    </select>
                  </td>
                  <td>
                    <select className="input input-small" value={r.model} aria-label={`${r.role} model`}
                      onChange={e => dispatch({ type: 'route', role: r.role, provider: r.provider, model: e.target.value })}>
                      {(p?.models ?? [r.model]).map(m => <option key={m}>{m}</option>)}
                    </select>
                  </td>
                  <td className="rec">
                    {r.recommended && (
                      <>
                        {r.recommended.provider === r.provider && r.recommended.model === r.model
                          ? <span className="pill pill-ok small">{r.recommended.provider} · {r.recommended.model} ✓</span>
                          : <button className="btn btn-small" title="Use the recommended provider and model for this job"
                              disabled={!s.providers.find(x => x.id === r.recommended!.provider)?.detected}
                              onClick={() => dispatch({ type: 'route', role: r.role, provider: r.recommended!.provider, model: r.recommended!.model })}>
                              Use {r.recommended.provider} · {r.recommended.model}</button>}
                        <div className="muted small">{r.recommended.why}</div>
                      </>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <DictationCard />

      <div className="card">
        <h2>Local Python for exercises</h2>
        <p className="muted small">Exercises that need PyTorch run on your machine in a separate environment in your workspace
          ({s.runner.packages.join(', ')}). You review each exercise's test code before it first runs.</p>
        <div className="row" role="radiogroup" aria-label="Where exercises run">
          <label className="row"><input type="radio" checked={s.runner.mode === 'local'} onChange={() => dispatch({ type: 'setRunnerMode', mode: 'local' })} />
            Local environment</label>
          <label className="row"><input type="radio" checked={s.runner.mode === 'docker'} onChange={() => dispatch({ type: 'setRunnerMode', mode: 'docker' })} />
            Docker container (no network, read-only, resource limits)</label>
        </div>
        {s.runner.mode === 'local' && (s.runner.setUp
          ? <span className="pill pill-ok">ready</span>
          : <button className="btn" disabled={running('runner_setup')}
              onClick={() => dispatch({ type: 'setupRunner' })}>Set up (about 1 GB download)</button>)}
        {s.runner.mode === 'docker' && (s.runner.dockerReady
          ? <span className="pill pill-ok">container ready</span>
          : <button className="btn" disabled={running('runner_docker_setup')}
              onClick={() => dispatch({ type: 'setupRunnerDocker' })}>Build the container (CPU PyTorch, large download)</button>)}
      </div>

      <div className="card">
        <h2>Backups</h2>
        <p className="muted small">A copy of your workspace database is made every day while the app runs (the newest 14 are kept), and
          always before a goal is removed. To restore one, stop the app and copy it over <code>study.db</code>.</p>
        <p className="small">Folder: <code>{s.backups.folder}</code><br />
          Last backup: {s.backups.last ? new Date(s.backups.last).toLocaleString() : 'none yet'}</p>
        <button className="btn" onClick={() => dispatch({ type: 'backupNow' })}>Back up now</button>
      </div>

      <div className="card">
        <h2>Goals</h2>
        {s.goals.length === 0 ? <p className="muted">No goals yet.</p> : (
          <ul className="plain">
            {s.goals.map(g => (
              <li key={g.id} className="row row-between">
                <span>{g.title}{g.id === s.goal?.id && <span className="muted small"> · active</span>}</span>
                <button className="btn btn-small" onClick={() => {
                  if (confirm(`Remove "${g.title}" with all its lessons, notes and progress? A backup is made first. Your playbook is kept.`)) dispatch({ type: 'deleteGoal', id: g.id })
                }}>Remove</button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="card">
        <h2>Research</h2>
        <label className="row">
          <input type="checkbox" checked={s.settings.autoResearch}
            onChange={e => dispatch({ type: 'setSetting', key: 'autoResearch', value: e.target.checked })} />
          <span>Research automatically, one module ahead of you</span>
        </label>
        <label className="row">
          <input type="checkbox" checked={s.settings.autoRefresh}
            onChange={e => dispatch({ type: 'setSetting', key: 'autoRefresh', value: e.target.checked })} />
          <span>Re-check cards older than 30 days for errors and better sources (up to 3 a day)</span>
        </label>
        <p className="muted small">Each module's research runs on the provider set for “Research” (with web search) and can take several
          minutes of your plan's usage. Turn this off to research modules only when you click “Research now”.</p>
      </div>

      <div className="card">
        <h2>Recent jobs</h2>
        {s.jobs.length === 0 ? <p className="muted">None yet.</p> : (
          <table className="table">
            <thead><tr><th>Job</th><th>Status</th><th>Details</th></tr></thead>
            <tbody>{s.jobs.map(j => (
              <tr key={j.id}>
                <td>{j.label}</td>
                <td><span className={`pill ${j.status === 'done' ? 'pill-ok' : j.status === 'failed' ? 'pill-bad' : 'pill-warn'}`}>{j.status}</span></td>
                <td className="small">{j.error ?? j.progress.slice(-1)[0] ?? ''}</td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2>Demo data</h2>
        <p className="muted small">Replaces everything in the workspace database with the demo AI roadmap.</p>
        <button className="btn" onClick={() => { if (confirm('Erase all goals, notes, feedback and progress, and load the demo?')) dispatch({ type: 'reset' }) }}>Reset to demo</button>
      </div>
    </div>
  )
}

/** Dictation (SPEC §27): the browser's speech API, or Whisper on this computer. */
function DictationCard() {
  const { s, dispatch } = useStore()
  const [tryText, setTryText] = useState('')
  const d = s.dictation
  const job = (model: string) => s.jobs.find(j => j.kind === 'dictation_model' && (j.status === 'queued' || j.status === 'running')
    && j.label.includes(`(${model})`))
  const failed = s.jobs.find(j => j.kind === 'dictation_model' && j.status === 'failed')
  const browserApi = typeof window !== 'undefined' && ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window)
  return (
    <div className="card">
      <h2>Dictation</h2>
      <p className="muted small">Speak your thinking instead of typing it. The browser's dictation sends your voice to its
        maker's servers (Google for Chrome and Edge). Local dictation keeps your voice on this computer: a Whisper model
        writes down each phrase. It needs a one-time download, then it works offline.</p>
      {!d.available && <p className="error small">Local dictation is not installed: the backend has no faster-whisper package.</p>}
      <div className="row" role="radiogroup" aria-label="Dictation engine">
        <label className="row"><input type="radio" checked={d.mode === 'browser'} onChange={() => dispatch({ type: 'setDictation', mode: 'browser' })} />
          Browser{browserApi ? '' : ' (not available in this browser)'}</label>
        <label className="row"><input type="radio" checked={d.mode === 'local'} disabled={!d.available}
          onChange={() => dispatch({ type: 'setDictation', mode: 'local' })} />
          On this computer (Whisper)</label>
      </div>
      {d.available && (
        <ul className="dictation-models">
          {d.models.map(m => {
            const j = job(m.id)
            return (
              <li key={m.id} className="row">
                <label className="row"><input type="radio" name="dictation-model" checked={d.model === m.id}
                  onChange={() => dispatch({ type: 'setDictation', model: m.id })} />{m.label}</label>
                {m.installed
                  ? <><span className="pill pill-ok small">downloaded</span>
                      <button className="link small" onClick={() => {
                        if (window.confirm(`Delete the ${m.id} model (${m.mb} MB)? You can download it again later.`)) {
                          dispatch({ type: 'removeDictationModel', model: m.id })
                        }
                      }}>Delete</button></>
                  : j
                    ? <span className="muted small">{j.progress[j.progress.length - 1] ?? 'starting the download…'}</span>
                    : <button className="btn btn-small" onClick={() => dispatch({ type: 'downloadDictationModel', model: m.id })}>
                        Download ({m.mb} MB)</button>}
              </li>
            )
          })}
        </ul>
      )}
      {failed && !d.ready && <p className="error small">The last download failed: {failed.error}</p>}
      {d.mode === 'local' && !d.ready && d.available && (
        <p className="small">Download the chosen model to use local dictation. Until then, the browser's dictation is used.</p>
      )}
      {(d.mode === 'browser' ? browserApi : d.ready) && (
        <div className="dictation-try">
          <span className="small muted">Try it: click “Dictate” and say a sentence.</span>
          <DictationArea value={tryText} onChange={setTryText} rows={2} placeholder="Your words appear here." />
        </div>
      )}
    </div>
  )
}
