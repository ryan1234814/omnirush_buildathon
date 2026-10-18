export type HistoryEntry = {
  id: string
  topic: string
  status: string
  createdAt: string
}

type RecentRunsProps = {
  entries: HistoryEntry[]
  activeId: string | null
  onSelect: (id: string) => void
  onClear: () => void
}

function RecentRuns({ entries, activeId, onSelect, onClear }: RecentRunsProps) {
  return (
    <section className="dashboard-panel history-panel" aria-labelledby="history-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">LOCAL ARCHIVE</p>
          <h2 id="history-title">Recent runs</h2>
        </div>
        {entries.length > 0 && <button className="text-button" type="button" onClick={onClear}>Clear</button>}
      </div>
      {entries.length === 0 ? (
        <p className="empty-state">Your completed and active runs will appear here.</p>
      ) : (
        <div className="history-list">
          {entries.map((entry) => (
            <button
              className={entry.id === activeId ? 'history-row active' : 'history-row'}
              key={entry.id}
              type="button"
              onClick={() => onSelect(entry.id)}
            >
              <span className={`history-status ${entry.status}`}>{entry.status === 'completed' ? '✓' : entry.status === 'failed' ? '!' : '◌'}</span>
              <span className="history-copy">
                <strong>{entry.topic}</strong>
                <small>{entry.status} · {new Date(entry.createdAt).toLocaleDateString()}</small>
              </span>
              <span className="history-arrow" aria-hidden="true">→</span>
            </button>
          ))}
        </div>
      )}
      <p className="panel-note">Stored in this browser · {entries.length}/10 slots used</p>
    </section>
  )
}

export default RecentRuns
