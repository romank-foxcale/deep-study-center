import { useStore } from '../store'
import type { Provider } from '../types'

const PROVIDERS: { id: Provider; label: string; cli: string; models: string[]; status: string }[] = [
  { id: 'claude', label: 'Claude (subscription)', cli: 'claude -p', models: ['opus', 'sonnet', 'haiku'], status: 'detected · logged in' },
  { id: 'codex', label: 'ChatGPT (subscription)', cli: 'codex exec', models: ['default'], status: 'not checked' },
  { id: 'cursor', label: 'Cursor (subscription)', cli: 'cursor-agent -p', models: ['default'], status: 'not checked' },
]

export default function Settings() {
  const { s, dispatch } = useStore()
  return (
    <div className="page">
      <h1>Settings</h1>

      <div className="card">
        <h2>Workspace</h2>
        <p><code>~/DeepStudy</code> <span className="muted small">Your data lives here, outside the code repo.</span></p>
      </div>

      <div className="card">
        <h2>Providers</h2>
        <p className="muted small">The app drives the agent CLIs you have installed and logged in, so it uses your subscriptions. No API keys, but each plan's rate limits apply.</p>
        <table className="table">
          <thead><tr><th>Provider</th><th>CLI</th><th>Status</th></tr></thead>
          <tbody>{PROVIDERS.map(p => <tr key={p.id}><td>{p.label}</td><td><code>{p.cli}</code></td><td className="muted">{p.status} (mock)</td></tr>)}</tbody>
        </table>
      </div>

      <div className="card">
        <h2>Who does what</h2>
        <table className="table">
          <thead><tr><th>Job</th><th>Provider</th><th>Model</th></tr></thead>
          <tbody>
            {s.routes.map(r => {
              const p = PROVIDERS.find(x => x.id === r.provider)!
              return (
                <tr key={r.role}>
                  <td>{r.role}<div className="muted small">{r.description}</div></td>
                  <td>
                    <select className="input input-small" value={r.provider} aria-label={`${r.role} provider`}
                      onChange={e => {
                        const np = PROVIDERS.find(x => x.id === e.target.value)!
                        dispatch({ type: 'route', role: r.role, provider: np.id, model: np.models[0] })
                      }}>
                      {PROVIDERS.map(x => <option key={x.id} value={x.id}>{x.id}</option>)}
                    </select>
                  </td>
                  <td>
                    <select className="input input-small" value={r.model} aria-label={`${r.role} model`}
                      onChange={e => dispatch({ type: 'route', role: r.role, provider: r.provider, model: e.target.value })}>
                      {p.models.map(m => <option key={m}>{m}</option>)}
                    </select>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>Prototype</h2>
        <button className="btn" onClick={() => { if (confirm('Reset all prototype data?')) dispatch({ type: 'reset' }) }}>Reset demo data</button>
      </div>
    </div>
  )
}
