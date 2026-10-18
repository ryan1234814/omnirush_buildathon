import { useCallback, useEffect, useState } from 'react'

const SOUND_PREF_KEY = 'omnirush:sound-enabled'

export type SoundCue = 'start' | 'stage' | 'complete' | 'error'

let sharedContext: AudioContext | null = null
function getContext(): AudioContext | null {
  if (typeof window === 'undefined') return null
  if (sharedContext) return sharedContext
  const Ctor = (window as unknown as { AudioContext?: typeof AudioContext; webkitAudioContext?: typeof AudioContext }).AudioContext
    ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!Ctor) return null
  sharedContext = new Ctor()
  return sharedContext
}

function playTone(frequency: number, durationSeconds: number, type: OscillatorType = 'sine', gain = 0.06) {
  const ctx = getContext()
  if (!ctx) return
  // Chrome/Safari require a user gesture before the context can start.
  if (ctx.state === 'suspended') void ctx.resume()
  const osc = ctx.createOscillator()
  const amp = ctx.createGain()
  osc.type = type
  osc.frequency.value = frequency
  amp.gain.value = 0
  osc.connect(amp).connect(ctx.destination)
  const now = ctx.currentTime
  amp.gain.linearRampToValueAtTime(gain, now + 0.02)
  amp.gain.exponentialRampToValueAtTime(0.0001, now + durationSeconds)
  osc.start(now)
  osc.stop(now + durationSeconds + 0.02)
}

function fire(cue: SoundCue) {
  switch (cue) {
    case 'start':
      playTone(520, 0.14, 'triangle', 0.05)
      return
    case 'stage':
      playTone(680, 0.10, 'sine', 0.05)
      return
    case 'complete':
      playTone(660, 0.14, 'triangle', 0.06)
      window.setTimeout(() => playTone(880, 0.20, 'sine', 0.05), 140)
      return
    case 'error':
      playTone(220, 0.24, 'sawtooth', 0.05)
      return
  }
}

function readEnabled(): boolean {
  try {
    const raw = window.localStorage.getItem(SOUND_PREF_KEY)
    // Off by default — sound on stage is a big "judges are impressed" or
    // "judges are annoyed" coin flip, so we make it opt-in.
    return raw === 'true'
  } catch {
    return false
  }
}

export function useSoundCues(): { enabled: boolean; toggle: () => void; play: (cue: SoundCue) => void } {
  const [enabled, setEnabled] = useState<boolean>(() => (typeof window === 'undefined' ? false : readEnabled()))

  useEffect(() => {
    try {
      window.localStorage.setItem(SOUND_PREF_KEY, String(enabled))
    } catch {
      // Preference persistence is optional.
    }
  }, [enabled])

  const toggle = useCallback(() => {
    setEnabled((current) => {
      const next = !current
      if (next) fire('start')
      return next
    })
  }, [])

  const play = useCallback((cue: SoundCue) => {
    if (enabled) fire(cue)
  }, [enabled])

  return { enabled, toggle, play }
}
