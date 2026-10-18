import type { HealthSnapshot } from '../api/client'

type SystemStatsProps = {
  health: HealthSnapshot | null
  healthError: string
  status: string
  stage: string
  sourceFetched: number
  sourceSucceeded: number
  sourceRetained: number
  eventCount: number
  elapsed: string
  reportLength: number
}

function Badge({ ok, children }: { ok: boolean; children: string }) {
  return <span className={`stat-badge ${ok ? 'good' : 'muted'}`}>{children}</span>
}

function SystemStats({
  health,
  healthError,
  status,
  stage,
  sourceFetched,
  sourceSucceeded,
  sourceRetained,
  eventCount,
  elapsed,
  reportLength,
}: SystemStatsProps) {
  return (
    <section className="dashboard-panel system-panel" aria-labelledby="system-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">SYSTEM TELEMETRY</p>
          <h2 id="system-title">Control room</h2>
        </div>
        <span className="panel-index">LIVE</span>
      </div>
      <div className="health-badges">
        <Badge ok={!healthError}>{healthError ? 'API OFFLINE' : 'API ONLINE'}</Badge>
        {health && <Badge ok={health.mock_mode}>{health.mock_mode ? 'MOCK MODE' : 'LIVE PROVIDERS'}</Badge>}
      </div>
      <div className="stats-grid">
        <div className="stat-cell"><span>Run state</span><strong>{status.toUpperCase()}</strong></div>
        <div className="stat-cell"><span>Current stage</span><strong>{stage}</strong></div>
        <div className="stat-cell"><span>Attempted</span><strong>{sourceFetched}</strong></div>
        <div className="stat-cell"><span>Succeeded</span><strong>{sourceSucceeded}</strong></div>
        <div className="stat-cell"><span>Retained</span><strong>{sourceRetained}</strong></div>
        <div className="stat-cell"><span>Events</span><strong>{eventCount}</strong></div>
        <div className="stat-cell"><span>Elapsed</span><strong>{elapsed}</strong></div>
      </div>
      <div className="system-footer">
        <span>{health?.search_provider ? `Search: ${health.search_provider}` : 'Search: unavailable'}</span>
        <span>{health?.llm_configured ? 'Synthesis ready' : 'Synthesis unconfigured'}</span>
        <span>{reportLength.toLocaleString()} report chars</span>
      </div>
    </section>
  )
}

export default SystemStats
