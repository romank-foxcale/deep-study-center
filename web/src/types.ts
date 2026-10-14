// Shapes returned by the backend (backend/dsc/state.py and lesson.py). See docs/SPEC.md §2.

export type NodeState = 'locked' | 'ready' | 'learning' | 'learned' | 'mastered' | 'rusty'
export type ResearchStatus = 'outline' | 'researching' | 'ready'
export type Angle = 'geometric' | 'algebraic' | 'computational'
export type Verdict = 'works' | 'avoid' | 'trying'
export type Provider = 'claude' | 'codex' | 'cursor'

export interface Goal {
  id: string
  title: string
  why: string
  doneLooksLike: string
  hoursPerWeek: number
  profile: string
}

export interface Track { id: string; title: string; summary: string; moduleIds: string[] }

export interface Module {
  id: string
  trackId: string
  title: string
  summary: string
  research: ResearchStatus
  conceptIds: string[]
  plannedConcepts: number
}

export interface Concept {
  id: string
  moduleId: string
  title: string
  objective: string
  minutes: number
  prereqs: string[]
  state: NodeState
  /** BKT estimate of P(learned), 0..1. */
  mastery: number
}

export interface Source { title: string; url: string; kind: string; why: string }

/** Check as the learner sees it: no answer key until answered. */
export interface McqCheck { id: string; prompt: string; options: string[] }

export interface CodeExercise { id: string; prompt: string; starter: string; tests: string }

export interface CardSection {
  id: string
  heading: string
  purpose?: string
  angles: Angle[]
  check?: McqCheck
  code?: CodeExercise
}

/** Knowledge center #1: canonical, learner-independent, versioned. */
export interface SourceCard {
  conceptId: string
  version: number
  factCheck: 'passed' | 'pending' | 'needs-revision'
  factIssues?: string[]
  checkedAt: string
  objective: string
  bloom: string
  core: string
  formal: string
  why: string
  angles: { id: Angle; label: string; summary: string }[]
  examples: { label: string; domain: string }[]
  misconceptions: string[]
  sources: Source[]
  sections: CardSection[]
}

export interface RenditionSummary {
  conceptId: string
  cardVersion: number
  playbookVersion: number
  studied: boolean
  stale: boolean
  sectionAngles: Record<string, Angle>
  pinned: Record<string, Angle>
}

export interface LessonSectionView {
  id: string
  heading: string
  angle: Angle
  angles: Angle[]
  body: string | null
  approximate: boolean
  pending: boolean
  check: McqCheck | null
  code: CodeExercise | null
}

/** Knowledge center #2 output for one lesson, as the page shows it. */
export interface LessonView {
  conceptId: string
  card: SourceCard | null
  sections: LessonSectionView[]
  rendering: boolean
  renderError: string | null
  refreshed?: boolean
  rendition: { cardVersion: number; playbookVersion: number; studied: boolean; stale: boolean } | null
}

export interface PlaybookEntry {
  id: string
  dimension: string
  value: string
  score: number
  evidence: number
  verdict: Verdict
  note: string
}

export interface Playbook {
  version: number
  entries: PlaybookEntry[]
  adjust: { pace: number; depth: number; rigor: number }
}

export interface Feedback {
  id: number
  ts: string
  conceptId: string
  sectionId?: string
  tags: string[]
  text: string
  effects: string[]
}

export interface Note { id: number; ts: string; conceptId: string; quote?: string | null; text: string }

export interface RoadmapChange { op: 'insert' | 'compress' | 'deepen'; title: string; detail: string }

export interface RoadmapDiff { id: number; ts: string; reason: string; changes: RoadmapChange[]; status: 'pending' | 'approved' | 'rejected' }

export interface ChatMessage { role: 'tutor' | 'me'; text: string }

export interface Answer { choice: number | null; correct: boolean; answer?: number; explanation?: string }

export interface ProviderRoute { role: string; description: string; provider: Provider; model: string }

export interface ProviderStatus { id: Provider; cli: string; detected: boolean; implemented: boolean; models: string[] }

export interface Job {
  id: number
  kind: string
  status: 'queued' | 'running' | 'done' | 'failed'
  label: string
  progress: string[]
  error: string | null
  updatedAt: string
  input: { concept_id?: string; module_id?: string }
}

export interface Review { conceptId: string; due: string; isDue: boolean }

export interface State {
  goal: Goal | null
  goals: { id: string; title: string }[]
  tracks: Track[]
  modules: Module[]
  concepts: Concept[]
  cards: SourceCard[]
  playbook: Playbook
  renditions: RenditionSummary[]
  feedback: Feedback[]
  notes: Note[]
  diffs: RoadmapDiff[]
  chats: Record<string, ChatMessage[]>
  answers: Record<string, Answer>
  routes: ProviderRoute[]
  providers: ProviderStatus[]
  jobs: Job[]
  reviews: Review[]
}
