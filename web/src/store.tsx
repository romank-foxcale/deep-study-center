// Client state: a snapshot from the backend (GET /api/state). Actions are POSTed to
// /api/action and return the next snapshot. While agent jobs run, the snapshot is polled.

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import type { Angle, BookView, ReasoningEntry, FormulaTreeView, TodayView, FeedbackKind, IdeaDetail, FeedbackRef, GraphView, LessonDiff, LessonPlanView, LessonView, Plan, PracticeDue, PracticeTargets, PracticeView, RunResult, SearchHit, SessionView, SourceDoc, State, Verdict } from './types'

export type Action =
  | { type: 'answer'; conceptId: string; checkId: string; angle?: Angle; choice?: number; correct?: boolean; thinking?: string; confidence?: number | null }
  | { type: 'review'; conceptId: string; checkId: string; choice: number; thinking?: string; confidence?: number | null }
  | { type: 'feedback'; conceptId: string; sectionId?: string; angle?: Angle; available?: Angle[]; tags: string[]; text: string; kind?: FeedbackKind; ref?: FeedbackRef; apply?: boolean; worked?: string[] }
  | { type: 'editFeedback'; id: number; tags?: string[]; text?: string; kind?: FeedbackKind }
  | { type: 'deleteFeedback'; id: number }
  | { type: 'applyFeedback'; conceptId: string; ids: number[] }
  | { type: 'revertLesson'; conceptId: string; version: number }
  | { type: 'addRemedial'; conceptId: string }
  | { type: 'dismissRemedial'; conceptId: string }
  | { type: 'editGuidelines'; lines: string[] }
  | { type: 'distillGuidelines' }
  | { type: 'explainDifferently'; conceptId: string; sectionId: string }
  | { type: 'refresh'; conceptId: string }
  | { type: 'markStudied'; conceptId: string }
  | { type: 'addNote'; conceptId: string; text: string; quote?: string }
  | { type: 'deleteNote'; id: number }
  | { type: 'chat'; conceptId: string; text: string; sectionHeading?: string }
  | { type: 'decideDiff'; id: number; approve: boolean }
  | { type: 'researchModule'; moduleId: string }
  | { type: 'createGoal'; answers: { q: string; a: string }[]; layout: 'ohtani' | 'list'; sourceIds?: string[]; kind?: 'goal' | 'book' }
  | { type: 'linkSource'; sourceId: string; goalId?: string; on: boolean }
  | { type: 'editSource'; id: string; title?: string; kind?: SourceDoc['kind'] }
  | { type: 'deleteSource'; id: string }
  | { type: 'rereadSource'; id: string }
  | { type: 'setGoal'; id: string }
  | { type: 'correctEntry'; id: string; verdict: Verdict | 'remove' }
  | { type: 'adjust'; key: 'pace' | 'depth' | 'rigor'; value: number }
  | { type: 'route'; role: string; provider: string; model: string }
  | { type: 'useRecommendedRoutes' }
  | { type: 'explain'; conceptId: string; itemId: string; answer: string; angle?: Angle; confidence?: number | null; drawing?: string }
  | { type: 'startPractice'; nodeIds?: string[]; own?: string; source?: { id: string; page: number }
      focus?: Record<string, string[]>; formulas?: string[]; count?: number; surface?: string; title?: string }
  | { type: 'practiceNext'; practiceId: string }
  | { type: 'practiceSubmit'; itemId: number; text: string; hint?: boolean }
  | { type: 'practiceGiveUp'; itemId: number }
  | { type: 'practiceRetry'; practiceId: string }
  | { type: 'practiceStop'; practiceId: string }
  | { type: 'startSession'; topic: string; sourceIds?: string[] }
  | { type: 'sessionAnswer'; sessionId: string; itemId: number; choice: number | null; thinking?: string; confidence?: number | null }
  | { type: 'sessionKnown'; sessionId: string; ideaKey: string; known: boolean }
  | { type: 'sessionTeach'; sessionId: string }
  | { type: 'sessionAssessNow'; sessionId: string }
  | { type: 'sessionRetry'; sessionId: string }
  | { type: 'deleteSession'; sessionId: string }
  | { type: 'sessionLearnAgain'; sessionId: string }
  | { type: 'setApiKey'; key: string }
  | { type: 'clearApiKey' }
  | { type: 'useApiForAll' }
  | { type: 'studyBook'; sourceId: string }
  | { type: 'bookRetry'; bookId: string }
  | { type: 'bookOpenLesson'; conceptId: string }
  | { type: 'reviewReasoning'; conceptId: string; itemId: string }
  | { type: 'makeFormulaLesson'; conceptId: string; key: string }
  | { type: 'addFormulaForm'; conceptId: string; key: string; formulaId: string }
  | { type: 'preferFormulaForm'; formulaId: string; key: string }
  | { type: 'learnBlocksFirst'; formulaId: string }
  | { type: 'bookRemapChapter'; bookId: string; chapter: number; asLessons?: boolean }
  | { type: 'bookHomework'; bookId: string; chapter: number }
  | { type: 'deleteBook'; bookId: string }
  | { type: 'bookReplan'; bookId: string }
  | { type: 'openFormula'; node: string }
  | { type: 'planLesson'; conceptId: string }
  | { type: 'lessonPlanNote'; conceptId: string; kind: 'cut' | 'other' | 'note' | 'plan' | 'steer'; text?: string; node?: string }
  | { type: 'approveLessonPlan'; conceptId: string }
  | { type: 'predictStep'; conceptId: string; sectionId: string; choice: number; thinking?: string; confidence?: number | null }
  | { type: 'rewriteStep'; conceptId: string; sectionId: string; note?: string }
  | { type: 'demoResult'; conceptId: string; sectionId: string; version: number; ok: boolean; errors?: string[] }
  | { type: 'makeFormulaPage'; node: string }
  | { type: 'setMapView'; view: import('./types').MapViewId }
  | { type: 'setDictation'; mode?: 'browser' | 'local'; model?: string }
  | { type: 'downloadDictationModel'; model: string }
  | { type: 'removeDictationModel'; model: string }
  | { type: 'startProbe' }
  | { type: 'probeAnswer'; itemId: number; choice: number | null; thinking?: string; confidence?: number | null }
  | { type: 'probeAssessNow' }
  | { type: 'applyProbe' }
  | { type: 'resetProbe' }
  | { type: 'dismissProbe' }
  | { type: 'reflect' }
  | { type: 'decideProposal'; reflectionId: number; index: number; accept: boolean }
  | { type: 'setSetting'; key: 'autoResearch' | 'autoRefresh'; value: boolean }
  | { type: 'setSetting'; key: 'lessonWriting'; value: 'steps' | 'single' }
  | { type: 'setSetting'; key: 'writingStyle'; value: 'ste' | 'plain' }
  | { type: 'refreshCard'; conceptId: string }
  | { type: 'decideCardProposal'; id: number; approve: boolean }
  | { type: 'setPlanSettings'; weeklyHours?: number; studyDays?: number[]; startTime?: string; goalId?: string; hours?: number }
  | { type: 'setupRunner' }
  | { type: 'undoAnswer'; conceptId: string; itemId: string }
  | { type: 'loadDemo' }
  | { type: 'deleteGoal'; id: string }
  | { type: 'backupNow' }
  | { type: 'setRunnerMode'; mode: 'local' | 'docker' }
  | { type: 'setupRunnerDocker' }
  | { type: 'reset' }

export const KIND_LABELS: Record<FeedbackKind, string> = {
  lesson: 'Only this lesson',
  me: 'All my future lessons',
  fact: 'Report an error in the material',
}

export const FEEDBACK_TAGS: { id: string; label: string; old?: string }[] = [
  { id: 'framing-off', label: "The framing didn't work for me" },
  { id: 'confused', label: 'I got lost / missing background' },
  { id: 'too-abstract', label: 'Too abstract' },
  { id: 'too-fast', label: 'Too fast' },
  { id: 'too-slow', label: 'Too slow' },
  { id: 'too-long', label: 'Too long' },
  { id: 'more-rigor', label: 'More formal (exact definitions, proofs)', old: 'I want more rigor' },
  { id: 'loved-it', label: 'This worked really well' },
]

/** With "This worked really well": what exactly worked (saved in the text, and as a guideline for all future lessons). */
export const WORKED_PARTS = ['The pictures and graphs', 'The examples', 'The code', 'The step size', 'The order of the ideas']

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!res.ok) {
    const detail = await res.json().then(j => j.detail, () => res.statusText)
    throw new Error(String(detail))
  }
  return res.json() as Promise<T>
}

export const getLesson = (id: string) => api<LessonView>(`/api/lesson/${encodeURIComponent(id)}`)
export const postActivity = (conceptId: string, seconds: number) =>
  api<{ ok: boolean }>('/api/activity', { method: 'POST', body: JSON.stringify({ conceptId, seconds }) })
/** Upload a PDF as the raw request body; the server reads its text in a background job. ``onProgress`` gets 0..1.
 *  The same file twice is refused (409) with a message that names the source it already is. */
export const uploadSource = (file: File, opts: { kind?: string; title?: string; link?: boolean; onProgress?: (f: number) => void } = {}) =>
  new Promise<State>((resolve, reject) => {
    const q = new URLSearchParams({ filename: file.name, kind: opts.kind ?? 'book', title: opts.title ?? '', link: opts.link ? '1' : '0' })
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `/api/sources?${q}`)
    xhr.setRequestHeader('Content-Type', 'application/pdf')
    xhr.upload.onprogress = e => { if (e.lengthComputable) opts.onProgress?.(e.loaded / e.total) }
    xhr.onload = () => {
      let body: unknown = null
      try { body = JSON.parse(xhr.responseText) } catch { /* not JSON */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as State)
      else reject(new Error(String((body as { detail?: string } | null)?.detail ?? xhr.statusText)))
    }
    xhr.onerror = () => reject(new Error('The upload failed. Is the app still running?'))
    xhr.send(file)
  })
/** A link source (a web page or a video). */
export const addLinkSource = (body: { url: string; title: string; kind: string }) =>
  api<State>('/api/sources/link', { method: 'POST', body: JSON.stringify(body) })
/** A card source url "source:<id>#page=N" points into an uploaded PDF; open it at that page. */
export const sourceHref = (url: string) => {
  const m = /^source:([\w-]+)(?:#page=(\d+))?$/.exec(url)
  return m ? `/api/sources/${m[1]}/file${m[2] ? `#page=${m[2]}` : ''}` : url
}
export const getPractice = (id: string) => api<PracticeView>(`/api/practice/${encodeURIComponent(id)}`)
export const getPracticeDue = () => api<PracticeDue>('/api/practice-due')
export const getPracticeTargets = () => api<PracticeTargets>('/api/practice-targets')
export const getGraph = () => api<GraphView>('/api/graph')
export const getSession = (id: string) => api<SessionView>(`/api/session/${encodeURIComponent(id)}`)
export const getBook = (id: string) => api<BookView>(`/api/book/${encodeURIComponent(id)}`)
export const getToday = () => api<TodayView>('/api/today')
export const getReasoning = () => api<ReasoningEntry[]>('/api/reasoning')
export const getFormulaTree = () => api<FormulaTreeView>('/api/formulas')
export const getIdea = (id: string) => api<IdeaDetail>(`/api/graph/node/${encodeURIComponent(id)}`)
export const getPlan = () => api<Plan>('/api/plan')
export const searchAll = (q: string) => api<SearchHit[]>(`/api/search?q=${encodeURIComponent(q)}`)
export const runLocal = (body: { conceptId: string; itemId: string; code: string; angle?: Angle; approve?: boolean }) =>
  api<RunResult>('/api/run', { method: 'POST', body: JSON.stringify(body) })
export const getLessonDiff = (id: string, a: number, b: number) =>
  api<LessonDiff>(`/api/lesson/${encodeURIComponent(id)}/diff?a=${a}&b=${b}`)
export const openLesson = (id: string, noplan = false) =>
  api<LessonView>(`/api/lesson/${encodeURIComponent(id)}/open${noplan ? '?noplan=true' : ''}`, { method: 'POST' })
export const getLessonPlan = (id: string) => api<LessonPlanView>(`/api/lesson/${encodeURIComponent(id)}/plan`)

interface Ctx {
  s: State
  /** Resolves true when the action succeeded (errors show in the app's error bar). */
  dispatch: (a: Action) => Promise<boolean>
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
      return true
    } catch (e) {
      setError((e as Error).message)
      return false
    }
  }, [])

  if (!s) {
    return <div className="boot">{error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>}</div>
  }
  return <StoreCtx.Provider value={{ s, dispatch, reload: load, error, clearError: () => setError('') }}>{children}</StoreCtx.Provider>
}

/** The dictation settings, or null outside the store (components that may render before it loads). */
export function useDictationSettings() {
  return useContext(StoreCtx)?.s.dictation ?? null
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
