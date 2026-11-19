import { Link } from 'react-router-dom'
import { useStore } from '../store'

const KINDS = ['outline', 'research_module', 'fact_check', 'placement_bank']

/** The jobs that build a new goal (outline → placement quiz → first research), from `since` on. */
export default function BuildProgress({ since, goalBefore }: { since: string; goalBefore?: string }) {
  const { s } = useStore()
  const jobs = s.jobs.filter(j => KINDS.includes(j.kind) && j.updatedAt >= since.slice(0, 19))
  const created = s.goal && s.goal.id !== goalBefore
  return (
    <div className="pipeline">
      {jobs.length === 0 && <div className="pipe-step active"><span className="pipe-dot" />Starting…</div>}
      {[...jobs].reverse().map(j => (
        <div key={j.id} className={`pipe-step ${j.status === 'done' ? 'done' : j.status === 'failed' ? 'failed' : 'active'}`}>
          <span className="pipe-dot" />
          <span>{j.label}{j.status === 'failed' ? `: failed (${j.error})` : ''}
            {j.progress.length > 0 && j.status !== 'failed' && <span className="muted small"> · {j.progress.slice(-1)[0]}</span>}</span>
        </div>
      ))}
      {created && <p>Your roadmap is ready. <Link to="/placement" className="link">Take the placement quiz →</Link> to skip
        what you already know, or <Link to="/roadmap" className="link">open the roadmap</Link>. The first module's lessons appear
        when its research finishes.</p>}
    </div>
  )
}
