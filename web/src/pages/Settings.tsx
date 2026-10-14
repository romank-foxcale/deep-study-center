import { useStore } from '../store'

export default function Settings() {
  const { s, dispatch } = useStore()
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
        <h2>Who does what</h2>
        <table className="table">
          <thead><tr><th>Job</th><th>Provider</th><th>Model</th></tr></thead>
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
                </tr>
              )
            })}
          </tbody>
        </table>
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
