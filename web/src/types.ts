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
  /** Placement showed the learner already knows this module. */
  known: boolean
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

export interface CodeExercise { id: string; prompt: string; starter: string; tests: string; runtime?: 'pyodide' | 'local' }

/** Interactive visual: a built-in widget and its numbers (validated by the backend). */
export type VizSpec =
  | { type: 'vectors2d'; caption: string; vectors: { x: number; y: number; label: string }[]; showSum: boolean }
  | { type: 'lincomb2d'; caption: string; u: number[]; v: number[]; target?: number[] }
  | { type: 'matrix2d'; caption: string; matrix: number[][] }
  | { type: 'plot'; caption: string; expr: string; xmin: number; xmax: number; params: { name: string; min: number; max: number; value: number }[] }

export interface PlanItem { kind: 'review' | 'lesson'; goalId: string; conceptId: string; title: string; minutes: number; note: string }

export interface Plan {
  start: string
  settings: { weekly_hours: number; study_days: number[]; start_time: string }
  days: { date: string; weekday: string; study: boolean; budget: number; minutes: number; items: PlanItem[] }[]
  goals: { id: string; title: string; share: number; plannedMinutes: number; targetMinutes: number }[]
  upcomingResearch: { goalId: string; moduleId: string; title: string; research: ResearchStatus }[]
}

export interface CardProposal {
  id: number
  ts: string
  conceptId: string
  baseVersion: number
  summary: string
  changes: string[]
  diff: { field: string; before: string; after: string }[]
}

export interface LibraryCard { key: string; title: string; objective: string; version: number; sourceConcept: string; promotedAt: string; uses: number }

export interface SearchHit { kind: 'note' | 'lesson' | 'card'; ref: string; conceptId: string; title: string; snippet: string }

export type RunResult =
  | { status: 'needs_setup' }
  | { status: 'needs_approval'; tests: string }
  | { status: 'blocked'; problems: string[] }
  | { status: 'ran'; passed: boolean; output: string }

/** Explain-back item as the learner sees it: the grading rubric stays on the server. */
export interface ExplainItem { id: string; prompt: string }

export interface Grading {
  id: number
  status: 'pending' | 'graded' | 'ungraded'
  answer: string
  score: number | null
  feedback: string | null
  missing: string[]
  followup: string | null
}

export interface PlacementState {
  available: boolean
  finished: boolean
  asked: number
  done: boolean
  question: { moduleId: string; module: string; prompt: string; options: string[] } | null
  counts: { known: number; gap: number; uncertain: number }
  status: Record<string, 'known' | 'gap' | 'uncertain'>
}

export interface Proposal {
  dimension: string
  value: string
  verdict?: Verdict
  delta?: number
  why: string
  status: 'pending' | 'accepted' | 'rejected'
}

export interface Reflection { id: number; ts: string; summary: string; proposals: Proposal[]; source: 'llm' | 'offline' }

export interface CardSection {
  id: string
  heading: string
  purpose?: string
  angles: Angle[]
  check?: McqCheck
  code?: CodeExercise
  explain?: ExplainItem
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
  explain: ExplainItem | null
  viz: VizSpec | null
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

export interface Answer { choice: number | null; correct: boolean; score?: number | null; answer?: number; explanation?: string }

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
  gradings: Record<string, Grading>
  placement: PlacementState | null
  reflections: Reflection[]
  settings: { autoResearch: boolean; autoRefresh: boolean; weeklyHours: number; studyDays: number[]; startTime: string }
  cardProposals: CardProposal[]
  library: LibraryCard[]
  runner: { setUp: boolean; packages: string[] }
  ankiExport: string | null
}
