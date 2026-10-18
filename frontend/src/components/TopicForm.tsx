import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'

const EXAMPLE_TOPICS = [
  'Quantum computing 2026',
  'AI agent reliability',
  'Future of remote work',
  'Climate tech in 2026',
]

type TopicFormProps = {
  topic: string
  isRunning: boolean
  onTopicChange: (topic: string) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

// Minimal typing for the browser SpeechRecognition API (Chromium + Safari
// expose it, other browsers get a graceful disabled button).
type SpeechRecognitionLike = {
  lang: string
  interimResults: boolean
  continuous: boolean
  onresult: ((event: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null
  onend: (() => void) | null
  onerror: (() => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike

function getSpeechCtor(): SpeechRecognitionCtor | null {
  if (typeof window === 'undefined') return null
  const w = window as unknown as { SpeechRecognition?: SpeechRecognitionCtor; webkitSpeechRecognition?: SpeechRecognitionCtor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

function TopicForm({ topic, isRunning, onTopicChange, onSubmit }: TopicFormProps) {
  const [listening, setListening] = useState(false)
  const [voiceError, setVoiceError] = useState<string | null>(null)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const supported = getSpeechCtor() !== null

  useEffect(() => () => recognitionRef.current?.abort(), [])

  function toggleVoice() {
    if (!supported) {
      setVoiceError('Voice capture is unavailable in this browser.')
      return
    }
    if (listening) {
      recognitionRef.current?.stop()
      return
    }
    const Ctor = getSpeechCtor()
    if (!Ctor) return
    const recognition = new Ctor()
    recognition.lang = 'en-US'
    recognition.interimResults = true
    recognition.continuous = false
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0].transcript)
        .join(' ')
      onTopicChange(transcript.trim())
    }
    recognition.onend = () => {
      setListening(false)
    }
    recognition.onerror = () => {
      setListening(false)
      setVoiceError('Microphone capture failed. Check browser permissions.')
      window.setTimeout(() => setVoiceError(null), 3200)
    }
    recognitionRef.current = recognition
    setListening(true)
    setVoiceError(null)
    recognition.start()
  }

  return (
    <div className="topic-form-wrap">
      <form className="topic-form" onSubmit={onSubmit}>
        <label htmlFor="topic">What should we research?</label>
        <div className="input-row">
          <input
            id="topic"
            type="text"
            value={topic}
            onChange={(event) => onTopicChange(event.target.value)}
            placeholder="e.g. How will AI change customer support?"
            maxLength={500}
            disabled={isRunning}
            data-listening={listening || undefined}
          />
          <button
            type="button"
            className={`voice-toggle${listening ? ' listening' : ''}`}
            onClick={toggleVoice}
            disabled={isRunning || !supported}
            aria-pressed={listening}
            aria-label={listening ? 'Stop voice capture' : 'Start voice capture'}
            title={supported ? 'Speak your topic' : 'Voice capture not supported in this browser'}
          >
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path
                fill="currentColor"
                d="M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V22h2v-3.08A7 7 0 0 0 19 12h-2z"
              />
            </svg>
            <span className="voice-wave" aria-hidden="true">
              <i /><i /><i />
            </span>
          </button>
          <button type="submit" disabled={isRunning}>
            {isRunning ? 'Researching…' : 'Start research'} <span aria-hidden="true">→</span>
          </button>
        </div>
        {voiceError && <p className="voice-error" role="status">{voiceError}</p>}
      </form>

      <div className="examples" aria-label="Example topics">
        <span>TRY AN EXAMPLE</span>
        {EXAMPLE_TOPICS.map((example) => (
          <button key={example} type="button" onClick={() => onTopicChange(example)} disabled={isRunning}>
            {example}
          </button>
        ))}
      </div>
    </div>
  )
}

export default TopicForm
