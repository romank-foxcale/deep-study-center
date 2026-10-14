// Domain types shared by the prototype UI. They mirror docs/SPEC.md §2 so the backend
// can later return the same shapes.

export type NodeState = 'locked' | 'ready' | 'learning' | 'learned' | 'mastered' | 'rusty'
export type ResearchStatus = 'outline' | 'researching' | 'ready'
export type Angle = 'geometric' | 'algebraic' | 'computational'

export interface Goal {
  id: string
  title: string
  why: string
  doneLooksLike: string
  hoursPerWeek: number
  createdAt: string
}

export interface Track {
  id: string
  title: string
  summary: string
  moduleIds: string[]
}

export interface Module {
  id: string
  trackId: string
  title: string
  research: ResearchStatus
  conceptIds: string[]
  /** Concepts planned in the outline but not yet broken down (outline-only modules). */
  plannedConcepts?: number
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

export interface Source {
  title: string
  url: string
  kind: 'video' | 'book' | 'article' | 'paper' | 'interactive'
  why: string
}

/** Knowledge center #1: canonical, learner-independent, versioned. */
export interface SourceCard {
  conceptId: string
  version: number
  factCheck: 'passed' | 'pending' | 'needs-revision'
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
}

export interface McqCheck {
  id: string
  prompt: string
  options: string[]
  answer: number
  explanation: string
}

export interface CodeExercise {
  id: string
  prompt: string
  starter: string
  tests: string
}

/** A section of a lesson. `variants` holds one body per teaching angle. */
export interface LessonSection {
  id: string
  heading: string
  variants: Partial<Record<Angle, string>>
  check?: McqCheck
  code?: CodeExercise
}

/** Knowledge center #2 output: this learner's version of one lesson. */
export interface Rendition {
  conceptId: string
  cardVersion: number
  playbookVersion: number
  studied: boolean
  /** Angle chosen for each section (from the playbook, or "explain differently"). */
  sectionAngles: Record<string, Angle>
  /** Sections whose angle came from direct feedback here; a refresh keeps them. */
  pinned?: Record<string, Angle>
}

export type Verdict = 'works' | 'avoid' | 'trying'

export interface PlaybookEntry {
  id: string
  dimension: 'angle' | 'example-domain' | 'format'
  value: string
  /** Posterior mean that this helps, 0..1. */
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
  id: string
  ts: string
  conceptId: string
  sectionId?: string
  tags: string[]
  text: string
  effects: string[]
}

export interface Note {
  id: string
  ts: string
  conceptId: string
  quote?: string
  text: string
}

export interface RoadmapChange {
  op: 'insert' | 'compress' | 'deepen'
  title: string
  detail: string
}

export interface RoadmapDiff {
  id: string
  ts: string
  reason: string
  changes: RoadmapChange[]
  status: 'pending' | 'approved' | 'rejected'
}

export interface ChatMessage {
  role: 'tutor' | 'me'
  text: string
}

export type Provider = 'claude' | 'codex' | 'cursor'

export interface ProviderRoute {
  role: string
  description: string
  provider: Provider
  model: string
}
