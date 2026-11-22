import { useState } from 'react'
import { useStore } from '../store'

/** The learner's Anthropic API key (SPEC §25): stored in the system keychain by the backend, never shown again. */
export default function ApiKeyCard({ compact }: { compact?: boolean }) {
  const { s, dispatch } = useStore()
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true)
    if (await dispatch({ type: 'setApiKey', key })) setKey('')
    setBusy(false)
  }
  const onApi = s.routes.filter(r => r.provider === 'anthropic').length
  return (
    <div className="card">
      <h2>{compact ? 'Connect a model' : 'Anthropic API key'}</h2>
      <p className="muted small">
        {compact ? 'DSC needs a model to research, write lessons and check your answers. ' : ''}
        Use the Claude CLI with your subscription (install it and sign in), or an Anthropic API key from
        {' '}<a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noreferrer">console.anthropic.com</a>.
        With a key, jobs run on Claude Opus 5.5 and Sonnet 5.5 and are billed to that account. The key is checked once,
        then kept in your system's credential store (Windows Credential Manager), never in DSC's files.
      </p>
      {s.apiKey.set ? (
        <div className="row">
          <span className="pill pill-ok">key set</span>
          <span className="muted small">{s.apiKey.source === 'environment' ? 'from the ANTHROPIC_API_KEY environment variable' : 'in the system credential store'}
            {' · '}{onApi} of {s.routes.length} jobs use it directly; the others use it when their CLI is missing</span>
          <span className="spacer" />
          {onApi < s.routes.length && <button className="btn btn-small" onClick={() => dispatch({ type: 'useApiForAll' })}>Use the API for all jobs</button>}
          {s.apiKey.source === 'keychain' && <button className="btn btn-small" onClick={() => {
            if (window.confirm('Remove the API key from this computer?')) dispatch({ type: 'clearApiKey' })
          }}>Remove key</button>}
        </div>
      ) : (
        <div className="row">
          <input className="input api-key-input" type="password" autoComplete="off" spellCheck={false} placeholder="sk-ant-…"
            value={key} onChange={e => setKey(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && key) save() }} aria-label="Anthropic API key" />
          <button className="btn btn-primary" disabled={busy || key.trim().length < 20} onClick={save}>{busy ? 'Checking…' : 'Save key'}</button>
        </div>
      )}
    </div>
  )
}
