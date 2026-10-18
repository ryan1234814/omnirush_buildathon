const API_ROOT = '/api'
const MAX_RECONNECT_ATTEMPTS = 3

export type RunStatus = 'queued' | 'running' | 'completed' | 'failed'
export type RunStage =
  | 'PLANNING'
  | 'SEARCHING'
  | 'EXTRACTING'
  | 'RANKING'
  | 'SYNTHESIZING'
  | 'RENDERING'
  | 'DONE'
  | 'FAILED'

export type SourceEntry = {
  id: number
  url: string
  title: string
  excerpt: string
}

export type ReportSnapshot = {
  id: string
  topic: string
  status: RunStatus
  stage: RunStage
  sources: SourceEntry[]
  report_md: string | null
  created_at: string
  error: string | null
  outcome?: string
  message?: string | null
  no_results?: boolean
  partial?: boolean
  synthesis_partial?: boolean
  incomplete?: boolean
  incomplete_reason?: string | null
  results?: number
  attempted_sources?: number
  succeeded_sources?: number
  sources_attempted?: number
  sources_succeeded?: number
  attempted?: number
  succeeded?: number
  search_calls?: number
  max_search_calls?: number
  latency_ms?: number
  latency_budget_ms?: number
  budget_exceeded?: boolean
  metrics?: RunTelemetry
}

export type RunTelemetry = {
  latency_ms?: number
  elapsed_ms?: number
  latency_budget_ms?: number
  budget_ms?: number
  budget_exceeded?: boolean
  budget_warning?: boolean
  [key: string]: unknown
}

export type ReportEventType =
  | 'stage_started'
  | 'stage_completed'
  | 'source_fetched'
  | 'report_token'
  | 'citations_removed'
  | 'stage_failed'
  | 'run_completed'
  | 'run_failed'
  | 'no_results'
  | 'source_skipped'
  | 'source_dead'
  | 'synthesis_partial'
  | 'quota_error'
  | 'quota_exceeded'
  | 'provider_quota_error'
  | 'provider_error'
  | 'provider_failed'
  | 'search_error'
  | 'search_failed'
  | 'synthesis_failed'
  | 'latency_warning'
  | 'budget_warning'
  | 'latency_budget_warning'
  | 'latency_budget_exceeded'

export type ReportEventPayload = {
  stage?: RunStage
  token?: string
  error?: string
  url?: string
  ok?: boolean
  bytes?: number
  sources?: number
  results?: number
  result_count?: number
  attempted?: number
  succeeded?: number
  attempted_sources?: number
  succeeded_sources?: number
  total?: number
  source_url?: string
  reason?: string
  skip_reason?: string
  dead_reason?: string
  message?: string
  code?: string
  error_code?: string
  provider?: string
  retryable?: boolean
  quota_exceeded?: boolean
  partial?: boolean
  incomplete?: boolean
  incomplete_reason?: string
  report_md?: string
  latency_ms?: number
  latency?: number
  elapsed_ms?: number
  duration_ms?: number
  latency_budget_ms?: number
  budget_ms?: number
  budget?: number
  budget_seconds?: number
  within_budget?: boolean
  budget_status?: string
  latency_warning?: boolean
  budget_exceeded?: boolean
  budget_warning?: boolean
  metrics?: RunTelemetry
  sub_queries?: string[]
  ids?: number[]
  removed_citations?: number
  [key: string]: unknown
}

export type ReportEvent = {
  seq: number
  type: ReportEventType | string
  payload: ReportEventPayload
  created_at: string
}

export type HealthSnapshot = {
  status: string
  search_provider: string
  search_configured: boolean
  llm_configured: boolean
  mock_mode: boolean
}

export type ReportEventStreamOptions = {
  onEvent: (event: ReportEvent) => void
  onOpen?: () => void
  onRetry?: (attempt: number) => void
  onError?: (error: Error) => void
}

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function requestJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init)
  const payload: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const detail =
      typeof payload === 'object' && payload !== null && 'detail' in payload
        ? String(payload.detail)
        : `Request failed with status ${response.status}.`
    throw new ApiError(detail, response.status)
  }
  return payload as T
}

export async function createReport(topic: string): Promise<{ id: string }> {
  return requestJson<{ id: string }>(`${API_ROOT}/reports`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ topic }),
  })
}

export async function getReport(runId: string): Promise<ReportSnapshot> {
  return requestJson<ReportSnapshot>(`${API_ROOT}/reports/${encodeURIComponent(runId)}`)
}

export async function getReportMarkdown(runId: string): Promise<string> {
  const response = await fetch(`${API_ROOT}/reports/${encodeURIComponent(runId)}/report.md`)
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null)
    const detail =
      typeof payload === 'object' && payload !== null && 'detail' in payload
        ? String(payload.detail)
        : 'The finished report could not be loaded.'
    throw new ApiError(detail, response.status)
  }
  return response.text()
}

export async function getHealth(): Promise<HealthSnapshot> {
  return requestJson<HealthSnapshot>(`${API_ROOT}/health`)
}

const REPORT_EVENT_TYPES: ReportEventType[] = [
  'stage_started',
  'stage_completed',
  'source_fetched',
  'report_token',
  'citations_removed',
  'stage_failed',
  'run_completed',
  'run_failed',
  'no_results',
  'source_skipped',
  'source_dead',
  'synthesis_partial',
  'quota_error',
  'quota_exceeded',
  'provider_quota_error',
  'provider_error',
  'provider_failed',
  'search_error',
  'search_failed',
  'synthesis_failed',
  'latency_warning',
  'budget_warning',
  'latency_budget_warning',
  'latency_budget_exceeded',
]

/**
 * Typed wrapper around native EventSource.
 *
 * This wrapper owns reconnects so it can stop after three failed attempts.
 * Each replacement EventSource receives the last sequence as a query cursor;
 * the API also accepts the native Last-Event-ID header for browser retries.
 */
export class ReportEventStream {
  private readonly runId: string
  private readonly options: ReportEventStreamOptions
  private source: EventSource | null = null
  private reconnectAttempts = 0
  private closed = false
  private _lastSeq = 0
  private retryTimer: number | null = null

  constructor(runId: string, options: ReportEventStreamOptions) {
    this.runId = runId
    this.options = options
    this.connect()
  }

  private connect(): void {
    if (this.closed) return

    const cursor = this._lastSeq > 0 ? `?last_event_id=${this._lastSeq}` : ''
    const source = new EventSource(`${API_ROOT}/reports/${encodeURIComponent(this.runId)}/events${cursor}`)
    this.source = source

    source.onopen = () => {
      this.reconnectAttempts = 0
      this.options.onOpen?.()
    }

    source.onerror = () => {
      if (this.closed) return

      source.close()
      this.reconnectAttempts += 1
      if (this.reconnectAttempts > MAX_RECONNECT_ATTEMPTS) {
        this.close()
        this.options.onError?.(new Error('The live progress connection could not be restored.'))
        return
      }
      this.options.onRetry?.(this.reconnectAttempts)
      this.retryTimer = window.setTimeout(() => this.connect(), this.reconnectAttempts * 350)
    }

    for (const eventType of REPORT_EVENT_TYPES) {
      source.addEventListener(eventType, (event) => this.handleEvent(event))
    }
  }

  get lastSeq(): number {
    return this._lastSeq
  }

  close(): void {
    this.closed = true
    if (this.retryTimer !== null) window.clearTimeout(this.retryTimer)
    this.source?.close()
    this.source = null
  }

  private handleEvent(event: Event): void {
    if (this.closed) return

    const message = event as MessageEvent<string>
    let parsed: ReportEvent
    try {
      parsed = JSON.parse(message.data) as ReportEvent
    } catch {
      this.close()
      this.options.onError?.(new Error('The server sent an invalid progress event.'))
      return
    }

    const eventSeq = Number(message.lastEventId)
    const parsedSeq = Number(parsed.seq)
    const nextSeq = Number.isFinite(parsedSeq) ? parsedSeq : eventSeq
    if (Number.isFinite(nextSeq)) this._lastSeq = Math.max(this._lastSeq, nextSeq)
    this.options.onEvent(parsed)
  }
}
