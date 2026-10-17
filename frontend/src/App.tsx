import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

const exampleTopics = ['AI agent reliability', 'Future of remote work', 'Climate tech in 2026']
const stages = ['PLANNING', 'SEARCHING', 'EXTRACTING', 'RANKING', 'SYNTHESIZING', 'DONE']
type RunStatus = 'idle' | 'running' | 'done' | 'error'

type ReportEvent = {
  type?: string
  payload?: {
    stage?: string
    token?: string
    error?: string
  }
}

function App() {
  const [topic, setTopic] = useState('')
  const [status, setStatus] = useState<RunStatus>('idle')
  const [stage, setStage] = useState('READY')
  const [events, setEvents] = useState<string[]>([])
  const [report, setReport] = useState('')
  const [error, setError] = useState('')
  const eventSource = useRef<EventSource | null>(null)

  useEffect(() => () => eventSource.current?.close(), [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const requestedTopic = topic.trim()
    if (!requestedTopic || status === 'running') {
      setError('Enter a topic before starting research.')
      return
    }

    eventSource.current?.close()
    setStatus('running')
    setStage('PLANNING')
    setEvents([])
    setReport('')
    setError('')

    try {
      const response = await fetch('/api/reports', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ topic: requestedTopic }),
      })
      const payload = await response.json()
      if (!response.ok || !payload.id) {
        throw new Error(payload.detail || 'The research run could not be started.')
      }

      const source = new EventSource(`/api/reports/${payload.id}/events`)
      eventSource.current = source
      let terminal = false
      const eventTypes = ['stage_started', 'stage_completed', 'source_fetched', 'report_token', 'run_completed', 'run_failed']
      const handleReportEvent = (incoming: Event) => {
        const message = incoming as MessageEvent<string>
        let data: ReportEvent
        try {
          data = JSON.parse(message.data) as ReportEvent
        } catch {
          setStatus('error')
          setError('The server sent an invalid progress event.')
          source.close()
          return
        }
        const eventType = data.type || incoming.type
        setEvents((previous) => [...previous, eventType])
        if (data.payload?.stage) setStage(data.payload.stage)
        const token = data.payload?.token
        if (token) setReport((previous) => previous + token)
        if (eventType === 'run_failed') {
          terminal = true
          source.close()
          setStatus('error')
          setError(data.payload?.error || 'The research run failed.')
        }
        if (eventType === 'run_completed') {
          terminal = true
          source.close()
          setStage('DONE')
          setStatus('done')
          void fetch(`/api/reports/${payload.id}/report.md`)
            .then(async (reportResponse) => {
              if (!reportResponse.ok) throw new Error('The finished report could not be loaded.')
              setReport(await reportResponse.text())
            })
            .catch((reportError: Error) => {
              setStatus('error')
              setError(reportError.message)
            })
        }
      }
      eventTypes.forEach((eventType) => source.addEventListener(eventType, handleReportEvent))
      source.onerror = () => {
        if (!terminal) {
          setStatus('error')
          setError('The live progress connection closed unexpectedly.')
          source.close()
        }
      }
    } catch (requestError) {
      setStatus('error')
      setError(requestError instanceof Error ? requestError.message : 'The research run could not be started.')
    }
  }

  return (
    <main className="mission-control">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true">
          R
        </div>
        <div>
          <p className="eyebrow">OMNIRUSH / RESEARCH SYSTEM</p>
          <p className="brand-name">One-Click Reports</p>
        </div>
        <div className="connection-status">
          <span className={`status-dot ${status === 'error' ? 'offline' : ''}`} />
          {status === 'running' ? 'RESEARCH ACTIVE' : status === 'done' ? 'REPORT READY' : status === 'error' ? 'CHECK FAILED' : 'SYSTEM READY'}
        </div>
      </header>

      <section className="hero-section">
        <p className="eyebrow accent">AUTONOMOUS RESEARCH, ON DEMAND</p>
        <h1>Turn a question into a report.</h1>
        <p className="hero-copy">
          Watch an AI research agent search the web, read the best sources, and assemble a
          citation-backed report you can share.
        </p>

        <form className="topic-form" onSubmit={handleSubmit}>
          <label htmlFor="topic">What should we research?</label>
          <div className="input-row">
            <input
              id="topic"
              type="text"
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              placeholder="e.g. How will AI change customer support?"
            />
            <button type="submit" disabled={status === 'running'}>
              {status === 'running' ? 'Researching…' : 'Start research'} <span aria-hidden="true">→</span>
            </button>
          </div>
        </form>

        {error && <p className="run-error" role="alert">{error}</p>}

        {status !== 'idle' && (
          <section className="run-panel" aria-live="polite">
            <div className="run-panel-heading">
              <div>
                <p className="eyebrow">LIVE RUN</p>
                <h2>{status === 'done' ? 'Report ready' : status === 'error' ? 'Run stopped' : 'Research in progress'}</h2>
              </div>
              <span className="phase-label">{stage}</span>
            </div>
            <div className="run-stages">
              {stages.map((runStage) => (
                <span className={stages.indexOf(runStage) <= stages.indexOf(stage) ? 'run-stage active' : 'run-stage'} key={runStage}>
                  {runStage}
                </span>
              ))}
            </div>
            {events.length > 0 && <p className="event-count">{events.length} live events received</p>}
          </section>
        )}

        {report && (
          <article className="report-panel">
            <div className="run-panel-heading">
              <div>
                <p className="eyebrow accent">CITATION-BACKED OUTPUT</p>
                <h2>Research report</h2>
              </div>
              <span className="phase-label">MARKDOWN</span>
            </div>
            <pre className="report-output">{report}</pre>
          </article>
        )}

        <div className="examples" aria-label="Example topics">
          <span>TRY AN EXAMPLE</span>
          {exampleTopics.map((example) => (
            <button key={example} type="button" onClick={() => setTopic(example)}>
              {example}
            </button>
          ))}
        </div>
      </section>

      <section className="pipeline-preview" aria-label="Research pipeline">
        <div className="section-heading">
          <div>
            <p className="eyebrow">PIPELINE PREVIEW</p>
            <h2>From prompt to proof</h2>
          </div>
          <span className="phase-label">PHASE 01 / READY</span>
        </div>
        <div className="stage-grid">
          {['Plan the search', 'Read the sources', 'Write with citations'].map((stage, index) => (
            <article className="stage-card" key={stage}>
              <span className="stage-number">0{index + 1}</span>
              <h3>{stage}</h3>
              <p>
                {index === 0 && 'Break your topic into focused research questions.'}
                {index === 1 && 'Extract and rank evidence from trusted sources.'}
                {index === 2 && 'Deliver a clear report with verifiable references.'}
              </p>
            </article>
          ))}
        </div>
      </section>
    </main>
  )
}

export default App
