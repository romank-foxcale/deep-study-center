// Client state: a snapshot from the backend (GET /api/state). Actions are POSTed to
// /api/action and return the next snapshot. While agent jobs run, the snapshot is polled.

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import type { Angle, LessonView, Plan, RunResult, SearchHit, State, Verdict } from './types'

export type Action =
  | { type: 'answer'; conceptId: string; checkId: string; angle?: Angle; choice?: number; correct?: boolean }
  | { type: 'review'; conceptId: string; checkId: string; choice: number }
  | { type: 'feedback'; conceptId: string; sectionId?: string; angle?: Angle; available?: Angle[]; tags: string[]; text: string }
  | { type: 'explainDifferently'; conceptId: string; sectionId: string }
  | { type: 'refresh'; conceptId: string }
  | { type: 'markStudied'; conceptId: string }
  | { type: 'addNote'; conceptId: string; text: string; quote?: string }
  | { type: 'deleteNote'; id: number }
  | { type: 'chat'; conceptId: string; text: string; sectionHeading?: string }
  | { type: 'decideDiff'; id: number; approve: boolean }
  | { type: 'researchModule'; moduleId: string }
  | { type: 'createGoal'; answers: { q: string; a: string }[] }
  | { type: 'setGoal'; id: string }
  | { type: 'correctEntry'; id: string; verdict: Verdict | 'remove' }
  | { type: 'adjust'; key: 'pace' | 'depth' | 'rigor'; value: number }
  | { type: 'route'; role: string; provider: string; model: string }
  | { type: 'explain'; conceptId: string; itemId: string; answer: string; angle?: Angle }
  | { type: 'startPlacement' }
  | { type: 'placementAnswer'; moduleId: string; choice: number | null }
  | { type: 'finishPlacement' }
  | { type: 'resetPlacement' }
  | { type: 'reflect' }
  | { type: 'decideProposal'; reflectionId: number; index: number; accept: boolean }
  | { type: 'setSetting'; key: 'autoResearch' | 'autoRefresh'; value: boolean }
  | { type: 'refreshCard'; conceptId: string }
  | { type: 'decideCardProposal'; id: number; approve: boolean }
  | { type: 'setPlanSettings'; weeklyHours?: number; studyDays?: number[]; startTime?: string; goalId?: string; hours?: number }
  | { type: 'promoteCard'; conceptId: string }
  | { type: 'setupRunner' }
  | { type: 'reset' }

export const FEEDBACK_TAGS = [
  { id: 'framing-off', label: "The framing didn't work for me" },
  { id: 'confused', label: 'I got lost / missing background' },
  { id: 'too-abstract', label: 'Too abstract' },
  { id: 'too-fast', label: 'Too fast' },
  { id: 'too-slow', label: 'Too slow' },
  { id: 'too-long', label: 'Too long' },
  { id: 'more-rigor', label: 'I want more rigor' },
  { id: 'loved-it', label: 'This worked really well' },
]

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!res.ok) {
    const detail = await res.json().then(j => j.detail, () => res.statusText)
    throw new Error(String(detail))
  }
  return res.json() as Promise<T>
}

export const getLesson = (id: string) => api<LessonView>(`/api/lesson/${encodeURIComponent(id)}`)
export const getPlan = () => api<Plan>('/api/plan')
export const searchAll = (q: string) => api<SearchHit[]>(`/api/search?q=${encodeURIComponent(q)}`)
export const runLocal = (body: { conceptId: string; itemId: string; code: string; angle?: Angle; approve?: boolean }) =>
  api<RunResult>('/api/run', { method: 'POST', body: JSON.stringify(body) })
export const openLesson = (id: string) => api<LessonView>(`/api/lesson/${encodeURIComponent(id)}/open`, { method: 'POST' })

interface Ctx {
  s: State
  dispatch: (a: Action) => Promise<void>
  /** Re-read the snapshot, e.g. after opening a lesson queued a render job. */
  reload: () => Promise<void>
  error: string
  clearError: () => void
}

const StoreCtx = createContext<Ctx | null>(null)

export function StoreProvider({ children }: { children: ReactNode }) {
  const [s, setS] = useState<State | null>(null)
  const [error, setError] = useState('')
  const busy = s?.jobs.some(j => j.status === 'queued' || j.status === 'running') ?? false
  const alive = useRef(true)

  const load = useCallback(async () => {
    try {
      const next = await api<State>('/api/state')
      if (alive.current) { setS(next); setError('') }
    } catch (e) {
      if (alive.current) setError(`Can't reach the backend: ${(e as Error).message}. Is \`dsc serve\` running?`)
    }
  }, [])

  useEffect(() => { alive.current = true; load(); return () => { alive.current = false } }, [load])

  // Poll while agent jobs run (renders, tutor replies, research), slowly otherwise; retry quickly
  // until the first load succeeds (e.g. the backend is still starting).
  const loaded = s !== null
  useEffect(() => {
    const t = setInterval(load, !loaded ? 2000 : busy ? 1500 : 15000)
    return () => clearInterval(t)
  }, [busy, loaded, load])

  const dispatch = useCallback(async (a: Action) => {
    try {
      setS(await api<State>('/api/action', { method: 'POST', body: JSON.stringify(a) }))
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])

  if (!s) {
    return <div className="boot">{error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>}</div>
  }
  return <StoreCtx.Provider value={{ s, dispatch, reload: load, error, clearError: () => setError('') }}>{children}</StoreCtx.Provider>
}

export function useStore() {
  const v = useContext(StoreCtx)
  if (!v) throw new Error('useStore outside StoreProvider')
  return v
}

export function jobActive(s: State, kind: string, match: { concept_id?: string; module_id?: string } = {}) {
  return s.jobs.some(j => j.kind === kind && (j.status === 'queued' || j.status === 'running')
    && Object.entries(match).every(([k, v]) => j.input[k as keyof typeof j.input] === v))
}
