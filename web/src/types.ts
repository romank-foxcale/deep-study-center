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
  /** list: classic tracks → modules roadmap. ohtani: 9×9 Mandala grid (8 areas × 8 steps + 8 merges). */
  layout: 'list' | 'ohtani'
  /** goal: a normal goal. book: the 80/20 core of chosen sources (SPEC §18). */
  kind: 'goal' | 'book'
}

/** Ohtani grid block of a track: an area on the ring (clockwise from top left) or C for the merge steps. */
export type GridPos = 'TL' | 'TM' | 'TR' | 'MR' | 'BR' | 'BM' | 'BL' | 'ML' | 'C' | ''

export interface Track { id: string; title: string; summary: string; pos: GridPos; moduleIds: string[] }

export interface Module {
  id: string
  trackId: string
  title: string
  summary: string
  research: ResearchStatus
  /** The probe (or the old placement quiz) showed the learner already knows this module. */
  known: boolean
  conceptIds: string[]
  plannedConcepts: number
  /** Position inside its track. */
  ord: number
  /** Modules that must be learned first (Ohtani merge steps). */
  requires: string[]
  /** The step's concrete completion check ('' for classic roadmaps). */
  doneWhen: string
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
  | { type: 'formula'; caption: string; tex: string
      parts: { id: string; tex: string; label: string; color: string; side: 'above' | 'below'; param: string | null
        expr?: string; variants?: { tex: string; expr: string; why: string }[] }[]
      checks?: { kind: 'area' | 'peak' | 'at' | 'result'; label: string; at?: number; expect?: number }[]
      params: { name: string; min: number; max: number; value: number; effect: string; label?: string }[]
      resultExpr?: string; resultTex?: string; plotExpr?: string; plotVar?: string; xmin?: number; xmax?: number }

export interface PlanItem { kind: 'review' | 'lesson'; goalId: string; conceptId: string; title: string; minutes: number; note: string }

export interface Plan {
  start: string
  settings: { weekly_hours: number; study_days: number[]; start_time: string }
  days: { date: string; weekday: string; study: boolean; budget: number; minutes: number; actualMinutes: number; items: PlanItem[] }[]
  goals: { id: string; title: string; hours: number; share: number; plannedMinutes: number; targetMinutes: number }[]
  actualLast7: { date: string; minutes: number }[]
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

/** A book, article or post the learner uploaded as a PDF (SPEC §17). */
/** One ranked chapter of a book goal's sources. core and supporting are kept; skip is left out until brought back. */
export interface BookCut {
  id: number; sourceId: string; sourceTitle: string; chapter: string; pages: string
  rank: 'core' | 'supporting' | 'skip'; why: string; moduleId: string | null
  status: 'kept' | 'cut' | 'restored'; conceptId: string | null
}

export interface SourceDoc {
  id: string; title: string; author: string; kind: 'book' | 'article' | 'post' | 'other'; filename: string
  pages: number; status: 'reading' | 'ready' | 'no_text' | 'error'; addedAt: string; goalIds: string[]; outline: number
}

export interface SearchHit { kind: 'note' | 'lesson' | 'card'; ref: string; conceptId: string; title: string; snippet: string }

export type RunResult =
  | { status: 'needs_setup'; mode?: 'local' | 'docker' }
  | { status: 'needs_approval'; tests: string }
  | { status: 'blocked'; problems: string[] }
  | { status: 'ran'; passed: boolean; output: string }

/** Explain-back item as the learner sees it: the grading rubric stays on the server. */
export interface ExplainItem { id: string; prompt: string }

export interface Grading {
  id: number
  status: 'pending' | 'graded' | 'ungraded' | 'voided'
  answer: string
  score: number | null
  feedback: string | null
  missing: string[]
  followup: string | null
}

export interface GraphNode {
  id: string; title: string; statement: string; kind: string; state: string; mastery: number
  goals: string[]; concepts: string[]; sessions: string[]; lessons: { id: string; title: string; goalId: string }[]
}
/** The knowledge graph (SPEC §21, §23). */
export interface GraphView {
  nodes: GraphNode[]; links: { src: string; dst: string; origin: string }[]
  goals: { id: string; title: string }[]; sessions: { id: string; title: string }[]
}

export interface SessionQuestion {
  id: number; idea: string; phase: 'probe' | 'predict' | 'check'; round: number; prompt: string; options: string[]
  answered: boolean; choice?: number | null; correct?: boolean; answer?: number; explanation?: string
  thinking?: string; confidence?: number | null
}
export interface SessionExplain { id: number; idea: string; phase: 'explain'; body: string; repair: boolean }
export type SessionItem = SessionQuestion | SessionExplain

export interface SessionIdea {
  key: string; title: string; statement: string; node: string; prereqs: string[]; target: boolean
  level: 'known' | 'partial' | 'unknown' | null; skip?: boolean; fromGraph: boolean; nodeState: string
}

/** A study session, "teach me X" (SPEC §22). */
export interface SessionView {
  id: string; topic: string; title: string
  status: 'sketching' | 'probing' | 'planning' | 'teaching' | 'extracting' | 'done'
  busy: boolean; error: string | null; ideas: SessionIdea[]; plan: string[]; current: number; items: SessionItem[]
  summary: string; sources: string[]; createdAt: string
}

export interface ProbeAnswered {
  id: number; round: number; module: string; prompt: string; options: string[]; choice: number | null; correct: boolean
  answer: number; explanation: string; thinking: string; confidence: number | null
}

/** The probe (SPEC §20): where the learner stands for the active goal. */
export interface ProbeState {
  status: 'idle' | 'thinking' | 'asking' | 'done'
  question: { id: number; round: number; module: string; prompt: string; options: string[] } | null
  answered: ProbeAnswered[]
  asked: number
  rounds: number
  maxQuestions: number
  dismissed: boolean
  error: string | null
  assessment: {
    summary: string; edge: string; misconceptions: string[]; applied: boolean
    modules: { moduleId: string; title: string; level: 'known' | 'partial' | 'unknown'; note: string }[]
  } | null
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
  /** The graph / quiz question was made for this learner by the lesson writer (not the card's one). */
  vizMine: boolean
  /** What the app had to fix or remove in this graph after computing it (empty when it works as written). */
  vizNotes: string[]
  checkMine: boolean
}

/** How the lesson was written for this learner: the planner's summary and briefs, and the reviewer's findings. */
export interface LessonPlan {
  summary: string
  briefs: Record<string, string>
  review: {
    summary: string
    issues: { sectionId: string; part: 'prose' | 'viz' | 'check'; problem: string; fix: string; source: string }[]
    fixed: string[]
    dropped: string[]
  } | null
}

/** Knowledge center #2 output for one lesson, as the page shows it. */
export interface LessonView {
  conceptId: string
  card: SourceCard | null
  sections: LessonSectionView[]
  rendering: boolean
  renderError: string | null
  refreshed?: boolean
  rendition: { cardVersion: number; playbookVersion: number; studied: boolean; stale: boolean; shaped: boolean } | null
  /** The version the page shows. */
  head: number | null
  /** Newest first. */
  versions: LessonVersion[]
  /** An apply-feedback job is running for this lesson. */
  applying: boolean
  /** Offer of an extra lesson when the learner is stuck (SPEC §12). */
  remedial: { id: string; title: string; reasons: string[]; score: number } | null
  /** Extra lessons already added for this lesson ("Vectors (b)", …). */
  extraLessons: { id: string; title: string }[]
  plan: LessonPlan | null
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

/** lesson = about this lesson only; me = about how I learn (changes the playbook); fact = the material may be wrong. */
export type FeedbackKind = 'lesson' | 'me' | 'fact'

export interface FeedbackStatus {
  state: 'pending' | 'applied' | 'reverted' | 'routed' | 'done'
  /** The lesson version that applied it (applied) or that was left (reverted). */
  version: number | null
  /** Edited after it was applied. */
  changedSinceApplied: boolean
  note: string | null
}

/** The part of a lesson a piece of feedback (or a note) is about. */
export interface FeedbackRef {
  kind: 'text' | 'formula' | 'viz'
  /** Selected text (formulas as $LaTeX$), a formula's LaTeX, or a graph's caption. */
  quote: string
  sectionId?: string | null
}

/** Lesson guidelines distilled from the learner's feedback (SPEC §12). */
export interface Guidelines {
  version: number
  ts: string
  source: 'agent' | 'learner'
  summary: string
  items: { text: string; why: string; feedbackIds: number[]; byLearner: boolean }[]
}

export interface Feedback {
  id: number
  ts: string
  conceptId: string
  sectionId?: string | null
  tags: string[]
  text: string
  effects: string[]
  kind: FeedbackKind
  /** Who set the kind: auto (rules), agent, or learner. */
  kindSource: 'auto' | 'agent' | 'learner'
  angle?: Angle | null
  updatedAt: string | null
  status: FeedbackStatus
  ref: FeedbackRef | null
}

/** One immutable version of a lesson (SPEC §11). */
export interface LessonVersion {
  version: number
  ts: string
  parent: number | null
  source: 'render' | 'apply'
  summary: string
  cardVersion: number
  playbookVersion: number
  style: string
  feedbackIds: number[]
  changes: number
}

export interface DiffChange {
  sectionId: string
  feedbackIds: number[]
  why: string
  how: string
  technique: string
  /** Set when the change is outside the part the feedback is about: why it is directly relevant. */
  relatedBecause?: string
  version: number
  /** The change is in the older side only: going from A to B undoes it. */
  undone: boolean
}

export interface LessonDiff {
  conceptId: string
  a: LessonVersion
  b: LessonVersion
  sections: {
    id: string
    heading: string
    status: 'same' | 'changed' | 'added' | 'removed'
    angleA: Angle | null
    angleB: Angle | null
    tokens: ['eq' | 'del' | 'ins', string][]
    inserted: number
    deleted: number
    changes: DiffChange[]
  }[]
  feedback: { id: number; text: string; tags: string[]; kind: FeedbackKind; deleted: boolean }[]
}

export interface Note { id: number; ts: string; conceptId: string; quote?: string | null; text: string }

export interface RoadmapChange { op: 'insert' | 'compress' | 'deepen'; title: string; detail: string }

export interface RoadmapDiff { id: number; ts: string; reason: string; changes: RoadmapChange[]; status: 'pending' | 'approved' | 'rejected' }

export interface ChatMessage { role: 'tutor' | 'me'; text: string }

export interface Answer {
  choice: number | null; correct: boolean; score?: number | null; answer?: number; explanation?: string
  thinking?: string; confidence?: number | null
}

export interface ProviderRoute {
  role: string
  description: string
  provider: Provider
  model: string
  /** The recommended provider and model for this job, and why. */
  recommended: { provider: Provider; model: string; why: string } | null
}

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
  guidelines: Guidelines | null
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
  probe: ProbeState | null
  reflections: Reflection[]
  settings: { autoResearch: boolean; autoRefresh: boolean; lessonWriting: 'steps' | 'single'; weeklyHours: number; studyDays: number[]; startTime: string }
  cardProposals: CardProposal[]
  library: LibraryCard[]
  sources: SourceDoc[]
  sessions: { id: string; title: string; topic: string; status: string; createdAt: string }[]
  lastSession: string | null
  runner: { setUp: boolean; packages: string[]; mode: 'local' | 'docker'; dockerReady: boolean }
  backups: { folder: string; last: string | null; items: { name: string; size: number; at: string }[] }
  firstRun: boolean
  shareSuggestions: string[]
  ankiExport: string | null
  bookCuts: BookCut[]
}
