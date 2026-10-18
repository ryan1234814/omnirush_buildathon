export type ActivityItem = {
  label: string
  detail: string
}

type EventTickerProps = {
  items: ActivityItem[]
}

function EventTicker({ items }: EventTickerProps) {
  return (
    <section className="activity-panel" aria-labelledby="activity-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">EVENT STREAM</p>
          <h2 id="activity-title">Run activity</h2>
        </div>
        <span className="panel-index">LATEST FIRST</span>
      </div>
      {items.length === 0 ? (
        <p className="empty-state">Stage transitions and source fetches will appear here.</p>
      ) : (
        <ol className="activity-list">
          {items.map((item, index) => (
            <li key={`${item.label}-${item.detail}-${index}`}>
              <span className="activity-pulse" aria-hidden="true" />
              <span><strong>{item.label}</strong><small>{item.detail}</small></span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

export default EventTicker
