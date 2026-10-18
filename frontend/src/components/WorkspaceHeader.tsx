type WorkspaceView = 'control' | 'reports' | 'sources'

type WorkspaceHeaderProps = {
  statusLabel: string
  status: 'idle' | 'running' | 'done' | 'error'
  activeView: WorkspaceView
  onViewChange: (view: WorkspaceView) => void
  onProjectorToggle: () => void
  projectorMode: boolean
  soundEnabled: boolean
  onSoundToggle: () => void
  onOpenPalette: () => void
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
  soundEnabled,
  onSoundToggle,
  onOpenPalette,
}: WorkspaceHeaderProps) {
  return (
    <header className="topbar workspace-header">
      <div className="brand-lockup">
        <div className="brand-mark" aria-hidden="true">R</div>
        <div>
          <p className="eyebrow">OMNIRUSH · RESEARCH AGENT</p>
          <p className="brand-name">Omnirush</p>
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
        <button
          className="palette-hint"
          type="button"
          onClick={onOpenPalette}
          aria-label="Open command palette"
          title="Command palette (⌘K)"
        >
          <kbd>⌘</kbd><kbd>K</kbd>
        </button>
        <button
          className={`sound-toggle${soundEnabled ? ' active' : ''}`}
          type="button"
          onClick={onSoundToggle}
          aria-pressed={soundEnabled}
          aria-label={soundEnabled ? 'Mute sound cues' : 'Enable sound cues'}
          title={soundEnabled ? 'Mute sound cues' : 'Enable sound cues'}
        >
          {soundEnabled ? (
            <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
              <path fill="currentColor" d="M4 9v6h4l5 4V5L8 9H4zm11.5 3a3 3 0 0 0-1.5-2.6v5.2A3 3 0 0 0 15.5 12zM14 3.2v2.1a6.8 6.8 0 0 1 0 13.4v2.1a8.9 8.9 0 0 0 0-17.6z" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
              <path fill="currentColor" d="M4 9v6h4l5 4V5L8 9H4zm15.5 3l2.5-2.5-1.4-1.4L18 10.6l-2.6-2.5-1.4 1.4 2.6 2.5-2.6 2.5 1.4 1.4 2.6-2.5 2.5 2.5 1.4-1.4L19.5 12z" />
            </svg>
          )}
        </button>
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
