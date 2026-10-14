import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getPlan, useStore } from '../store'
import type { Plan } from '../types'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/** One plan across all goals: weekly hours split by goal, each study day filled reviews-first. */
export default function Week() {
  const { s, dispatch } = useStore()
  const [plan, setPlan] = useState<Plan | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { getPlan().then(p => { setPlan(p); setError('') }, e => setError((e as Error).message)) }, [s])
  const st = s.settings

  const toggleDay = (d: number) => {
    const days = st.studyDays.includes(d) ? st.studyDays.filter(x => x !== d) : [...st.studyDays, d]
    if (days.length) dispatch({ type: 'setPlanSettings', studyDays: days })
  }

  return (
    <div className="page">
      <h1>This week</h1>
      <p className="lead">One plan across all your goals. Reviews come first each day, then lessons in roadmap order, from whichever goal
        is furthest behind its share of your time. It updates as you learn.</p>

      <div className="card plan-settings">
        <label className="row">
          <span>Hours per week</span>
          <input className="input input-small" type="number" min={0.5} max={80} step={0.5} defaultValue={st.weeklyHours}
            key={st.weeklyHours} onBlur={e => dispatch({ type: 'setPlanSettings', weeklyHours: Number(e.target.value) })} />
        </label>
        <div className="row" role="group" aria-label="Study days">
          <span>Study days</span>
          {DAYS.map((d, i) => (
            <button key={d} className={`chip ${st.studyDays.includes(i) ? 'on' : ''}`} aria-pressed={st.studyDays.includes(i)}
              onClick={() => toggleDay(i)}>{d}</button>
          ))}
        </div>
        <label className="row">
          <span>Start time</span>
          <input className="input input-small" type="time" defaultValue={st.startTime} key={st.startTime}
            onBlur={e => e.target.value && dispatch({ type: 'setPlanSettings', startTime: e.target.value })} />
          <a className="btn" href="/api/plan.ics" download>Add to calendar (.ics)</a>
        </label>
      </div>

      {error && <p className="error">{error}</p>}
      {plan && plan.goals.length > 1 && (
        <div className="card">
          <div className="eyebrow">Time per goal this week</div>
          {plan.goals.map(g => (
            <div key={g.id} className="goal-share">
              <span className="goal-share-title">{g.title}</span>
              <span className="meter"><span style={{ width: `${Math.min(100, (g.plannedMinutes / Math.max(1, g.targetMinutes)) * 100)}%` }} /></span>
              <span className="muted small">{Math.round(g.plannedMinutes / 6) / 10} of {Math.round(g.targetMinutes / 6) / 10} h · {Math.round(g.share * 100)}%</span>
            </div>
          ))}
        </div>
      )}

      {plan && (
        <div className="week">
          {plan.days.map((d, di) => (
            <section key={d.date} className={`day ${di === 0 ? 'today' : ''} ${d.study ? '' : 'rest'}`}>
              <div className="day-head">
                <strong>{di === 0 ? 'Today' : d.weekday}</strong>
                <span className="muted small">{new Date(d.date + 'T00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span>
                {d.study && <span className="muted small">{d.minutes}/{d.budget} min</span>}
              </div>
              {!d.study && <p className="muted small">Rest day</p>}
              {d.study && d.items.length === 0 && <p className="muted small">Nothing ready to plan.</p>}
              <ul className="plain">
                {d.items.map((it, i) => (
                  <li key={i} className={`plan-item plan-${it.kind}`}>
                    <Link to={it.kind === 'review' ? '/review' : `/lesson/${it.conceptId}`}
                      onClick={() => { if (it.goalId !== s.goal?.id) dispatch({ type: 'setGoal', id: it.goalId }) }}>{it.title}</Link>
                    <span className="muted small">{it.kind === 'review' ? 'review' : `${it.minutes} min`}{it.note ? ` · ${it.note}` : ''}</span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      {plan && plan.upcomingResearch.length > 0 && (
        <p className="muted small">Next to research: {plan.upcomingResearch.map(u => `${u.title} (${u.research})`).join(', ')}.
          Its lessons join the plan once research finishes.</p>
      )}
    </div>
  )
}
