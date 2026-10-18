type CapabilitiesPanelProps = {
  onUseExample: (topic: string) => void
}

const CAPABILITIES = [
  { number: '01', title: 'Plan the search', detail: 'Break a broad question into focused research queries.', topic: 'Quantum computing 2026' },
  { number: '02', title: 'Read the web', detail: 'Extract evidence and keep dead or empty sources out.', topic: 'AI agent reliability' },
  { number: '03', title: 'Rank evidence', detail: 'Keep the strongest sources inside a bounded context.', topic: 'Climate tech in 2026' },
  { number: '04', title: 'Write with proof', detail: 'Stream a clear report with deterministic citations.', topic: 'Future of remote work' },
]

function CapabilitiesPanel({ onUseExample }: CapabilitiesPanelProps) {
  return (
    <section className="dashboard-panel capabilities-panel" aria-labelledby="capabilities-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">RESEARCH STACK</p>
          <h2 id="capabilities-title">What the agent does</h2>
        </div>
        <span className="panel-index">04 STEPS</span>
      </div>
      <div className="capability-list">
        {CAPABILITIES.map((capability) => (
          <button className="capability-row" key={capability.number} type="button" onClick={() => onUseExample(capability.topic)}>
            <span className="capability-number">{capability.number}</span>
            <span className="capability-copy"><strong>{capability.title}</strong><small>{capability.detail}</small></span>
            <span className="capability-arrow" aria-hidden="true">↗</span>
          </button>
        ))}
      </div>
    </section>
  )
}

export default CapabilitiesPanel
