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
import ProgressTimeline, { type FetchedSource } from './components/ProgressTimeline'
import ReportView from './components/ReportView'
import CapabilitiesPanel from './components/CapabilitiesPanel'
import CitationHeatmap from './components/CitationHeatmap'
import CommandPalette, { type CommandItem } from './components/CommandPalette'
import EventTicker, { type ActivityItem } from './components/EventTicker'
import RecentRuns, { type HistoryEntry } from './components/RecentRuns'
import ReportTools from './components/ReportTools'
import { LatencyBudgetPanel, RunFailureNotice, type RunFailureDetails, ZeroResultsNotice } from './components/RunStateNotices'
import PipelineFlow from './components/PipelineFlow'
import SourceIntelligence from './components/SourceIntelligence'
import SystemStats from './components/SystemStats'
import TopicForm from './components/TopicForm'
import WorkspaceHeader, { type WorkspaceView } from './components/WorkspaceHeader'
import { useSoundCues } from './hooks/useSoundCues'
import './App.css'

type AppStatus = 'idle' | 'running' | 'done' | 'error'

const LAST_RUN_KEY = 'omnirush:last-run-id'
const HISTORY_KEY = 'omnirush:run-history'
const INITIAL_TOPIC = 'Quantum computing 2026'
const COMMAND_EXAMPLES = [
  'Quantum computing 2026',
  'AI agent reliability',
  'Future of remote work',
  'Climate tech in 2026',
]

function readViewFromHash(): WorkspaceView {
  const raw = window.location.hash.replace(/^#\/?/, '')
  if (raw === 'reports' || raw === 'sources') return raw
  return 'control'
}

type LatencyBudget = {
  latencyMs: number
  budgetMs: number
}

function recordValue(record: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    if (key in record) return record[key]
  }
  return undefined
}

function numberValue(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value)
  return null
}

function stringValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function booleanValue(value: unknown): boolean | null {
  if (typeof value === 'boolean') return value
  if (value === 'true') return true
  if (value === 'false') return false
  return null
}

function eventUrl(payload: ReportEvent['payload']): string | null {
  return stringValue(recordValue(payload, ['url', 'source_url']))
}

function eventReason(payload: ReportEvent['payload']): string | undefined {
  return stringValue(recordValue(payload, ['reason', 'skip_reason', 'dead_reason', 'error', 'message', 'detail'])) || undefined
}

function payloadCount(payload: ReportEvent['payload'], keys: string[]): number | null {
  return numberValue(recordValue(payload, keys))
}

function readLatencyBudget(source: Record<string, unknown>): LatencyBudget | null {
  const nested = source.metrics && typeof source.metrics === 'object' && source.metrics !== null
    ? source.metrics as Record<string, unknown>
    : {}
  const read = (keys: string[]) => numberValue(recordValue(source, keys)) ?? numberValue(recordValue(nested, keys))
  const latencyMs = read(['latency_ms', 'latency', 'elapsed_ms', 'duration_ms'])
  const budgetSeconds = read(['budget_seconds']) ?? numberValue(recordValue(nested, ['budget_seconds']))
  const budgetMs = read(['latency_budget_ms', 'budget_ms', 'budget', 'latency_budget'])
    ?? (budgetSeconds === null ? null : budgetSeconds * 1000)
  if (latencyMs === null || budgetMs === null) return null
  return { latencyMs, budgetMs }
}

function hasLatencyWarning(source: Record<string, unknown>): boolean {
  const nested = source.metrics && typeof source.metrics === 'object' && source.metrics !== null
    ? source.metrics as Record<string, unknown>
    : {}
  const warning = booleanValue(recordValue(source, ['budget_exceeded', 'budget_warning', 'latency_budget_exceeded', 'latency_warning']))
    ?? booleanValue(recordValue(nested, ['budget_exceeded', 'budget_warning', 'latency_budget_exceeded', 'latency_warning']))
  const withinBudget = booleanValue(recordValue(source, ['within_budget']))
    ?? booleanValue(recordValue(nested, ['within_budget']))
  const budget = readLatencyBudget(source)
  return warning === true || withinBudget === false || recordValue(source, ['budget_status']) === 'exceeded' || (budget !== null && budget.latencyMs > budget.budgetMs)
}

function failureDetails(message: string, payload: ReportEvent['payload'] = {}, eventType = ''): RunFailureDetails {
  const combined = `${eventType} ${message} ${String(recordValue(payload, ['code', 'error_code', 'provider']) || '')}`.toLowerCase()
  const quotaFailure = booleanValue(payload.quota_exceeded) === true || /quota|rate limit|429|throttl/.test(combined)
  const searchFailure = /search/.test(combined)
  return {
    message,
    guidance: quotaFailure
      ? 'The provider may have reached a quota or rate limit. Wait for the limit to reset, then retry, or edit the topic to use a narrower request.'
      : searchFailure
        ? 'The search provider could not return evidence. Check provider configuration or retry with a different topic.'
        : 'A research provider did not complete this run. Retry the run or edit the topic and try again.',
    retryable: booleanValue(payload.retryable) !== false,
  }
}

function upsertFetchedSource(current: FetchedSource[], nextSource: FetchedSource): FetchedSource[] {
  const index = current.findIndex((source) => source.url === nextSource.url)
  if (index < 0) return [...current, nextSource]
  const next = [...current]
  next[index] = {
    ...next[index],
    ...nextSource,
    status: nextSource.status === 'dead' && next[index].status === 'skipped' ? 'skipped' : nextSource.status,
    reason: nextSource.reason ?? next[index].reason,
  }
  return next
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
  const [sourceSucceeded, setSourceSucceeded] = useState(0)
  const [sourceTotal, setSourceTotal] = useState<number | null>(null)
  const [fetchedSources, setFetchedSources] = useState<FetchedSource[]>([])
  const [eventCount, setEventCount] = useState(0)
  const [report, setReport] = useState('')
  const [sources, setSources] = useState<ReportSnapshot['sources']>([])
  const [noResults, setNoResults] = useState(false)
  const [partialReport, setPartialReport] = useState(false)
  const [partialReason, setPartialReason] = useState('')
  const [error, setError] = useState('')
  const [failure, setFailure] = useState<RunFailureDetails | null>(null)
  const [latencyBudget, setLatencyBudget] = useState<LatencyBudget | null>(null)
  const [latencyWarning, setLatencyWarning] = useState(false)
  const [connectionNote, setConnectionNote] = useState('')
  const [history, setHistory] = useState<HistoryEntry[]>(readHistory)
  const [activity, setActivity] = useState<ActivityItem[]>([])
  const [health, setHealth] = useState<HealthSnapshot | null>(null)
  const [healthError, setHealthError] = useState('')
  const [startedAt, setStartedAt] = useState<number | null>(null)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [activeView, setActiveView] = useState<WorkspaceView>(readViewFromHash)
  const [projectorMode, setProjectorMode] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const sound = useSoundCues()
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
    const snapshotMetrics = snapshot.metrics ?? {}
    const attempted = snapshot.attempted_sources
      ?? snapshot.sources_attempted
      ?? snapshot.attempted
      ?? numberValue(snapshotMetrics.attempted_sources)
      ?? numberValue(snapshotMetrics.sources_attempted)
    const succeeded = snapshot.succeeded_sources
      ?? snapshot.sources_succeeded
      ?? snapshot.succeeded
      ?? numberValue(snapshotMetrics.succeeded_sources)
      ?? numberValue(snapshotMetrics.sources_succeeded)
    if (attempted !== null && attempted !== undefined) {
      setSourceCount(attempted)
      setSourceTotal(attempted || null)
    } else {
      setSourceCount((count) => count || snapshot.sources.length)
      setSourceTotal((total) => total || snapshot.sources.length || null)
    }
    if (succeeded !== null && succeeded !== undefined) {
      setSourceSucceeded(succeeded)
    } else {
      setSourceSucceeded((count) => count || snapshot.sources.length)
    }
    setFetchedSources((current) => current.length > 0 ? current : snapshot.sources.map((source) => ({ url: source.url, ok: true, bytes: 0, status: 'succeeded' })))
    if ('no_results' in snapshot || 'results' in snapshot || snapshot.outcome) {
      setNoResults(snapshot.no_results === true || snapshot.results === 0 || snapshot.outcome === 'no_results' || snapshot.outcome === 'no_sources')
    }
    const hasPartialField = 'partial' in snapshot || 'synthesis_partial' in snapshot || 'incomplete' in snapshot || snapshot.outcome === 'partial'
    if (hasPartialField) {
      const isPartial = snapshot.partial === true || snapshot.synthesis_partial === true || snapshot.incomplete === true
      setPartialReport(isPartial)
      setPartialReason(snapshot.incomplete_reason ?? snapshot.message ?? '')
    }
    setError(snapshot.error ?? '')
    setFailure(snapshot.status === 'failed' && snapshot.error ? failureDetails(snapshot.error) : null)
    const snapshotRecord = snapshot as unknown as Record<string, unknown>
    const hasTelemetryFields = 'latency_ms' in snapshot || 'latency_budget_ms' in snapshot || 'budget_exceeded' in snapshot || 'metrics' in snapshot
    if (hasTelemetryFields) {
      setLatencyBudget(readLatencyBudget(snapshotRecord))
      setLatencyWarning(hasLatencyWarning(snapshotRecord))
    }
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
      const detail = payload.stage || eventUrl(payload) || (payload.error ? String(payload.error) : eventReason(payload) || incoming.type.replaceAll('_', ' '))
      setActivity((current) => [{ label: incoming.type.replaceAll('_', ' '), detail }, ...current].slice(0, 8))
    }

    if (incoming.type === 'source_fetched') {
      const sourceUrl = eventUrl(payload)
      if (sourceUrl) {
        const nextSource: FetchedSource = {
          url: sourceUrl,
          ok: payload.ok !== false,
          bytes: numberValue(payload.bytes) ?? 0,
          status: payload.ok === false ? 'dead' : 'succeeded',
          reason: eventReason(payload),
        }
        setFetchedSources((current) => {
          const next = upsertFetchedSource(current, nextSource)
          setSourceCount((count) => Math.max(count, payloadCount(payload, ['attempted_sources', 'attempted', 'total']) ?? next.length))
          setSourceSucceeded(payloadCount(payload, ['succeeded_sources', 'succeeded']) ?? next.filter((source) => source.status === 'succeeded').length)
          return next
        })
      } else {
        setSourceCount((count) => Math.max(count, payloadCount(payload, ['attempted_sources', 'attempted', 'total']) ?? count + 1))
      }
    }
    if (incoming.type === 'source_skipped' || incoming.type === 'source_dead') {
      const sourceUrl = eventUrl(payload) || `source-${incoming.seq}`
      const sourceStatus = incoming.type === 'source_skipped' ? 'skipped' : 'dead'
      const nextSource: FetchedSource = {
        url: sourceUrl,
        ok: false,
        bytes: 0,
        status: sourceStatus,
        reason: eventReason(payload) || (sourceStatus === 'skipped' ? 'Skipped by the pipeline' : 'Source could not be reached'),
      }
      setFetchedSources((current) => {
        const next = upsertFetchedSource(current, nextSource)
        setSourceCount((count) => Math.max(count, payloadCount(payload, ['attempted_sources', 'attempted', 'total']) ?? next.length))
        setSourceSucceeded(payloadCount(payload, ['succeeded_sources', 'succeeded']) ?? next.filter((source) => source.status === 'succeeded').length)
        return next
      })
    }
    if (incoming.type === 'stage_completed' && payload.stage === 'EXTRACTING') {
      const attemptedSources = payloadCount(payload, ['attempted_sources', 'attempted', 'total'])
      const succeededSources = payloadCount(payload, ['succeeded_sources', 'succeeded'])
      if (attemptedSources !== null) {
        setSourceCount(attemptedSources)
        setSourceTotal(attemptedSources)
      }
      if (succeededSources !== null) setSourceSucceeded(succeededSources)
    }
    if (incoming.type === 'no_results' || payload.no_results === true || payloadCount(payload, ['results', 'result_count']) === 0) {
      setNoResults(true)
    }
    if (incoming.type === 'synthesis_partial' || payload.partial === true || payload.incomplete === true) {
      setPartialReport(true)
      setPartialReason(eventReason(payload) || 'Synthesis stopped before all planned evidence could be incorporated.')
      if (typeof payload.report_md === 'string' && payload.report_md) {
        setReport(payload.report_md)
        hydratedReport.current = true
      }
    }
    if (incoming.type === 'stage_failed' || incoming.type === 'quota_error' || incoming.type === 'quota_exceeded' || incoming.type === 'provider_quota_error' || incoming.type === 'provider_error' || incoming.type === 'provider_failed' || incoming.type === 'search_error' || incoming.type === 'search_failed' || incoming.type === 'synthesis_failed') {
      const failureMessage = eventReason(payload) || 'The research provider could not complete this stage.'
      setError(failureMessage)
      setFailure(failureDetails(failureMessage, payload, incoming.type))
    }
    const eventRecord = payload as Record<string, unknown>
    const nextLatencyBudget = readLatencyBudget(eventRecord)
    if (nextLatencyBudget) setLatencyBudget(nextLatencyBudget)
    if (hasLatencyWarning(eventRecord) || incoming.type === 'latency_warning' || incoming.type === 'budget_warning' || incoming.type === 'latency_budget_warning' || incoming.type === 'latency_budget_exceeded') {
      setLatencyWarning(true)
    }
    if (incoming.type === 'report_token' && !hydratedReport.current && payload.token) {
      setReport((current) => current + payload.token)
    }
    if (incoming.type === 'run_completed') {
      closeStream()
      sound.play('complete')
      void finishFromSnapshot(id).catch((terminalError: unknown) => {
        if (activeRunId.current !== id) return
        setStatus('error')
        const terminalMessage = terminalError instanceof Error ? terminalError.message : 'The finished report could not be loaded.'
        setError(terminalMessage)
        setFailure(failureDetails(terminalMessage))
        setConnectionNote('')
      })
    }
    if (incoming.type === 'run_failed') {
      closeStream()
      setStage('FAILED')
      setStatus('error')
      setError(payload.error || 'The research run failed.')
      setFailure(failureDetails(payload.error || 'The research run failed.', payload, incoming.type))
      if (payload.partial === true) setPartialReport(true)
      setConnectionNote('')
      updateHistory({ id, topic, status: 'failed', createdAt: new Date().toISOString() })
      sound.play('error')
    }
  }, [closeStream, finishFromSnapshot, topic, updateHistory, sound])

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
        setFailure(failureDetails(streamError.message))
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
    setFailure(null)
    setNoResults(false)
    setPartialReport(false)
    setPartialReason('')
    setLatencyBudget(null)
    setLatencyWarning(false)
    setSourceCount(0)
    setSourceSucceeded(0)
    setSourceTotal(null)
    setFetchedSources([])
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
        setSourceSucceeded(0)
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
      const selectMessage = selectError instanceof Error ? selectError.message : 'This run could not be opened.'
      setError(selectMessage)
      setFailure(failureDetails(selectMessage))
    }
  }, [applySnapshot, closeStream, connectToRun])

  const selectRunRef = useRef(selectRun)
  selectRunRef.current = selectRun

  useEffect(() => {
    const id = readLastRunId()
    if (!id) return
    const restoreTimer = window.setTimeout(() => void selectRunRef.current(id), 0)

    return () => {
      window.clearTimeout(restoreTimer)
      activeRunId.current = null
      closeStream()
    }
  }, [closeStream])

  useEffect(() => () => closeStream(), [closeStream])

  // Keep the browser URL in sync with the active page so refreshes restore
  // the tab the operator was on (Mission control / Reports / Sources).
  useEffect(() => {
    const onHashChange = () => setActiveView(readViewFromHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  // Signal chime whenever the pipeline advances to a new stage.
  const previousStage = useRef<RunStage | null>(null)
  useEffect(() => {
    if (previousStage.current && previousStage.current !== stage && status === 'running') {
      sound.play('stage')
    }
    previousStage.current = stage
  }, [stage, status, sound])

  // Cursor-following glow inside cards: writes --mx/--my for the CSS gradient.
  useEffect(() => {
    const handler = (event: MouseEvent) => {
      const target = (event.target as HTMLElement | null)?.closest(
        '.dashboard-panel, .report-workspace, .source-intelligence-panel, .citation-heatmap',
      ) as HTMLElement | null
      if (!target) return
      const rect = target.getBoundingClientRect()
      target.style.setProperty('--mx', `${event.clientX - rect.left}px`)
      target.style.setProperty('--my', `${event.clientY - rect.top}px`)
    }
    document.addEventListener('mousemove', handler)
    return () => document.removeEventListener('mousemove', handler)
  }, [])

  // Global keyboard shortcuts: ⌘K palette, / focus topic, 1/2/3 pages, p PDF.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      const typingInField =
        target &&
        (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setPaletteOpen((open) => !open)
        return
      }
      if (typingInField) return
      if (event.key === '/') {
        event.preventDefault()
        document.getElementById('topic')?.focus()
        return
      }
      if (event.key === '1') { event.preventDefault(); navigateTo('control'); return }
      if (event.key === '2') { event.preventDefault(); navigateTo('reports'); return }
      if (event.key === '3') { event.preventDefault(); navigateTo('sources'); return }
      if (event.key.toLowerCase() === 'p' && status === 'done' && runId) {
        event.preventDefault()
        window.open(`/api/reports/${encodeURIComponent(runId)}/report.pdf`, '_blank', 'noopener')
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [status, runId])

  async function startResearch(requestedTopic: string) {
    const normalizedTopic = requestedTopic.trim()
    if (!normalizedTopic) {
      setError('Enter a topic before starting research.')
      return
    }

    closeStream()
    activeRunId.current = null
    setStatus('running')
    setStage('PLANNING')
    setRunId(null)
    setSourceCount(0)
    setSourceSucceeded(0)
    setSourceTotal(null)
    setFetchedSources([])
    setEventCount(0)
    setReport('')
    setSources([])
    setNoResults(false)
    setPartialReport(false)
    setPartialReason('')
    setError('')
    setFailure(null)
    setLatencyBudget(null)
    setLatencyWarning(false)
    setConnectionNote('Starting a new research run…')
    setActivity([{ label: 'run queued', detail: normalizedTopic }])
    setStartedAt(Date.now())
    setElapsedSeconds(0)
    hydratedReport.current = false
    sound.play('start')

    try {
      const created = await createReport(normalizedTopic)
      saveLastRunId(created.id)
      updateHistory({ id: created.id, topic: normalizedTopic, status: 'running', createdAt: new Date().toISOString() })
      setRunId(created.id)
      connectToRun(created.id)
    } catch (requestError) {
      setStatus('error')
      setConnectionNote('')
      const requestMessage = requestError instanceof Error ? requestError.message : 'The research run could not be started.'
      setError(requestMessage)
      setFailure(failureDetails(requestMessage))
      sound.play('error')
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void startResearch(topic)
  }

  function editTopic(): void {
    navigateTo('control')
    window.setTimeout(() => document.getElementById('topic')?.focus(), 0)
  }

  function tryDifferentTopic(): void {
    const resetToComposer = () => {
      closeStream()
      activeRunId.current = null
      setStatus('idle')
      setRunId(null)
      setTopic('')
      setError('')
      setFailure(null)
      setNoResults(false)
      setPartialReport(false)
      setPartialReason('')
      setReport('')
      setSources([])
    }
    resetToComposer()
    window.setTimeout(resetToComposer, 0)
    editTopic()
  }

  const statusLabel = status === 'running' ? 'RESEARCH ACTIVE' : status === 'done' ? 'REPORT READY' : status === 'error' ? 'CHECK FAILED' : 'SYSTEM READY'

  const commandItems: CommandItem[] = (() => {
    const items: CommandItem[] = [
      { id: 'go-control', label: 'Go to Mission control', hint: '1', section: 'Navigate', keywords: 'home deck topic start', run: () => navigateTo('control') },
      { id: 'go-reports', label: 'Go to Report workspace', hint: '2', section: 'Navigate', keywords: 'markdown pdf output', run: () => navigateTo('reports') },
      { id: 'go-sources', label: 'Go to Source intelligence', hint: '3', section: 'Navigate', keywords: 'evidence citations heatmap', run: () => navigateTo('sources') },
      { id: 'focus-topic', label: 'Focus topic input', hint: '/', section: 'Actions', keywords: 'search type write', run: () => { navigateTo('control'); window.setTimeout(() => document.getElementById('topic')?.focus(), 0) } },
      { id: 'toggle-projector', label: projectorMode ? 'Exit projector mode' : 'Enter projector mode', section: 'Actions', keywords: 'demo stage zoom', run: () => setProjectorMode((v) => !v) },
      { id: 'toggle-sound', label: sound.enabled ? 'Mute sound cues' : 'Enable sound cues', section: 'Actions', keywords: 'audio chime beep', run: sound.toggle },
    ]
    if (status === 'done' && runId) {
      items.push({ id: 'download-pdf', label: 'Download report PDF', hint: 'p', section: 'Actions', keywords: 'export save', run: () => window.open(`/api/reports/${encodeURIComponent(runId)}/report.pdf`, '_blank', 'noopener') })
    }
    if (status === 'error' || status === 'done') {
      items.push({ id: 'retry-run', label: 'Retry the last research run', section: 'Actions', keywords: 'again rerun start', run: () => void startResearch(topic) })
    }
    for (const example of COMMAND_EXAMPLES) {
      items.push({ id: `example-${example}`, label: `Research: ${example}`, section: 'Examples', keywords: example, run: () => { setTopic(example); navigateTo('control') } })
    }
    for (const entry of history.slice(0, 5)) {
      items.push({ id: `history-${entry.id}`, label: entry.topic, hint: entry.status, section: 'Recent runs', keywords: entry.id, run: () => void selectRun(entry.id) })
    }
    return items
  })()

  function navigateTo(view: WorkspaceView): void {
    setActiveView(view)
    const target = `#/${view}`
    if (window.location.hash !== target) {
      window.location.hash = target
    }
    window.scrollTo({ top: 0, behavior: 'smooth' })
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
        soundEnabled={sound.enabled}
        onSoundToggle={sound.toggle}
        onOpenPalette={() => setPaletteOpen(true)}
      />

      {error && <p className="run-error" role="alert">{error}</p>}
      {failure && <RunFailureNotice failure={failure} onRetry={() => void startResearch(topic)} onEdit={editTopic} />}
      {latencyWarning && <LatencyBudgetPanel latencyMs={latencyBudget?.latencyMs ?? null} budgetMs={latencyBudget?.budgetMs ?? null} />}

      {activeView === 'control' && (
        <>
          <section className="command-deck" id="command-deck">
            <div className="command-copy">
              <p className="eyebrow accent">COMMAND DECK / READY FOR INPUT</p>
              <h1>
                {['Ask', 'the', 'system', 'anything.'].map((word, i) => (
                  <span className="ink-word" key={`${word}-${i}`}>{word} </span>
                ))}
              </h1>
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
                <PipelineFlow stage={stage} />
                {status === 'idle' ? (
                  <div className="empty-live-state"><span className="empty-glyph">◌</span><div><strong>No operation in progress</strong><p>Use the command deck above to put the research pipeline to work.</p></div></div>
                ) : (
                  <ProgressTimeline
                    stage={stage}
                    sourceFetched={sourceCount}
                    sourceSucceeded={sourceSucceeded}
                    sourceTotal={sourceTotal}
                    fetchedSources={fetchedSources}
                    eventCount={eventCount}
                    connectionNote={connectionNote}
                  />
                )}
              </section>

              <EventTicker items={activity} />
            </div>

            <aside className="dashboard-side-column">
              <SystemStats
                health={health}
                healthError={healthError}
                status={status}
                stage={stage}
                sourceFetched={sourceCount}
                sourceSucceeded={sourceSucceeded}
                sourceRetained={sources.length}
                eventCount={eventCount}
                elapsed={formatDuration(elapsedSeconds)}
                reportLength={report.length}
              />
              <RecentRuns entries={history} activeId={runId} onSelect={(id) => void selectRun(id)} onClear={() => { setHistory([]); saveHistory([]) }} />
              <CapabilitiesPanel onUseExample={(example) => { setTopic(example); navigateTo('control') }} />
            </aside>
          </section>
        </>
      )}

      {activeView === 'reports' && (
        <div className="workspace-page">
          <section className="report-workspace" id="report-workspace" aria-labelledby="report-workspace-title">
            <div className="workspace-heading">
              <div><p className="eyebrow">OUTPUT WORKSPACE</p><h2 id="report-workspace-title">Report workspace</h2></div>
              <span className="panel-index">{report ? `${sources.length} SOURCES` : noResults ? 'NO RESULTS' : partialReport ? 'INCOMPLETE' : 'WAITING'}</span>
            </div>
            {noResults && !report ? (
              <ZeroResultsNotice topic={topic} onTryDifferentTopic={tryDifferentTopic} />
            ) : report || partialReport ? (
              <>
                <ReportView report={report} sources={sources} isStreaming={status === 'running'} isPartial={partialReport} partialReason={partialReason} />
                {runId && <ReportTools key={runId} runId={runId} topic={topic} history={history} />}
                {status === 'done' && runId && !partialReport && <PdfDownload runId={runId} />}
                {partialReport && <p className="pdf-unavailable" role="status">PDF export is unavailable until the report is complete. You can review the partial Markdown and citations above.</p>}
                <div className="page-cross-links">
                  <button type="button" className="text-button" onClick={() => navigateTo('sources')}>Inspect the evidence registry →</button>
                  <button type="button" className="text-button" onClick={() => navigateTo('control')}>← Return to Mission control</button>
                </div>
              </>
            ) : (
              <div className="workspace-empty">
                <span className="workspace-empty-number">02</span>
                <div>
                  <strong>Your report will appear here</strong>
                  <p>Live Markdown, inline citations, source cards, and PDF export land on this page as the pipeline streams. Nothing is running yet.</p>
                  <button type="button" className="text-button" onClick={() => navigateTo('control')}>Open Mission control →</button>
                </div>
              </div>
            )}
          </section>
        </div>
      )}

      {activeView === 'sources' && (
        <div className="workspace-page">
          <SourceIntelligence
            sources={sources}
            fetchedSources={fetchedSources}
            attemptedSources={sourceCount}
            succeededSources={sourceSucceeded}
            onOpenReport={() => navigateTo('reports')}
          />
          <CitationHeatmap report={report} sources={sources} />
          <div className="page-cross-links">
            <button type="button" className="text-button" onClick={() => navigateTo('reports')}>← Back to the report</button>
            <button type="button" className="text-button" onClick={() => navigateTo('control')}>Open Mission control →</button>
          </div>
        </div>
      )}

      <CommandPalette key={paletteOpen ? 'open' : 'closed'} open={paletteOpen} items={commandItems} onClose={() => setPaletteOpen(false)} />

      <footer className="platform-footer">
        <span>OMNIRUSH RESEARCH PLATFORM</span>
        <span>Replayable runs · citation-safe output · local browser archive</span>
      </footer>
    </main>
  )
}

export default App
