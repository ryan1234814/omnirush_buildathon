type WorkspaceView = 'control' | 'reports' | 'sources'

type WorkspaceHeaderProps = {
  statusLabel: string
  status: 'idle' | 'running' | 'done' | 'error'
  activeView: WorkspaceView
  onViewChange: (view: WorkspaceView) => void
  onProjectorToggle: () => void
  projectorMode: boolean
}

const NAV_ITEMS: Array<{ id: WorkspaceView; label: string }> = [
  { id: 'control', label: 'Mission control' },
  { id: 'reports', label: 'Report workspace' },
  { id: 'sources', label: 'Source intelligence' },
]

function WorkspaceHeader({
  statusLabel,
  status,
  activeView,
  onViewChange,
  onProjectorToggle,
  projectorMode,
}: WorkspaceHeaderProps) {
  return (
    <header className="topbar workspace-header">
      <div className="brand-lockup">
        <div className="brand-mark" aria-hidden="true">R</div>
        <div>
          <p className="eyebrow">OMNIRUSH / RESEARCH SYSTEM</p>
          <p className="brand-name">One-Click Reports</p>
        </div>
      </div>
      <nav className="workspace-nav" aria-label="Workspace sections">
        {NAV_ITEMS.map((item) => (
          <button
            className={activeView === item.id ? 'workspace-nav-item active' : 'workspace-nav-item'}
            key={item.id}
            type="button"
            onClick={() => onViewChange(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <div className="header-actions">
        <button className="projector-toggle" type="button" onClick={onProjectorToggle}>
          {projectorMode ? 'Normal view' : 'Projector mode'}
        </button>
        <div className="connection-status">
          <span className={`status-dot ${status === 'error' ? 'offline' : ''}`} />
          {statusLabel}
        </div>
      </div>
    </header>
  )
}

export type { WorkspaceView }
export default WorkspaceHeader
