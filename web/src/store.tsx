// Prototype state + a mock engine. The real engine (docs/SPEC.md §4) lives in the backend;
// here the same rules run in the browser so the adaptation loop can be tried end to end.

import { createContext, useContext, useEffect, useReducer, type ReactNode } from 'react'
import * as mock from './data/mock'
import type {
  Angle, ChatMessage, Concept, Feedback, Module, Note, Playbook, PlaybookEntry, Provider,
  ProviderRoute, Rendition, RoadmapDiff, SourceCard, Verdict,
} from './types'

export interface State {
  goal: typeof mock.goal
  modules: Module[]
  concepts: Concept[]
  cards: SourceCard[]
  playbook: Playbook
  renditions: Rendition[]
  feedback: Feedback[]
  notes: Note[]
  diffs: RoadmapDiff[]
  chats: Record<string, ChatMessage[]>
  answers: Record<string, { choice: number; correct: boolean }>
  routes: ProviderRoute[]
}

const STORAGE_KEY = 'deep-study-center/prototype/v1'

function initialState(): State {
  return {
    goal: mock.goal,
    modules: mock.modules,
    concepts: mock.concepts,
    cards: mock.cards,
    playbook: mock.initialPlaybook,
    renditions: mock.initialRenditions,
    feedback: [],
    notes: [],
    diffs: mock.initialDiffs,
    chats: {},
    answers: {},
    routes: mock.providerRoutes,
  }
}

function load(): State {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return { ...initialState(), ...JSON.parse(raw) }
  } catch { /* storage unavailable: start fresh */ }
  return initialState()
}

// ---- engine rules (mirrors Mentor's learner model, simplified) ----

const WORKS = 0.68
const AVOID = 0.32
const MIN_EVIDENCE = 1.5

function verdictFor(score: number, evidence: number): Verdict {
  if (evidence < MIN_EVIDENCE) return 'trying'
  if (score >= WORKS) return 'works'
  if (score <= AVOID) return 'avoid'
  return 'trying'
}

function nudge(entry: PlaybookEntry, delta: number, evidence = 1): PlaybookEntry {
  const score = Math.min(0.98, Math.max(0.02, entry.score + delta))
  const ev = entry.evidence + evidence
  return { ...entry, score, evidence: ev, verdict: verdictFor(score, ev) }
}

/** BKT step (slip 0.1, guess 0.25, transit 0.15), as in mentor_core.learner. */
function bkt(p: number, correct: boolean): number {
  const slip = 0.1, guess = 0.25, transit = 0.15
  const post = correct
    ? (p * (1 - slip)) / (p * (1 - slip) + (1 - p) * guess)
    : (p * slip) / (p * slip + (1 - p) * (1 - guess))
  return Math.min(1, post + (1 - post) * transit)
}

export function angleRanking(playbook: Playbook): Angle[] {
  const angles: Angle[] = ['geometric', 'algebraic', 'computational']
  const score = (a: Angle) => {
    const e = playbook.entries.find(x => x.dimension === 'angle' && x.value === a)
    if (!e) return 0.5
    return e.verdict === 'avoid' ? -1 : e.score
  }
  const evidence = (a: Angle) => playbook.entries.find(x => x.dimension === 'angle' && x.value === a)?.evidence ?? 0
  // Ties go to the less-tested angle, so near-equal options keep getting explored.
  return [...angles].sort((a, b) => score(b) - score(a) || evidence(a) - evidence(b))
}

export function isStale(r: Rendition | undefined, s: State): boolean {
  if (!r) return false
  const card = s.cards.find(c => c.conceptId === r.conceptId)
  return r.playbookVersion < s.playbook.version || (!!card && r.cardVersion < card.version)
}

function staleCount(s: State, version: number): number {
  return s.renditions.filter(r => r.playbookVersion < version).length
}

const uid = () => Math.random().toString(36).slice(2, 10)
const now = () => new Date().toISOString()

// ---- actions ----

export type Action =
  | { type: 'answer'; conceptId: string; checkId: string; angle: Angle; choice: number; correct: boolean }
  | { type: 'feedback'; conceptId: string; sectionId?: string; angle?: Angle; available?: Angle[]; tags: string[]; text: string }
  | { type: 'explainDifferently'; conceptId: string; sectionId: string; available: Angle[] }
  | { type: 'refresh'; conceptId: string; sectionIds: string[]; variants: Record<string, Angle[]> }
  | { type: 'markStudied'; conceptId: string }
  | { type: 'addNote'; conceptId: string; text: string; quote?: string }
  | { type: 'deleteNote'; id: string }
  | { type: 'chat'; conceptId: string; text: string; sectionHeading?: string }
  | { type: 'decideDiff'; id: string; approve: boolean }
  | { type: 'correctEntry'; id: string; verdict: Verdict | 'remove' }
  | { type: 'adjust'; key: keyof Playbook['adjust']; value: number }
  | { type: 'route'; role: string; provider: Provider; model: string }
  | { type: 'reset' }

const TAG_LABELS: Record<string, string> = {
  'framing-off': "The framing didn't work for me",
  'confused': 'I got lost / missing background',
  'too-abstract': 'Too abstract',
  'too-fast': 'Too fast',
  'too-slow': 'Too slow',
  'too-long': 'Too long',
  'more-rigor': 'I want more rigor',
  'loved-it': 'This worked really well',
}
export const FEEDBACK_TAGS = Object.entries(TAG_LABELS).map(([id, label]) => ({ id, label }))

function applyFeedback(s: State, a: Extract<Action, { type: 'feedback' }>): State {
  const effects: string[] = []
  let entries = s.playbook.entries
  const adjust = { ...s.playbook.adjust }
  let diffs = s.diffs
  const concept = s.concepts.find(c => c.id === a.conceptId)

  const touch = (match: (e: PlaybookEntry) => boolean, delta: number, why: string) => {
    entries = entries.map(e => {
      if (!match(e)) return e
      const next = nudge(e, delta)
      effects.push(`Playbook: "${e.value}" ${delta < 0 ? 'less' : 'more'} trusted (${e.score.toFixed(2)} → ${next.score.toFixed(2)}${next.verdict !== e.verdict ? `, now "${next.verdict}"` : ''}) ${why}`)
      return next
    })
  }
  const clamp = (v: number) => Math.max(-3, Math.min(3, v))

  for (const tag of a.tags) {
    if (tag === 'framing-off' && a.angle) touch(e => e.dimension === 'angle' && e.value === a.angle, -0.14, 'because the framing missed')
    if (tag === 'loved-it' && a.angle) touch(e => e.dimension === 'angle' && e.value === a.angle, +0.1, 'because it landed')
    if (tag === 'too-abstract') touch(e => e.dimension === 'angle' && e.value === 'computational', +0.08, '(more concrete, code-first)')
    if (tag === 'too-fast') { adjust.pace = clamp(adjust.pace - 1); effects.push(`Pace → ${adjust.pace}: smaller steps, more worked examples`) }
    if (tag === 'too-slow') { adjust.pace = clamp(adjust.pace + 1); effects.push(`Pace → ${adjust.pace}: fewer worked examples, skip what you show you know`) }
    if (tag === 'too-long') { adjust.depth = clamp(adjust.depth - 1); effects.push(`Depth → ${adjust.depth}: shorter lessons, details moved to "go deeper"`) }
    if (tag === 'more-rigor') { adjust.rigor = clamp(adjust.rigor + 1); effects.push(`Rigor → ${adjust.rigor}: proofs and formal statements earlier`) }
    if (tag === 'confused' && concept) {
      diffs = [{
        id: uid(), ts: now(), status: 'pending',
        reason: `You got lost in "${concept.title}"${a.sectionId ? ' (one section)' : ''}. A short refresher may be missing.`,
        changes: [
          { op: 'insert', title: `Coordinates & the plane (before ${concept.title})`, detail: '10-minute refresher: axes, coordinates, plotting points; 2 practice items.' },
          { op: 'deepen', title: concept.title, detail: 'Add one more worked example to each section at the current pace.' },
        ],
      }, ...diffs]
      effects.push('Roadmap: proposed a change for you to review (insert a refresher)')
    }
  }

  // A framing that missed here is replaced here right away, whatever the global ranking says.
  let renditions = s.renditions
  if (a.tags.includes('framing-off') && a.sectionId && a.angle && a.available && a.available.length > 1) {
    const ranking = angleRanking({ ...s.playbook, entries })
    const next = ranking.find(x => x !== a.angle && a.available!.includes(x))
    if (next) {
      renditions = renditions.map(r => r.conceptId === a.conceptId
        ? { ...r, sectionAngles: { ...r.sectionAngles, [a.sectionId!]: next }, pinned: { ...r.pinned, [a.sectionId!]: next } }
        : r)
      effects.unshift(`This section now uses the ${next} angle. Other lessons switch too if the pattern repeats.`)
    }
  }

  const playbookChanged = entries !== s.playbook.entries || JSON.stringify(adjust) !== JSON.stringify(s.playbook.adjust)
  const version = playbookChanged ? s.playbook.version + 1 : s.playbook.version
  if (playbookChanged) {
    const n = staleCount(s, version)
    effects.push(`Playbook v${version}: ${n} lesson${n === 1 ? '' : 's'} will be re-rendered for you (past ones offer a refresh)`)
  }
  if (a.text.trim()) effects.push('Your comment is logged and goes into the weekly reflection')
  if (!effects.length) effects.push('Logged')

  const fb: Feedback = {
    id: uid(), ts: now(), conceptId: a.conceptId, sectionId: a.sectionId,
    tags: a.tags.map(t => TAG_LABELS[t] ?? t), text: a.text, effects,
  }
  return { ...s, renditions, playbook: { version, entries, adjust }, diffs, feedback: [fb, ...s.feedback] }
}

function tutorReply(text: string, section?: string): string {
  const t = text.toLowerCase()
  if (/(just|tell me|give me).*(answer|solution)/.test(t))
    return "I'll give you the answer if you still want it after this hint: do the scaling step first, on each component separately, then add. What do you get for the first component?"
  if (t.includes('why'))
    return `Good question. Before I explain: in "${section ?? 'this section'}", what changes if you move along x? Does that affect your y-coordinate at all? Your answer is most of the "why".`
  if (t.includes('example'))
    return 'Here is one from your world: a batch of 32 images is 32 vectors of length 784. Adding a bias vector to each one is exactly the componentwise addition from this lesson. Want a second example from a different angle?'
  return `Let's work it out together. In one sentence, how would you explain "${section ?? 'this idea'}" to a colleague? I'll tell you which part is solid and which part to sharpen.`
}

function reducer(s: State, a: Action): State {
  switch (a.type) {
    case 'answer': {
      const concepts = s.concepts.map(c => {
        if (c.id !== a.conceptId) return c
        const mastery = bkt(c.mastery, a.correct)
        const correctCount = Object.entries(s.answers)
          .filter(([k, v]) => k.startsWith(a.conceptId + ':') && v.correct).length + (a.correct ? 1 : 0)
        const state = mastery >= 0.95 && correctCount >= 3 ? 'learned' : c.state === 'ready' ? 'learning' : c.state
        return { ...c, mastery, state }
      })
      // Outcome signal: weak evidence about the angle this section was taught with.
      const entries = s.playbook.entries.map(e =>
        e.dimension === 'angle' && e.value === a.angle ? nudge(e, a.correct ? 0.03 : -0.03, 0.3) : e)
      const unlocked = concepts.map(c => c.state === 'locked' && c.prereqs.every(p =>
        ['learned', 'mastered'].includes(concepts.find(x => x.id === p)?.state ?? '')) ? { ...c, state: 'ready' as const } : c)
      return {
        ...s, concepts: unlocked, playbook: { ...s.playbook, entries },
        answers: { ...s.answers, [`${a.conceptId}:${a.checkId}`]: { choice: a.choice, correct: a.correct } },
      }
    }
    case 'feedback':
      return applyFeedback(s, a)
    case 'explainDifferently': {
      const r = s.renditions.find(x => x.conceptId === a.conceptId)
      if (!r) return s
      const current = r.sectionAngles[a.sectionId]
      const order = angleRanking(s.playbook).filter(x => a.available.includes(x))
      const next = order[(order.indexOf(current) + 1) % order.length] ?? current
      const fb: Feedback = {
        id: uid(), ts: now(), conceptId: a.conceptId, sectionId: a.sectionId, tags: ['Explain it differently'], text: '',
        effects: [`Section switched: ${current} → ${next}`, `Weak signal recorded: "${current}" didn't land here`],
      }
      const entries = s.playbook.entries.map(e =>
        e.dimension === 'angle' && e.value === current ? nudge(e, -0.04, 0.3) : e)
      return {
        ...s,
        playbook: { ...s.playbook, entries },
        renditions: s.renditions.map(x => x === r ? { ...x, sectionAngles: { ...x.sectionAngles, [a.sectionId]: next }, pinned: { ...x.pinned, [a.sectionId]: next } } : x),
        feedback: [fb, ...s.feedback],
      }
    }
    case 'refresh': {
      const ranking = angleRanking(s.playbook)
      const card = s.cards.find(c => c.conceptId === a.conceptId)
      return {
        ...s,
        renditions: s.renditions.map(r => {
          if (r.conceptId !== a.conceptId) return r
          const sectionAngles: Record<string, Angle> = {}
          for (const id of a.sectionIds) {
            const avail = a.variants[id] ?? []
            const pin = r.pinned?.[id]
            sectionAngles[id] = pin && avail.includes(pin) ? pin : ranking.find(x => avail.includes(x)) ?? avail[0] ?? 'geometric'
          }
          return { ...r, sectionAngles, playbookVersion: s.playbook.version, cardVersion: card?.version ?? r.cardVersion }
        }),
      }
    }
    case 'markStudied':
      return { ...s, renditions: s.renditions.map(r => r.conceptId === a.conceptId ? { ...r, studied: true } : r) }
    case 'addNote':
      return { ...s, notes: [{ id: uid(), ts: now(), conceptId: a.conceptId, text: a.text, quote: a.quote }, ...s.notes] }
    case 'deleteNote':
      return { ...s, notes: s.notes.filter(n => n.id !== a.id) }
    case 'chat': {
      const thread = s.chats[a.conceptId] ?? []
      return {
        ...s,
        chats: { ...s.chats, [a.conceptId]: [...thread, { role: 'me', text: a.text }, { role: 'tutor', text: tutorReply(a.text, a.sectionHeading) }] },
      }
    }
    case 'decideDiff': {
      const diff = s.diffs.find(d => d.id === a.id)
      if (!diff) return s
      let { modules, concepts } = s
      if (a.approve && diff.changes.some(c => c.op === 'insert') && !concepts.some(c => c.id === 'c-coords')) {
        concepts = [{ id: 'c-coords', moduleId: 'm-la', title: 'Coordinates & the plane', objective: 'Read and plot points in 2D and 3D coordinates.', minutes: 10, prereqs: [], state: 'ready', mastery: 0.3 }, ...concepts]
        modules = modules.map(m => m.id === 'm-la' ? { ...m, conceptIds: ['c-coords', ...m.conceptIds] } : m)
      }
      return { ...s, modules, concepts, diffs: s.diffs.map(d => d.id === a.id ? { ...d, status: a.approve ? 'approved' : 'rejected' } : d) }
    }
    case 'correctEntry': {
      const entries = a.verdict === 'remove'
        ? s.playbook.entries.filter(e => e.id !== a.id)
        : s.playbook.entries.map(e => e.id === a.id ? { ...e, verdict: a.verdict as Verdict, note: `${e.note} Corrected by you.` } : e)
      return { ...s, playbook: { ...s.playbook, entries, version: s.playbook.version + 1 } }
    }
    case 'adjust':
      return { ...s, playbook: { ...s.playbook, adjust: { ...s.playbook.adjust, [a.key]: a.value }, version: s.playbook.version + 1 } }
    case 'route':
      return { ...s, routes: s.routes.map(r => r.role === a.role ? { ...r, provider: a.provider, model: a.model } : r) }
    case 'reset':
      return initialState()
  }
}

const Ctx = createContext<{ s: State; dispatch: (a: Action) => void } | null>(null)

export function StoreProvider({ children }: { children: ReactNode }) {
  const [s, dispatch] = useReducer(reducer, undefined, load)
  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(s)) } catch { /* ignore */ }
  }, [s])
  return <Ctx.Provider value={{ s, dispatch }}>{children}</Ctx.Provider>
}

export function useStore() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useStore outside StoreProvider')
  return v
}
