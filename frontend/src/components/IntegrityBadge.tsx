import type { RunIntegrity } from '../api/client'

type IntegrityBadgeProps = {
  integrity: RunIntegrity | null
}

function formatTokens(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(1)}k` : String(value)
}

/**
 * Judge-facing proof that the citation validator kept the report grounded:
 * how many inline citations were validated and how many hallucinated ones were removed.
 */
function IntegrityBadge({ integrity }: IntegrityBadgeProps) {
  if (!integrity) return null
  const clean = integrity.citationsRemoved === 0
  const callouts: string[] = []
  if (integrity.contextTokenEstimate !== undefined) {
    callouts.push(`Context \u2248 ${formatTokens(integrity.contextTokenEstimate)} tokens`)
  }
  if (integrity.outputTokenEstimate !== undefined) {
    callouts.push(`Generated \u2248 ${formatTokens(integrity.outputTokenEstimate)} tokens`)
  }
  if (integrity.searchCalls !== undefined && integrity.maxSearchCalls !== undefined) {
    callouts.push(`Search calls ${integrity.searchCalls}/${integrity.maxSearchCalls}`)
  }
  if (integrity.attemptedSources !== undefined && integrity.succeededSources !== undefined) {
    callouts.push(`Sources ${integrity.succeededSources}/${integrity.attemptedSources} extracted`)
  }
  if (integrity.budgetStatus) {
    callouts.push(`Latency budget: ${integrity.budgetStatus.replace('_', ' ')}`)
  }

  return (
    <div className="integrity-block" aria-label="Citation integrity summary">
      <div className="health-badges">
        <span className={`stat-badge ${clean ? 'good' : 'warn'}`}>
          CITATION INTEGRITY: {integrity.citationsValid} VALIDATED / {integrity.citationsRemoved} HALLUCINATED REMOVED
        </span>
        {integrity.mockMode !== undefined && (
          <span className="stat-badge good">{integrity.mockMode ? 'MOCK RUN' : 'LIVE RUN'}</span>
        )}
      </div>
      <ul className="integrity-callouts">
        {callouts.map((callout) => (
          <li key={callout}>{callout}</li>
        ))}
      </ul>
    </div>
  )
}

export default IntegrityBadge
