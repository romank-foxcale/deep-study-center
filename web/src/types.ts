// Shapes returned by the backend (backend/dsc/state.py and lesson.py). See docs/SPEC.md §2.

/** No schedule (SPEC §48): an idea is learned for good; there is no "mastered" or "rusty". */
export type NodeState = 'locked' | 'ready' | 'learning' | 'learned'
export type ResearchStatus = 'outline' | 'researching' | 'ready'
export type Angle = 'geometric' | 'algebraic' | 'computational'
export type Verdict = 'works' | 'avoid' | 'trying'
export type Provider = 'claude' | 'codex' | 'cursor' | 'anthropic'

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
  | import('./components/viz/Surface3D').SurfaceSpec
  | { type: 'formula'; caption: string; tex: string
      parts: { id: string; tex: string; label: string; color: string; side: 'above' | 'below'; param: string | null
        expr?: string; variants?: { tex: string; expr: string; why: string }[] }[]
      checks?: { kind: 'area' | 'peak' | 'at' | 'result'; label: string; at?: number; expect?: number }[]
      params: { name: string; min: number; max: number; value: number; effect: string; label?: string }[]
      resultExpr?: string; resultTex?: string; plotExpr?: string; plotVar?: string; xmin?: number; xmax?: number }

export interface PlanItem { kind: 'lesson'; goalId: string; conceptId: string; title: string; minutes: number; note: string }

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

/** The type of a source (SPEC §40). custom: made by the learner (a roadmap, or a "teach me" topic with no document). */
export type SourceKind = 'book' | 'article' | 'web' | 'video' | 'custom'

/** A source of the learner (SPEC §17, §40): a PDF file, or a link (a web page or a video) that is kept and opened. */
export interface SourceDoc {
  id: string; title: string; author: string; kind: SourceKind; filename: string
  pages: number; status: 'reading' | 'ready' | 'no_text' | 'error'; addedAt: string; goalIds: string[]; outline: number
  /** A link source: its address (no file). */
  url: string
  /** The file's SHA-256 (to find a duplicate before the upload). */
  sha256: string
  /** "Teach me this book" made its lessons. */
  mapped: boolean
}

export interface SearchHit { kind: 'note' | 'lesson' | 'card'; ref: string; conceptId: string; title: string; snippet: string }

export type RunResult =
  | { status: 'needs_setup'; mode?: 'local' | 'docker' }
  | { status: 'needs_approval'; tests: string }
  | { status: 'blocked'; problems: string[] }
  | { status: 'ran'; passed: boolean; output: string }

/** Explain-back item as the learner sees it: the grading rubric stays on the server. */
/** work: the answer is a calculation or derivation; the learner gets a drawing board (SPEC §31). */
export interface ExplainItem { id: string; prompt: string; work?: boolean }

export interface Grading {
  id: number
  status: 'pending' | 'graded' | 'ungraded' | 'voided'
  answer: string
  score: number | null
  feedback: string | null
  missing: string[]
  followup: string | null
  /** The drawing board image sent with the answer (file name under /api/drawing/). */
  drawing?: string | null
  /** The grader's reading of the answer: parts marked, the assumption, where it breaks (SPEC §35). */
  review?: ReasoningReview | null
}

export interface PracticeChunk {
  text: string; ts: string; askedHint: boolean; verdict?: string; feedback?: string; hint?: string
  /** The rung of the hint ladder the hint came from (SPEC §44). */
  rung?: number | null
}
export interface PracticeItem {
  id: number; title: string; prompt: string; level: number; ideas: { id: string; title: string }[]
  /** "waiting": written, shown when the learner presses "Next problem" (SPEC §44). */
  status: 'open' | 'waiting' | 'solved' | 'given_up' | 'skipped'; hints: number; score: number | null; chunks: PracticeChunk[]; solution: string | null
  mode: 'recall' | 'tell_apart' | 'combine'; retest: boolean
}
/** A recall-practice run (SPEC §24, §44). */
export interface PracticeView {
  id: string; title: string; status: 'active' | 'done'; level: number; levelText: string; count: number
  busy: boolean; error: string | null; items: PracticeItem[]; ideas: { id: string; title: string }[]
  retests: number; rungs: string[]; surface: string; wantNext: boolean
  focus: Record<string, string[]>; formulas: { name: string; tex: string }[]
}
/** What can be practised (SPEC §44). */
export interface PracticeTargets {
  books: { id: string; title: string; chapters: { chapter: number; title: string; lessons: {
    conceptId: string; nodeId: string; title: string; state: string; mastery: number; studied: boolean; parts: string[] }[] }[] }[]
  fields: { id: string; title: string; formulas: { key: string; name: string; tex: string }[] }[]
  weakest: { nodeId: string; title: string; state: string; mastery: number; misses: number }[]
}

export interface GraphNode {
  id: string; title: string; statement: string; kind: string; state: string; mastery: number
  goals: string[]; concepts: string[]; sessions: string[]; lessons: { id: string; title: string; goalId: string }[]
  books: string[]
  /** A formula on the map (SPEC §41): ``kind`` "formula" and its form. Ids "fx:…" are formulas with no page. */
  tex?: string
  /** A formula's fields of mathematics, most important first (SPEC §41). */
  fields?: string[]
  /** A step of a planned lesson, as an idea of its own (SPEC §46): ``kind`` "step", ids "pn-…". */
  step?: { conceptId: string; lesson: string; sectionId: string }
  /** Map views (SPEC §29): the idea's cluster ("book:<id>", "goal:<id>", "session:<id>" or "loose"), the other books and
   *  goals it is in, its chapter there and its reading order (0..1). */
  cluster: string; also: string[]; chapter: number; chapterTitle: string; order: number
}
export type MapViewId = 'tree' | 'wheel' | 'cells' | 'territory'
/** ``color``: the area's fixed color number (see areaColors.ts); -1 for "Other ideas". */
export interface MapCluster { id: string; kind: 'book' | 'goal' | 'session' | 'loose' | 'formulas'; title: string; size: number; color: number }
/** The knowledge graph (SPEC §21, §23). */
export interface GraphView {
  nodes: GraphNode[]; links: { src: string; dst: string; origin: string }[]
  goals: { id: string; title: string }[]; sessions: { id: string; title: string }[]; books: { id: string; title: string }[]
  clusters: MapCluster[]
  /** The fields of mathematics: the provinces of the Formulas country (SPEC §41). */
  formulaFields?: { id: string; title: string }[]
}

/** Book study (SPEC §28). */
export interface StudyBookSummary {
  id: string; sourceId: string; title: string; author: string; status: 'mapping' | 'ready' | 'failed'
  chapters: number; chaptersDone: number; parts: number; partsDone: number; updatedAt: string; goalId: string | null
  /** The source's type, and the book's area color on the map (areaColors.ts). */
  kind: SourceKind; color: number
  /** The book's ideas: how many, and how many learned. */
  ideas: number; known: number
}
/** The Today page (SPEC §30). */
export interface TodayView {
  continue: null | {
    kind: 'session'; sessionId: string; title: string; status: string; next: string | null; nextStatement: string | null
    done: number; total: number; book: SessionView['book']
  } | {
    kind: 'lesson'; bookId: string; bookTitle: string; conceptId: string; title: string; pages: [number, number]; summary: string
    chapter: number; chapterTitle: string; done: number; total: number
  }
  week: { learned: number; answers: number; sessions: number }
  recent: { id: string; title: string; status: string; updatedAt: string }[]
}
/** One lesson of a book (SPEC §31): a topic of a chapter, one concept and one idea of the graph. */
export interface BookLesson {
  id: number; conceptId: string; nodeId: string; title: string; covers: string; pages: [number, number]; ideas: string[]
  state: string; mastery: number
  /** written: its text is saved; carded: its plan is written from the book; started: opened at least once. */
  written: boolean; carded: boolean; started: boolean
  /** The newest plan's status (SPEC §42), or null when the lesson has no plan. */
  plan: LessonPlanStatus | null
  alsoIn: { id: string; title: string }[]
  /** What it builds on that you do not hold yet (SPEC §37); ready = nothing missing. */
  needs: { id: string; title: string; conceptId: string | null }[]; ready: boolean
  /** One cell per idea (SPEC §49): ``conceptId`` is the idea's one lesson; ``ownConceptId`` is this book's entry. */
  ownConceptId: string
}
export interface BookChapter {
  chapter: number; title: string; summary: string; pages: [number, number]; moduleId: string; mapped: boolean
  /** reference: a glossary, reading list, …: looked up, not cut into lessons. */
  kind: 'chapter' | 'reference'
  writing: boolean; lessons: BookLesson[]
}
export interface BookView {
  id: string; sourceId: string; title: string; status: 'mapping' | 'ready' | 'failed'; goalId: string | null; version: number
  chapters: BookChapter[]; chapterCount: number; chaptersDone: number
  /** The concept id of the lesson to continue with. */
  next: string | null; error: string | null; progress: string; busy: boolean
  /** Its lessons were planned by topic (before 0.5); "Re-plan lessons" plans them with one idea per lesson (SPEC §40). */
  oldPlan: boolean
}
/** A formula's hover note: its name, what it says, its symbols and the graph ideas it belongs to. */
export interface FormulaNote {
  name: string; meaning: string; symbols: { tex: string; meaning: string }[]
  ideas: { id: string; title: string; state: string; lesson: string | null; here: boolean }[]
  /** idea: worth knowing on its own; step: a line of a derivation (neutral frame). */
  kind: 'idea' | 'step'
  /** The frame: green (learned formula lesson, this form), orange (a formula lesson, another form), gray (none yet), step. */
  status: 'green' | 'orange' | 'gray' | 'step'
  formula: { id: string; title: string; state: string; sameForm: boolean; here: boolean; missing: number } | null
}
/** Where a book lesson sits in its book (on the lesson page). */
export interface LessonBook {
  bookId: string; bookTitle: string; sourceId: string; chapter: number; chapterTitle: string; pages: [number, number]
  covers: string; prev: { id: string; title: string } | null; next: { id: string; title: string } | null; index: number; count: number
}
/** One idea for a hover card (SPEC §28). */
export interface IdeaDetail {
  id: string; title: string; statement: string; kind: string; state: string; mastery: number
  buildsOn: { id: string; title: string; state: string }[]; leadsTo: { id: string; title: string; state: string }[]
  books: { id: string; title: string; part: string; pages: string; conceptId?: string | null }[]
  sessions: { id: string; title: string; status: string }[]; lessons: { id: string; title: string; goalId: string }[]
}

export interface SessionQuestion {
  id: number; idea: string; phase: 'probe' | 'predict' | 'check'; round: number; prompt: string; options: string[]
  answered: boolean; choice?: number | null; correct?: boolean; answer?: number; explanation?: string
  thinking?: string; confidence?: number | null
  /** The tutor's reading of your thinking on this answer (SPEC §35). */
  review?: ReasoningReview | null
}
export interface SessionExplain { id: number; idea: string; phase: 'explain'; body: string; repair: boolean }
export type SessionItem = SessionQuestion | SessionExplain

export interface SessionIdea {
  key: string; title: string; statement: string; node: string; prereqs: string[]; target: boolean
  level: 'known' | 'partial' | 'unknown' | null; skip?: boolean; fromGraph: boolean; nodeState: string
  /** A known idea put back into the plan, to learn it again. */
  again?: boolean
  /** What the probe found on this idea (SPEC §26); absent when no question reached it. */
  probe?: { level: 'known' | 'partial' | 'unknown' | 'untested'; reasonsFrom: string; runsOut: string; misconceptions: string[] } | null
}

/** A study session, "teach me X" (SPEC §22). */
export interface SessionView {
  id: string; topic: string; title: string
  status: 'sketching' | 'probing' | 'planning' | 'teaching' | 'extracting' | 'done'
  busy: boolean; error: string | null; ideas: SessionIdea[]; plan: string[]; current: number; items: SessionItem[]
  summary: string; sources: string[]; createdAt: string
  /** The probe's advice where teaching starts, and its question limit. */
  probeStart: string; probeMax: number
  /** The book part this session studies (SPEC §28). */
  book: { id: string; title: string; partId: number; part: string; pages: [number, number]; practiceId: string | null } | null
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
  /** Book lessons: a close summary of what the book says in this section, and its pages. */
  book?: { summary: string; pages: string } | null
  /** Step lessons (SPEC §43): the question before the step (its key arrives in the steps' predictions once answered),
   *  the repair shown after a wrong check, and the plan node's kind and form. */
  predict?: McqCheck | null
  repair?: string | null
  kind?: string | null
  form?: string | null
  /** A generated interactive demo (SPEC §45). */
  demo?: StepDemo | null
}

/** A generated interactive demo (SPEC §45): building, ready (with its HTML), or failed (left out). */
export interface StepDemo {
  status: 'building' | 'ready' | 'failed'; title: string; watch: string; version: number; tested: boolean; html?: string
}

/** A step lesson's progress (SPEC §43). */
export interface StepsView {
  /** The index of the step the learner is on (``total`` when all are done). */
  current: number; total: number; held: string[]; planVersion: number | null
  nodes: { id: string; title: string; kind: string; form: string; done: boolean; written: boolean; writing: boolean }[]
  predictions: Record<string, { choice: number; correct: boolean; thinking: string; answer?: number; explanation?: string }>
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
/** The lesson plan graph (SPEC §42). */
export type LessonPlanStatus = 'planning' | 'ready' | 'approved' | 'failed'
export type LessonPlanKind = 'held' | 'foundation' | 'step' | 'formula' | 'goal'
export interface LessonPlanNode {
  key: string; kind: LessonPlanKind; title: string; says: string
  form: 'example' | 'interactive' | 'figure' | 'text' | 'derivation' | 'none'; whyForm: string; pages: string; linksTo: string
  /** Compared with the version before: "new", "changed" or "". */
  change?: string
}
export interface LessonPlanGraph {
  conceptId: string; version: number; status: LessonPlanStatus; approach: string; goal: string
  nodes: LessonPlanNode[]; edges: [string, string][]; error: string; createdAt: string; approvedAt: string | null
  /** Titles of nodes the version before had and this one has not. */
  removed?: string[]
  /** While a new version is made, or when it failed: the last finished version, shown dimmed. */
  shown?: LessonPlanGraph
}
export interface LessonPlanNote { id: number; version: number; node: string; kind: 'cut' | 'other' | 'note' | 'plan' | 'steer'; text: string; at: string; used: number | null }
export interface LessonPlanView {
  plan: LessonPlanGraph | null; versions: number[]; notes: LessonPlanNote[]; pending: number
  job: { id: number; status: string; progress: string[] } | null
}

export interface LessonView {
  conceptId: string
  /** Book lessons: the plan's version and status (SPEC §42). */
  lessonPlan: { version: number; status: LessonPlanStatus } | null
  /** A step lesson's progress (SPEC §43), or null. */
  steps: StepsView | null
  /** Book lessons (SPEC §31): the book, chapter and pages, and the lessons before and after. */
  book: LessonBook | null
  /** The chapter's lessons are being written from the book's pages. */
  writingCards: boolean
  /** While the lesson is written: its steps, the step it is on, and the newest progress line. */
  writing: { steps: string[]; at: number; message: string; queued: boolean } | null
  /** Lessons of this idea written before one cell per idea (SPEC §49): the one lesson and the earlier written ones. */
  blockVersions: { conceptId: string; title: string; where: string; bookId: string | null; written: boolean; current: boolean }[]
  /** Every source of this idea (SPEC §49): books, articles, web pages, videos, with pages. */
  sources: CellSource[]
  /** Another lesson of the idea was asked for: open this one (the idea's one lesson). */
  redirect?: string
  /** Hover notes for the lesson's formulas, by the formula's TeX without spaces (SPEC §33). */
  formulas: Record<string, FormulaNote>
  formulasPending: boolean
  /** A formula lesson (SPEC §34): the forms it covers, where each comes from, and the one you prefer. */
  formulaLesson: { forms: { key: string; tex: string; from: { id: string; title: string } }[]; preferred: string | null
    /** The learner chose the preferred form (else it is the first form); every writer then uses it (SPEC §36). */
    chosen: boolean
    /** formula, or notation (a short lesson about a way of writing). */
    kind: 'formula' | 'notation'
    /** The formula tree (SPEC §37): what it is built from, and what is built from it. */
    blocks: { id: number; name: string; kind: 'notation' | 'formula' | 'idea'; tex: string; meaning: string; basic: boolean
      state: 'known' | 'new'; link: { id: string | null; title: string; kind: 'lesson' | 'idea' } | null }[]
    blocksReady: boolean; missing: number
    usedIn: { id: string; title: string; kind: 'formula' | 'lesson' }[]
    source: { id: string; title: string } } | null
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
  /** The tutor's reading of your thinking on this answer (SPEC §32). */
  review?: ReasoningReview | null
}
/** What the tutor found in your reasoning: parts marked in place, the wrong assumption, where following it breaks,
 * and how it really works. */
export interface ReasoningReview {
  id: number; status: 'pending' | 'done' | 'failed'
  verdict: 'right' | 'right_with_gaps' | 'wrong' | 'unclear'; summary: string
  parts: { quote: string; mark: 'right' | 'partly' | 'wrong'; note: string }[]
  assumption: string; follow: string[]; truth: string; takeaway: string
}
export interface ReasoningEntry extends ReasoningReview {
  /** check: a lesson check; session: a study-session answer; explain: an explain-back. */
  kind: 'check' | 'session' | 'explain'; link: string
  conceptId: string; title: string; itemId: string; at: string; correct: boolean; confidence: number | null; thinking: string
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

export interface DictationStatus {
  mode: 'browser' | 'local'; model: string; available: boolean; ready: boolean
  models: { id: string; label: string; mb: number; installed: boolean }[]
}

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
  apiKey: { set: boolean; source: 'environment' | 'keychain' | null }
  jobs: Job[]
  gradings: Record<string, Grading>
  probe: ProbeState | null
  reflections: Reflection[]
  settings: { autoResearch: boolean; autoRefresh: boolean; lessonWriting: 'steps' | 'single'; writingStyle: 'ste' | 'plain'; weeklyHours: number; studyDays: number[]; startTime: string }
  cardProposals: CardProposal[]
  sources: SourceDoc[]
  sessions: { id: string; title: string; topic: string; status: string; createdAt: string }[]
  lastSession: string | null
  /** Local dictation with Whisper (SPEC §27). */
  dictation: DictationStatus
  /** Book study (SPEC §28). */
  studyBooks: StudyBookSummary[]; lastBook: string | null
  /** The knowledge-map view the learner chose (SPEC §29). */
  mapView: MapViewId
  practices: { id: string; title: string; status: string; createdAt: string }[]
  lastPractice: string | null
  runner: { setUp: boolean; packages: string[]; mode: 'local' | 'docker'; dockerReady: boolean }
  backups: { folder: string; last: string | null; items: { name: string; size: number; at: string }[] }
  firstRun: boolean
}

/** The whole formula tree (SPEC §38). A link goes from a block to the formula built from it. */
export interface FormulaTreeNode {
  id: string; name: string; kind: 'formula' | 'notation' | 'idea'; tex: string; meaning: string
  state: 'known' | 'learning' | 'writing' | 'new'
  /** The lesson to open (a formula lesson or the idea's lesson); null for a block with no lesson yet. */
  lesson: string | null
  basic: boolean; formula: boolean; blocksReady: boolean
  source: { id: string; title: string } | null
  /** Other block names that this idea teaches here. */
  covers: string[]
  /** The derivation graph (SPEC §40): its parts can be found one level down (``openable``); they are being found now. */
  openable: boolean; opening: boolean
}
export interface FormulaTreeView { nodes: FormulaTreeNode[]; links: { src: string; dst: string }[] }

/** One source of an idea's cell (SPEC §49). */
export interface CellSource {
  bookId: string; sourceId: string | null; title: string; kind: string; url: string; chapter: number; chapterTitle: string
  part: string; pages: [number, number]
}
