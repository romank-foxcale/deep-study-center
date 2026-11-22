// Local dictation (SPEC §27): record the microphone one phrase at a time and send each phrase to the backend's
// Whisper model (POST /api/transcribe). The audio never leaves this computer.
//
// A phrase ends after a short silence (or after MAX_PHRASE_MS). One MediaRecorder runs per phrase, so each blob is a
// complete, decodable file; the recorder is cut only during silence, so no word is clipped. Phrases without speech
// are dropped. Results arrive in order (one request at a time).

const SILENCE_MS = 700
const MAX_PHRASE_MS = 20000
const MIN_SPEECH_MS = 250
const TICK_MS = 50

export interface LocalDictationHandlers {
  onText: (text: string) => void
  onBusy: (pending: number) => void
  onError: (message: string) => void
  onEnd: () => void
}

export interface LocalDictation { stop: () => void }

/** The level above which a frame counts as speech: a few times the running noise floor, with a minimum. */
export function speechThreshold(noiseFloor: number): number {
  return Math.max(0.015, noiseFloor * 3)
}

/** Root mean square of a block of samples in -1..1. */
export function rms(samples: Float32Array): number {
  let sum = 0
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i]
  return Math.sqrt(sum / Math.max(1, samples.length))
}

const pickMime = () =>
  ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/webm', 'audio/mp4'].find(t => MediaRecorder.isTypeSupported?.(t)) ?? ''

export async function transcribe(blob: Blob): Promise<string> {
  const r = await fetch('/api/transcribe', { method: 'POST', body: blob, headers: { 'Content-Type': blob.type || 'application/octet-stream' } })
  if (!r.ok) {
    let msg = `${r.status}`
    try { msg = (await r.json()).detail ?? msg } catch { /* not JSON */ }
    throw new Error(msg)
  }
  return ((await r.json()).text ?? '').trim()
}

export const localDictationSupported = () =>
  typeof window !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined'

export async function startLocalDictation(h: LocalDictationHandlers): Promise<LocalDictation> {
  let stream: MediaStream
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
  } catch (e) {
    const name = (e as DOMException).name
    h.onError(name === 'NotAllowedError' ? 'Microphone access was refused.' : `No microphone (${name || (e as Error).message}).`)
    h.onEnd()
    return { stop: () => {} }
  }
  const ctx = new AudioContext()
  const analyser = ctx.createAnalyser()
  analyser.fftSize = 2048
  ctx.createMediaStreamSource(stream).connect(analyser)
  const buf = new Float32Array(analyser.fftSize)
  const mime = pickMime()

  let stopped = false
  let phraseStart = 0
  let speechMs = 0
  let lastSpeech = 0
  let noise = 0.01
  let pending = 0
  let queue = Promise.resolve()

  const send = (blob: Blob) => {
    pending += 1
    h.onBusy(pending)
    queue = queue.then(async () => {
      try {
        const text = await transcribe(blob)
        if (text) h.onText(text)
      } catch (e) {
        h.onError(`Local dictation failed: ${(e as Error).message}`)
      } finally {
        pending -= 1
        h.onBusy(pending)
      }
    })
  }

  const newRecorder = () => {
    speechMs = 0
    phraseStart = performance.now()
    lastSpeech = 0
    const r = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
    const mine: Blob[] = []
    const hadSpeech = () => speechMs >= MIN_SPEECH_MS
    let keep = false
    r.ondataavailable = e => { if (e.data.size) mine.push(e.data) }
    r.onstop = () => { if (keep && mine.length) send(new Blob(mine, { type: r.mimeType || mime })) }
    r.start()
    return { cut: () => { keep = hadSpeech(); if (r.state !== 'inactive') r.stop() } }
  }

  let current = newRecorder()
  const timer = setInterval(() => {
    if (stopped) return
    analyser.getFloatTimeDomainData(buf)
    const level = rms(buf)
    const now = performance.now()
    if (level > speechThreshold(noise)) {
      speechMs += TICK_MS
      lastSpeech = now
    } else {
      noise = noise * 0.95 + level * 0.05  // follow the room's noise only while nobody speaks
    }
    // End the phrase after a pause (a pause after only a click or a cough also restarts it, and that blob is dropped),
    // or when it gets too long.
    const pause = lastSpeech > 0 && now - lastSpeech > SILENCE_MS
    if (pause || now - phraseStart > MAX_PHRASE_MS) {
      current.cut()
      current = newRecorder()
    }
  }, TICK_MS)

  return {
    stop: () => {
      if (stopped) return
      stopped = true
      clearInterval(timer)
      current.cut()
      stream.getTracks().forEach(t => t.stop())
      void ctx.close()
      void queue.then(() => h.onEnd())
    },
  }
}
