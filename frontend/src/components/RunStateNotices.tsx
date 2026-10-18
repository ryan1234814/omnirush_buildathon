export type RunFailureDetails = {
  message: string
  guidance: string
  retryable: boolean
}

type ZeroResultsNoticeProps = {
  topic: string
  onTryDifferentTopic: () => void
}

export function ZeroResultsNotice({ topic, onTryDifferentTopic }: ZeroResultsNoticeProps) {
  return (
    <section className="run-notice zero-results-notice" aria-labelledby="zero-results-title">
      <span className="notice-glyph" aria-hidden="true">∅</span>
      <div>
        <p className="eyebrow">NO EVIDENCE FOUND</p>
        <h2 id="zero-results-title">No results for this topic</h2>
        <p>Search providers did not return usable sources for “{topic}”. Try a broader phrase, a named subject, or a different topic.</p>
        <button className="secondary-action" type="button" onClick={onTryDifferentTopic}>Try a different topic <span aria-hidden="true">→</span></button>
      </div>
    </section>
  )
}

type RunFailureNoticeProps = {
  failure: RunFailureDetails
  onRetry: () => void
  onEdit: () => void
}

export function RunFailureNotice({ failure, onRetry, onEdit }: RunFailureNoticeProps) {
  return (
    <section className="run-notice failure-notice" aria-labelledby="failure-title">
      <span className="notice-glyph" aria-hidden="true">!</span>
      <div>
        <p className="eyebrow">RUN NEEDS ATTENTION</p>
        <h2 id="failure-title">Research could not finish</h2>
        <p>{failure.message}</p>
        <p className="notice-guidance">{failure.guidance}</p>
        <div className="notice-actions">
          <button className="secondary-action" type="button" onClick={onRetry}>Retry run <span aria-hidden="true">↻</span></button>
          <button className="text-button" type="button" onClick={onEdit}>Edit topic</button>
        </div>
      </div>
    </section>
  )
}

type LatencyBudgetPanelProps = {
  latencyMs: number | null
  budgetMs: number | null
}

export function LatencyBudgetPanel({ latencyMs, budgetMs }: LatencyBudgetPanelProps) {
  const overBy = latencyMs !== null && budgetMs !== null ? Math.max(0, latencyMs - budgetMs) : 0
  return (
    <section className="latency-budget-panel" aria-label="Latency budget warning">
      <div className="latency-budget-icon" aria-hidden="true">◷</div>
      <div>
        <p className="eyebrow">LATENCY BUDGET</p>
        <strong>Run is taking longer than planned</strong>
        <p>{latencyMs !== null && budgetMs !== null ? `${latencyMs.toLocaleString()} ms elapsed against a ${budgetMs.toLocaleString()} ms budget${overBy > 0 ? ` · ${overBy.toLocaleString()} ms over` : ''}.` : 'The server reported that this run is outside its latency budget.'} The run can still complete; keep this tab open for live updates.</p>
      </div>
    </section>
  )
}
