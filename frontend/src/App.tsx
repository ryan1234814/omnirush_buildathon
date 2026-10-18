import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  createReport,
  getHealth,
  getReport,
  type ReportEvent,
  type HealthSnapshot,
  type ReportSnapshot,
  ReportEventStream,
  type RunStage,
} from './api/client'
import PdfDownload from './components/PdfDownload'
import ProgressTimeline from './components/ProgressTimeline'
import ReportView from './components/ReportView'
import CapabilitiesPanel from './components/CapabilitiesPanel'
import EventTicker, { type ActivityItem } from './components/EventTicker'
import RecentRuns, { type HistoryEntry } from './components/RecentRuns'
import SourceIntelligence from './components/SourceIntelligence'
import SystemStats from './components/SystemStats'
import TopicForm from './components/TopicForm'
import WorkspaceHeader, { type WorkspaceView } from './components/WorkspaceHeader'
import './App.css'

type AppStatus = 'idle' | 'running' | 'done' | 'error'

const LAST_RUN_KEY = 'omnirush:last-run-id'
const HISTORY_KEY = 'omnirush:run-history'
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

function readHistory(): HistoryEntry[] {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(HISTORY_KEY) || '[]')
    if (!Array.isArray(parsed)) return []
    return parsed.filter((entry): entry is HistoryEntry => (
      typeof entry === 'object' && entry !== null &&
      typeof entry.id === 'string' && typeof entry.topic === 'string' &&
      typeof entry.status === 'string' && typeof entry.createdAt === 'string'
    )).slice(0, 10)
  } catch {
    return []
  }
}

function saveHistory(entries: HistoryEntry[]): void {
  try {
    window.localStorage.setItem(HISTORY_KEY, JSON.stringify(entries.slice(0, 10)))
  } catch {
    // History is optional; the active run still works without it.
  }
}

function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  return `${minutes}:${String(remainder).padStart(2, '0')}`
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
  const [history, setHistory] = useState<HistoryEntry[]>(readHistory)
  const [activity, setActivity] = useState<ActivityItem[]>([])
  const [health, setHealth] = useState<HealthSnapshot | null>(null)
  const [healthError, setHealthError] = useState('')
  const [startedAt, setStartedAt] = useState<number | null>(null)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [activeView, setActiveView] = useState<WorkspaceView>('control')
  const [projectorMode, setProjectorMode] = useState(false)
  const stream = useRef<ReportEventStream | null>(null)
  const activeRunId = useRef<string | null>(null)
  const hydratedReport = useRef(false)

  const updateHistory = useCallback((entry: HistoryEntry) => {
    setHistory((current) => {
      const next = [entry, ...current.filter((item) => item.id !== entry.id)]
      saveHistory(next)
      return next.slice(0, 10)
    })
  }, [])

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
    setStartedAt(Date.parse(snapshot.created_at) || null)
    hydratedReport.current = Boolean(snapshot.report_md)
    updateHistory({ id: snapshot.id, topic: snapshot.topic, status: snapshot.status, createdAt: snapshot.created_at })
  }, [updateHistory])

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
    if (incoming.type !== 'report_token') {
      const detail = payload.stage || payload.url || (payload.error ? String(payload.error) : incoming.type.replaceAll('_', ' '))
      setActivity((current) => [{ label: incoming.type.replaceAll('_', ' '), detail }, ...current].slice(0, 8))
    }

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
      updateHistory({ id, topic, status: 'failed', createdAt: new Date().toISOString() })
    }
  }, [closeStream, finishFromSnapshot, topic, updateHistory])

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
    let cancelled = false
    const refreshHealth = () => {
      void getHealth()
        .then((snapshot) => {
          if (!cancelled) {
            setHealth(snapshot)
            setHealthError('')
          }
        })
        .catch((healthRequestError: unknown) => {
          if (!cancelled) setHealthError(healthRequestError instanceof Error ? healthRequestError.message : 'Health check unavailable')
        })
    }
    refreshHealth()
    const interval = window.setInterval(refreshHealth, 30_000)
    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [])

  useEffect(() => {
    if (status !== 'running' || !startedAt) return
    const updateElapsed = () => setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)))
    updateElapsed()
    const interval = window.setInterval(updateElapsed, 1000)
    return () => window.clearInterval(interval)
  }, [startedAt, status])

  const selectRun = useCallback(async (id: string) => {
    closeStream()
    activeRunId.current = id
    setActivity([])
    setError('')
    try {
      const snapshot = await getReport(id)
      if (activeRunId.current !== id) return
      applySnapshot(snapshot)
      saveLastRunId(id)
      if (snapshot.status === 'completed') {
        setStage('DONE')
        setStatus('done')
      } else if (snapshot.status === 'failed') {
        setStage('FAILED')
        setStatus('error')
      } else {
        setSourceCount(0)
        setSourceTotal(null)
        setFetchedSources([])
        setReport('')
        hydratedReport.current = false
        connectToRun(id)
      }
    } catch (selectError: unknown) {
      if (activeRunId.current !== id) return
      if (selectError instanceof Error && 'status' in selectError && selectError.status === 404) {
        removeLastRunId()
        activeRunId.current = null
        return
      }
      setStatus('error')
      setError(selectError instanceof Error ? selectError.message : 'This run could not be opened.')
    }
  }, [applySnapshot, closeStream, connectToRun])

  useEffect(() => {
    const id = readLastRunId()
    if (!id) return
    const restoreTimer = window.setTimeout(() => void selectRun(id), 0)

    return () => {
      window.clearTimeout(restoreTimer)
      activeRunId.current = null
      closeStream()
    }
  }, [closeStream, selectRun])

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
    setActivity([{ label: 'run queued', detail: requestedTopic }])
    setStartedAt(Date.now())
    setElapsedSeconds(0)
    hydratedReport.current = false

    try {
      const created = await createReport(requestedTopic)
      saveLastRunId(created.id)
      updateHistory({ id: created.id, topic: requestedTopic, status: 'running', createdAt: new Date().toISOString() })
      setRunId(created.id)
      connectToRun(created.id)
    } catch (requestError) {
      setStatus('error')
      setConnectionNote('')
      setError(requestError instanceof Error ? requestError.message : 'The research run could not be started.')
    }
  }

  const statusLabel = status === 'running' ? 'RESEARCH ACTIVE' : status === 'done' ? 'REPORT READY' : status === 'error' ? 'CHECK FAILED' : 'SYSTEM READY'

  function navigateTo(view: WorkspaceView): void {
    setActiveView(view)
    const target = view === 'control' ? 'command-deck' : view === 'reports' ? 'report-workspace' : 'source-intelligence'
    document.getElementById(target)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <main className={`mission-control ${projectorMode ? 'projector-mode' : ''}`}>
      <WorkspaceHeader
        statusLabel={statusLabel}
        status={status}
        activeView={activeView}
        onViewChange={navigateTo}
        onProjectorToggle={() => setProjectorMode((enabled) => !enabled)}
        projectorMode={projectorMode}
      />

      <section className="command-deck" id="command-deck">
        <div className="command-copy">
          <p className="eyebrow accent">COMMAND DECK / READY FOR INPUT</p>
          <h1>Ask the system anything.</h1>
          <p>Launch a citation-backed research operation and watch every stage become observable.</p>
        </div>
        <div className="command-form-area">
          <TopicForm topic={topic} isRunning={status === 'running'} onTopicChange={setTopic} onSubmit={handleSubmit} />
          <div className="command-meta">
            <span><strong>{runId ? runId.slice(0, 10) : 'NO ACTIVE RUN'}</strong> {runId ? ' / RUN ID' : ' / START A MISSION'}</span>
            <span>{health?.mock_mode ? 'Deterministic demo data' : 'Live research providers'}</span>
            <span>{status === 'running' ? `Elapsed ${formatDuration(elapsedSeconds)}` : 'One click to begin'}</span>
          </div>
        </div>
      </section>

      {error && <p className="run-error" role="alert">{error}</p>}

      <section className="dashboard-layout" aria-label="Mission dashboard">
        <div className="dashboard-main-column">
          <section className="live-deck dashboard-panel" id="live-run" aria-labelledby="live-title">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">ACTIVE OPERATION</p>
                <h2 id="live-title">Live run deck</h2>
              </div>
              <span className="panel-index">{status === 'idle' ? 'STANDBY' : stage}</span>
            </div>
            {status === 'idle' ? (
              <div className="empty-live-state"><span className="empty-glyph">◌</span><div><strong>No operation in progress</strong><p>Use the command deck above to put the research pipeline to work.</p></div></div>
            ) : (
              <ProgressTimeline
                stage={stage}
                sourceFetched={sourceCount}
                sourceTotal={sourceTotal}
                fetchedSources={fetchedSources}
                eventCount={eventCount}
                connectionNote={connectionNote}
              />
            )}
          </section>

          <EventTicker items={activity} />

          <section className="report-workspace" id="report-workspace" aria-labelledby="report-workspace-title">
            <div className="workspace-heading">
              <div><p className="eyebrow">OUTPUT WORKSPACE</p><h2 id="report-workspace-title">Report workspace</h2></div>
              <span className="panel-index">{report ? `${sources.length} SOURCES` : 'WAITING'}</span>
            </div>
            {report ? (
              <>
                <ReportView report={report} sources={sources} isStreaming={status === 'running'} />
                {status === 'done' && runId && <PdfDownload runId={runId} />}
              </>
            ) : (
              <div className="workspace-empty"><span className="workspace-empty-number">02</span><div><strong>Your report will appear here</strong><p>Live Markdown, inline citations, source cards, and PDF export are all connected to the same run.</p></div></div>
            )}
          </section>
        </div>

        <aside className="dashboard-side-column">
          <SystemStats
            health={health}
            healthError={healthError}
            status={status}
            stage={stage}
            sourceFetched={sourceCount}
            sourceRetained={sources.length}
            eventCount={eventCount}
            elapsed={formatDuration(elapsedSeconds)}
            reportLength={report.length}
          />
          <RecentRuns entries={history} activeId={runId} onSelect={(id) => void selectRun(id)} onClear={() => { setHistory([]); saveHistory([]) }} />
          <CapabilitiesPanel onUseExample={(example) => { setTopic(example); navigateTo('control') }} />
        </aside>
      </section>

      <SourceIntelligence sources={sources} fetchedSources={fetchedSources} onOpenReport={() => navigateTo('reports')} />

      <footer className="platform-footer">
        <span>OMNIRUSH RESEARCH PLATFORM</span>
        <span>Replayable runs · citation-safe output · local browser archive</span>
      </footer>
    </main>
  )
}

export default App
