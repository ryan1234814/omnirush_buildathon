import { useMemo, useState } from 'react'
import type { SourceEntry } from '../api/client'

type SourceIntelligenceProps = {
  sources: SourceEntry[]
  fetchedSources: Array<{ url: string; ok: boolean }>
  onOpenReport: () => void
}

function sourceDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

function SourceIntelligence({ sources, fetchedSources, onOpenReport }: SourceIntelligenceProps) {
  const [filter, setFilter] = useState('')
  const visibleSources = useMemo(() => {
    const query = filter.trim().toLowerCase()
    if (!query) return sources
    return sources.filter((source) => `${source.title} ${source.url} ${source.excerpt}`.toLowerCase().includes(query))
  }, [filter, sources])

  return (
    <section className="dashboard-panel source-intelligence-panel" id="source-intelligence" aria-labelledby="source-intelligence-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">EVIDENCE REGISTRY</p>
          <h2 id="source-intelligence-title">Source intelligence</h2>
        </div>
        <span className="panel-index">{sources.length} RETAINED</span>
      </div>
      <div className="source-intel-meta">
        <span>{fetchedSources.filter((source) => source.ok).length} fetched successfully</span>
        <button className="text-button" type="button" onClick={onOpenReport}>Open citations</button>
      </div>
      <input className="source-filter" value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Filter title, domain, or excerpt" aria-label="Filter sources" />
      {visibleSources.length === 0 ? (
        <p className="empty-state">Sources will populate after extraction and ranking.</p>
      ) : (
        <div className="intel-source-list">
          {visibleSources.map((source) => (
            <a className="intel-source-row" key={source.id} href={`#source-${source.id}`} onClick={onOpenReport}>
              <span className="intel-source-id">[{source.id}]</span>
              <span className="intel-source-copy"><strong>{source.title}</strong><small>{sourceDomain(source.url)}</small></span>
              <span className="intel-source-arrow" aria-hidden="true">↗</span>
            </a>
          ))}
        </div>
      )}
    </section>
  )
}

export default SourceIntelligence
