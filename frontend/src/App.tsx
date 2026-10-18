import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  createReport,
  getReport,
  type ReportEvent,
  type ReportSnapshot,
  ReportEventStream,
  type RunStage,
} from './api/client'
import PdfDownload from './components/PdfDownload'
import ProgressTimeline from './components/ProgressTimeline'
import ReportView from './components/ReportView'
import TopicForm from './components/TopicForm'
import './App.css'

type AppStatus = 'idle' | 'running' | 'done' | 'error'

const LAST_RUN_KEY = 'omnirush:last-run-id'
const INITIAL_TOPIC = 'Quantum computing 2026'

type FetchedSource = {
  url: string
  ok: boolean
  bytes: number
}

function readLastRunId(): string | null {
  try {
    return window.localStorage.getItem(LAST_RUN_KEY)
  } catch {
    return null
  }
}

function saveLastRunId(runId: string): void {
  try {
    window.localStorage.setItem(LAST_RUN_KEY, runId)
  } catch {
    // Storage is optional; the active run still works without it.
  }
}

function removeLastRunId(): void {
  try {
    window.localStorage.removeItem(LAST_RUN_KEY)
  } catch {
    // Storage is optional.
  }
}

function App() {
  const [topic, setTopic] = useState(INITIAL_TOPIC)
  const [status, setStatus] = useState<AppStatus>('idle')
  const [stage, setStage] = useState<RunStage>('PLANNING')
  const [runId, setRunId] = useState<string | null>(null)
  const [sourceCount, setSourceCount] = useState(0)
  const [sourceTotal, setSourceTotal] = useState<number | null>(null)
  const [fetchedSources, setFetchedSources] = useState<FetchedSource[]>([])
  const [eventCount, setEventCount] = useState(0)
  const [report, setReport] = useState('')
  const [sources, setSources] = useState<ReportSnapshot['sources']>([])
  const [error, setError] = useState('')
  const [connectionNote, setConnectionNote] = useState('')
  const stream = useRef<ReportEventStream | null>(null)
  const activeRunId = useRef<string | null>(null)
  const hydratedReport = useRef(false)

  const closeStream = useCallback(() => {
    stream.current?.close()
    stream.current = null
  }, [])

  const applySnapshot = useCallback((snapshot: ReportSnapshot) => {
    setRunId(snapshot.id)
    setTopic(snapshot.topic)
    setStage(snapshot.stage)
    setSources(snapshot.sources)
    setReport(snapshot.report_md ?? '')
    setSourceCount(snapshot.sources.length)
    setSourceTotal(snapshot.sources.length || null)
    setFetchedSources(snapshot.sources.map((source) => ({ url: source.url, ok: true, bytes: 0 })))
    setError(snapshot.error ?? '')
    hydratedReport.current = Boolean(snapshot.report_md)
  }, [])

  const finishFromSnapshot = useCallback(async (id: string, snapshot?: ReportSnapshot) => {
    const latest = snapshot ?? await getReport(id)
    if (activeRunId.current !== id) return
    applySnapshot(latest)
    if (latest.status === 'completed') {
      setStage('DONE')
      setStatus('done')
      setConnectionNote('')
    } else if (latest.status === 'failed') {
      setStage('FAILED')
      setStatus('error')
      setError(latest.error ?? 'The research run failed.')
      setConnectionNote('')
    }
  }, [applySnapshot])

  const handleEvent = useCallback((id: string, incoming: ReportEvent) => {
    if (activeRunId.current !== id) return

    setEventCount((count) => count + 1)
    const payload = incoming.payload
    if (payload.stage) setStage(payload.stage)

    if (incoming.type === 'source_fetched') {
      const sourceUrl = payload.url
      if (sourceUrl) {
        setFetchedSources((current) => {
          if (current.some((source) => source.url === sourceUrl)) return current
          return [
            ...current,
            {
              url: sourceUrl,
              ok: payload.ok !== false,
              bytes: typeof payload.bytes === 'number' ? payload.bytes : 0,
            },
          ]
        })
      }
      setSourceCount((count) => count + 1)
    }
    if (incoming.type === 'stage_completed' && payload.stage === 'EXTRACTING' && typeof payload.sources === 'number') {
      setSourceTotal(payload.sources)
    }
    if (incoming.type === 'report_token' && !hydratedReport.current && payload.token) {
      setReport((current) => current + payload.token)
    }
    if (incoming.type === 'run_completed') {
      closeStream()
      void finishFromSnapshot(id).catch((terminalError: unknown) => {
        if (activeRunId.current !== id) return
        setStatus('error')
        setError(terminalError instanceof Error ? terminalError.message : 'The finished report could not be loaded.')
        setConnectionNote('')
      })
    }
    if (incoming.type === 'run_failed') {
      closeStream()
      setStage('FAILED')
      setStatus('error')
      setError(payload.error || 'The research run failed.')
      setConnectionNote('')
    }
  }, [closeStream, finishFromSnapshot])

  const connectToRun = useCallback((id: string) => {
    closeStream()
    activeRunId.current = id
    setStatus('running')
    setConnectionNote('')
    const nextStream = new ReportEventStream(id, {
      onEvent: (incoming) => handleEvent(id, incoming),
      onOpen: () => setConnectionNote('Live connection established.'),
      onRetry: (attempt) => setConnectionNote(`Connection interrupted. Reconnecting (${attempt}/3)…`),
      onError: (streamError) => {
        if (activeRunId.current !== id) return
        setStatus('error')
        setError(streamError.message)
        setConnectionNote('')
      },
    })
    stream.current = nextStream
  }, [closeStream, handleEvent])

  useEffect(() => {
    const id = readLastRunId()
    if (!id) return
    activeRunId.current = id
    void getReport(id)
      .then((snapshot) => {
        if (activeRunId.current !== id) return
        applySnapshot(snapshot)
        if (snapshot.status === 'completed') {
          setStatus('done')
          setStage('DONE')
        } else if (snapshot.status === 'failed') {
          setStatus('error')
          setStage('FAILED')
        } else {
          // Replay starts at sequence zero after a refresh. Rebuild progress
          // from replayed source_fetched events instead of counting the
          // snapshot's already-materialized source registry twice.
          setSourceCount(0)
          setSourceTotal(null)
          connectToRun(id)
        }
      })
      .catch((restoreError: unknown) => {
        if (activeRunId.current !== id) return
        if (restoreError instanceof Error && 'status' in restoreError && restoreError.status === 404) {
          removeLastRunId()
          activeRunId.current = null
          return
        }
        setStatus('error')
        setError(restoreError instanceof Error ? restoreError.message : 'The previous run could not be restored.')
      })

    return () => {
      activeRunId.current = null
      closeStream()
    }
  }, [applySnapshot, closeStream, connectToRun])

  useEffect(() => () => closeStream(), [closeStream])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const requestedTopic = topic.trim()
    if (!requestedTopic) {
      setError('Enter a topic before starting research.')
      return
    }

    closeStream()
    activeRunId.current = null
    setStatus('running')
    setStage('PLANNING')
    setRunId(null)
    setSourceCount(0)
    setSourceTotal(null)
    setFetchedSources([])
    setEventCount(0)
    setReport('')
    setSources([])
    setError('')
    setConnectionNote('Starting a new research run…')
    hydratedReport.current = false

    try {
      const created = await createReport(requestedTopic)
      saveLastRunId(created.id)
      setRunId(created.id)
      connectToRun(created.id)
    } catch (requestError) {
      setStatus('error')
      setConnectionNote('')
      setError(requestError instanceof Error ? requestError.message : 'The research run could not be started.')
    }
  }

  const statusLabel = status === 'running' ? 'RESEARCH ACTIVE' : status === 'done' ? 'REPORT READY' : status === 'error' ? 'CHECK FAILED' : 'SYSTEM READY'

  return (
    <main className="mission-control">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true">R</div>
        <div>
          <p className="eyebrow">OMNIRUSH / RESEARCH SYSTEM</p>
          <p className="brand-name">One-Click Reports</p>
        </div>
        <div className="connection-status">
          <span className={`status-dot ${status === 'error' ? 'offline' : ''}`} />
          {statusLabel}
        </div>
      </header>

      <section className="hero-section">
        <p className="eyebrow accent">AUTONOMOUS RESEARCH, ON DEMAND</p>
        <h1>Turn a question into a report.</h1>
        <p className="hero-copy">
          Watch an AI research agent search the web, read the best sources, and assemble a
          citation-backed report you can share.
        </p>

        <TopicForm topic={topic} isRunning={status === 'running'} onTopicChange={setTopic} onSubmit={handleSubmit} />
        {error && <p className="run-error" role="alert">{error}</p>}

        {status !== 'idle' && status !== 'error' && (
           <ProgressTimeline
             stage={stage}
             sourceFetched={sourceCount}
             sourceTotal={sourceTotal}
             fetchedSources={fetchedSources}
             eventCount={eventCount}
             connectionNote={connectionNote}
          />
        )}
        {status === 'error' && runId && (
           <ProgressTimeline
             stage={stage}
             sourceFetched={sourceCount}
             sourceTotal={sourceTotal}
             fetchedSources={fetchedSources}
             eventCount={eventCount}
             connectionNote={connectionNote}
          />
        )}

        {report && (
          <>
            <ReportView report={report} sources={sources} isStreaming={status === 'running'} />
            {status === 'done' && runId && <PdfDownload runId={runId} />}
          </>
        )}
      </section>

      <section className="pipeline-preview" aria-label="Research pipeline">
        <div className="section-heading">
          <div>
            <p className="eyebrow">PIPELINE PREVIEW</p>
            <h2>From prompt to proof</h2>
          </div>
          <span className="phase-label">PHASE 06 / LIVE</span>
        </div>
        <div className="stage-grid">
          {['Plan the search', 'Read the sources', 'Write with citations'].map((pipelineStage, index) => (
            <article className="stage-card" key={pipelineStage}>
              <span className="stage-number">0{index + 1}</span>
              <h3>{pipelineStage}</h3>
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
