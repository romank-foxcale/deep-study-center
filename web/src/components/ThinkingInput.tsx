import { useEffect, useRef, useState } from 'react'
import { useDictationSettings } from '../store'
import { localDictationSupported, startLocalDictation, type LocalDictation } from './localDictation'

/** What the learner sends with an answer, besides the answer itself. */
export interface Reasoning { thinking: string; confidence: number | null }
export const NO_REASONING: Reasoning = { thinking: '', confidence: null }

/** Confidence = how likely you think your pick is right (0..1). The slider snaps to these stops, with more of them near
 *  the top, where "sure" and "certain" differ. A right answer at or below chance (1/n) or 30% counts as a guess (SPEC §26). */
const STOPS = [
  { at: 0, label: 'I think it is wrong' }, { at: 0.3, label: 'Doubtful' }, { at: 0.5, label: 'Coin flip' },
  { at: 0.7, label: 'Fairly sure' }, { at: 0.9, label: 'Sure' }, { at: 1, label: 'Certain' },
]
const nearest = (c: number) => STOPS.reduce((best, s, i) => (Math.abs(s.at - c) < Math.abs(STOPS[best].at - c) ? i : best), 0)
export const confidenceLabel = (c: number) => STOPS[nearest(c)].label

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

/** Speech to text: final phrases are appended through onText; interim text is shown while you speak.
 *  Two engines: the browser's speech API (audio goes to the browser maker's servers), or local Whisper (SPEC §27),
 *  used when Settings → Dictation says "local", or when the browser has no speech API and a model is installed. */
export function useDictation(onText: (text: string) => void) {
  const rec = useRef<Recognizer | null>(null)
  const local = useRef<LocalDictation | null>(null)
  const sink = useRef(onText)
  const [on, setOn] = useState(false)
  const [interim, setInterim] = useState('')
  const [error, setError] = useState('')
  const settings = useDictationSettings()
  useEffect(() => { sink.current = onText }, [onText])
  useEffect(() => () => { rec.current?.stop(); local.current?.stop() }, [])
  const localReady = !!settings?.ready && localDictationSupported()
  const useLocal = localReady && (settings?.mode === 'local' || !speechCtor())
  const supported = useLocal || !!speechCtor()
  const startLocal = async () => {
    setError('')
    setOn(true)
    setInterim('Listening…')
    local.current = await startLocalDictation({
      onText: t => sink.current(t),
      onBusy: n => setInterim(n > 0 ? 'Writing down what you said…' : 'Listening…'),
      onError: m => setError(m),
      onEnd: () => { setOn(false); setInterim(''); local.current = null },
    })
  }
  const start = () => {
    if (useLocal) { void startLocal(); return }
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
  const stop = () => { rec.current?.stop(); local.current?.stop() }
  return { supported, on, interim, error, local: useLocal, toggle: () => (on ? stop() : start()) }
}

export function MicButton({ dictation }: { dictation: ReturnType<typeof useDictation> }) {
  if (!dictation.supported) return null
  return (
    <button type="button" className={`btn btn-small mic ${dictation.on ? 'mic-on' : ''}`} onClick={dictation.toggle}
      title={dictation.on ? 'Stop dictation' : `Dictate: speak your thinking${dictation.local ? ' (on this computer)' : ''}`} aria-pressed={dictation.on}>
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
      <span className="small">How likely is your pick right?</span>
      <input type="range" min={0} max={STOPS.length - 1} step={1} value={nearest(value ?? 0.5)} disabled={disabled}
        aria-label="Confidence" aria-valuetext={value === null ? 'not set' : confidenceLabel(value)}
        onChange={e => onChange(STOPS[Number(e.target.value)].at)}
        onClick={e => { if (value === null) onChange(STOPS[Number((e.target as HTMLInputElement).value)].at) }} />
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
