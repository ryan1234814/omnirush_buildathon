import type { RunStage } from '../api/client'

export type FetchedSource = {
  url: string
  ok: boolean
  bytes: number
  status: 'succeeded' | 'skipped' | 'dead'
  reason?: string
}

const STAGES: RunStage[] = ['PLANNING', 'SEARCHING', 'EXTRACTING', 'RANKING', 'SYNTHESIZING', 'RENDERING', 'DONE']

type ProgressTimelineProps = {
  stage: RunStage
  sourceFetched: number
  sourceSucceeded: number
  sourceTotal: number | null
  fetchedSources: FetchedSource[]
  eventCount: number
  connectionNote?: string
}

function ProgressTimeline({
  stage,
  sourceFetched,
  sourceSucceeded,
  sourceTotal,
  fetchedSources,
  eventCount,
  connectionNote,
}: ProgressTimelineProps) {
  const currentIndex = STAGES.indexOf(stage)

  return (
    <section className="run-panel" aria-live="polite" aria-label="Research progress">
      <div className="run-panel-heading">
        <div className="run-heading-copy">
          <span className={`status-glyph ${stage === 'DONE' ? 'success' : stage === 'FAILED' ? 'failure' : ''}`} aria-hidden="true">
            {stage === 'DONE' ? '✓' : stage === 'FAILED' ? '!' : '◌'}
          </span>
          <div>
            <p className="eyebrow">LIVE RUN</p>
            <h2>{stage === 'DONE' ? 'Report ready' : stage === 'FAILED' ? 'Run stopped' : 'Research in progress'}</h2>
          </div>
        </div>
        <span className="phase-label">{stage}</span>
      </div>

      <ol className="timeline">
        {STAGES.map((runStage, index) => {
          const isComplete = currentIndex >= 0 && index < currentIndex
          const isActive = runStage === stage
          return (
            <li className={`timeline-step${isComplete ? ' complete' : ''}${isActive ? ' active' : ''}`} key={runStage}>
              <span className="timeline-marker" aria-hidden="true">{isComplete ? '✓' : String(index + 1).padStart(2, '0')}</span>
              <span>{runStage}</span>
            </li>
          )
        })}
      </ol>

      <div className="progress-meta">
        <span>
          Sources attempted: <strong>{sourceFetched}{sourceTotal !== null ? ` / ${sourceTotal}` : ''}</strong>
        </span>
        <span>Sources succeeded: <strong>{sourceSucceeded}</strong></span>
        <span>{eventCount} live events</span>
      </div>
      {fetchedSources.length > 0 && (
        <ul className="source-fetch-list" aria-label="Fetched sources">
          {fetchedSources.map((source) => {
            let label = source.url
            try {
              label = new URL(source.url).hostname.replace(/^www\./, '')
            } catch {
              // Keep the original URL for malformed-but-visible source data.
            }
            return (
              <li className={`source-fetch ${source.status === 'succeeded' ? 'ok' : 'failed'}`} key={source.url}>
                <span className="source-fetch-glyph" aria-hidden="true">{source.status === 'succeeded' ? '✓' : source.status === 'skipped' ? '–' : '!'}</span>
                <span>{label}</span>
                <span className="source-fetch-size">{source.reason || (source.bytes > 0 ? `${source.bytes.toLocaleString()} bytes` : 'unavailable')}</span>
              </li>
            )
          })}
        </ul>
      )}
      {connectionNote && <p className="connection-note">{connectionNote}</p>}
    </section>
  )
}

export default ProgressTimeline
