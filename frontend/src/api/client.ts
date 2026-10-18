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

export type ReportEventPayload = {
  stage?: RunStage
  token?: string
  error?: string
  url?: string
  ok?: boolean
  bytes?: number
  sources?: number
  results?: number
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
