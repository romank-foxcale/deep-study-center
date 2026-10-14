import type { NodeState } from '../types'

const LABEL: Record<NodeState, string> = {
  locked: 'Locked', ready: 'Ready', learning: 'Learning', learned: 'Learned', mastered: 'Mastered', rusty: 'Rusty',
}

export default function StateBadge({ state }: { state: NodeState }) {
  return <span className={`badge badge-${state}`}>{LABEL[state]}</span>
}

export function MasteryBar({ value }: { value: number }) {
  return (
    <span className="mastery" title={`P(learned) = ${value.toFixed(2)}`}>
      <span className="mastery-fill" style={{ width: `${Math.round(value * 100)}%` }} />
    </span>
  )
}
