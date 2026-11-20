import { useEffect, useRef, useState } from 'react'

/** What the learner sends with an answer, besides the answer itself. */
export interface Reasoning { thinking: string; confidence: number | null }
export const NO_REASONING: Reasoning = { thinking: '', confidence: null }

/** Confidence labels; the value sent is 0..1. A right answer at "Guess" counts as half. */
const LEVELS = [
  { at: 0.1, label: 'Guess' }, { at: 0.35, label: 'Unsure' }, { at: 0.6, label: 'Fairly sure' },
  { at: 0.85, label: 'Sure' }, { at: 1.01, label: 'Certain' },
]
export const confidenceLabel = (c: number) => (LEVELS.find(l => c <= l.at) ?? LEVELS[LEVELS.length - 1]).label

// ---------------------------------------------------------------- dictation (browser speech recognition)

interface SpeechResult { isFinal: boolean; 0: { transcript: string } }
interface SpeechEvent { resultIndex: number; results: ArrayLike<SpeechResult> }
interface Recognizer {
  continuous: boolean; interimResults: boolean; lang: string
  onresult: ((e: SpeechEvent) => void) | null; onend: (() => void) | null; onerror: ((e: { error: string }) => void) | null
  start(): void; stop(): void
}
type RecognizerCtor = new () => Recognizer
const speechCtor = (): RecognizerCtor | undefined => {
  const w = window as unknown as { SpeechRecognition?: RecognizerCtor; webkitSpeechRecognition?: RecognizerCtor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition
}

/** Speech to text: final phrases are appended through onText; interim text is shown while you speak. */
export function useDictation(onText: (text: string) => void) {
  const rec = useRef<Recognizer | null>(null)
  const sink = useRef(onText)
  const [on, setOn] = useState(false)
  const [interim, setInterim] = useState('')
  const [error, setError] = useState('')
  useEffect(() => { sink.current = onText }, [onText])
  useEffect(() => () => rec.current?.stop(), [])
  const supported = !!speechCtor()
  const start = () => {
    const Ctor = speechCtor()
    if (!Ctor) return
    const r = new Ctor()
    r.continuous = true
    r.interimResults = true
    r.lang = navigator.language || 'en-US'
    r.onresult = e => {
      let live = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i]
        if (res.isFinal) sink.current(res[0].transcript.trim())
        else live += res[0].transcript
      }
      setInterim(live)
    }
    r.onerror = e => setError(e.error === 'not-allowed' ? 'Microphone access was refused.' : `Dictation stopped (${e.error}).`)
    r.onend = () => { setOn(false); setInterim('') }
    rec.current = r
    setError('')
    r.start()
    setOn(true)
  }
  const stop = () => rec.current?.stop()
  return { supported, on, interim, error, toggle: () => (on ? stop() : start()) }
}

export function MicButton({ dictation }: { dictation: ReturnType<typeof useDictation> }) {
  if (!dictation.supported) return null
  return (
    <button type="button" className={`btn btn-small mic ${dictation.on ? 'mic-on' : ''}`} onClick={dictation.toggle}
      title={dictation.on ? 'Stop dictation' : 'Dictate: speak your thinking'} aria-pressed={dictation.on}>
      <span className="mic-dot" aria-hidden />{dictation.on ? 'Listening… stop' : 'Dictate'}
    </button>
  )
}

/** A text area with dictation. Spoken phrases are added at the end. */
export function DictationArea({ value, onChange, rows = 3, placeholder, disabled }: {
  value: string; onChange: (v: string) => void; rows?: number; placeholder?: string; disabled?: boolean
}) {
  const latest = useRef(value)
  useEffect(() => { latest.current = value }, [value])
  const dictation = useDictation(t => { const v = latest.current; onChange(v && !/\s$/.test(v) ? `${v} ${t}` : v + t) })
  return (
    <div className="dictation">
      <textarea className="input" rows={rows} value={value} placeholder={placeholder} disabled={disabled}
        onChange={e => onChange(e.target.value)} />
      <div className="row dictation-bar">
        <MicButton dictation={dictation} />
        {dictation.interim && <span className="muted small dictation-live">{dictation.interim}</span>}
        {dictation.error && <span className="error small">{dictation.error}</span>}
      </div>
    </div>
  )
}

export function ConfidenceSlider({ value, onChange, disabled }: { value: number | null; onChange: (v: number | null) => void; disabled?: boolean }) {
  return (
    <div className={`confidence ${value === null ? 'confidence-unset' : ''}`}>
      <span className="small">How sure are you?</span>
      <input type="range" min={0} max={100} step={5} value={value === null ? 50 : Math.round(value * 100)} disabled={disabled}
        aria-label="Confidence" onChange={e => onChange(Number(e.target.value) / 100)}
        onClick={e => { if (value === null) onChange(Number((e.target as HTMLInputElement).value) / 100) }} />
      <span className="small confidence-value">{value === null ? 'not set' : `${Math.round(value * 100)}% · ${confidenceLabel(value)}`}</span>
      {value !== null && !disabled && <button type="button" className="link small" onClick={() => onChange(null)}>clear</button>}
    </div>
  )
}

/** The thinking box and confidence slider under a question. Both are optional; the thinking is what helps most. */
export default function ThinkingInput({ value, onChange, disabled, placeholder }: {
  value: Reasoning; onChange: (r: Reasoning) => void; disabled?: boolean; placeholder?: string
}) {
  return (
    <div className="thinking">
      <DictationArea value={value.thinking} rows={2} disabled={disabled} onChange={thinking => onChange({ ...value, thinking })}
        placeholder={placeholder ?? 'Think out loud (optional): what do you expect, and why? Messy is fine.'} />
      <ConfidenceSlider value={value.confidence} disabled={disabled} onChange={confidence => onChange({ ...value, confidence })} />
    </div>
  )
}

/** After answering: what you wrote and how sure you were. */
export function ReasoningShown({ thinking, confidence }: { thinking?: string; confidence?: number | null }) {
  if (!thinking && (confidence === null || confidence === undefined)) return null
  return (
    <div className="reasoning-shown small">
      {confidence !== null && confidence !== undefined && <span className="pill">{Math.round(confidence * 100)}% · {confidenceLabel(confidence)}</span>}
      {thinking && <span className="muted"> Your thinking: “{thinking}”</span>}
    </div>
  )
}
