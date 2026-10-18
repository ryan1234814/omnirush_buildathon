import { useEffect, useMemo, useRef, useState } from 'react'

export type CommandItem = {
  id: string
  label: string
  hint?: string
  section: string
  keywords?: string
  run: () => void
}

type CommandPaletteProps = {
  open: boolean
  items: CommandItem[]
  onClose: () => void
}

function CommandPalette({ open, items, onClose }: CommandPaletteProps) {
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return items
    return items.filter((item) =>
      `${item.label} ${item.hint ?? ''} ${item.section} ${item.keywords ?? ''}`
        .toLowerCase()
        .split(/\s+/)
        .some((token) => token.startsWith(q) || q.includes(token) || token.includes(q)),
    )
  }, [items, query])

  const grouped = useMemo(() => {
    const map = new Map<string, CommandItem[]>()
    for (const item of filtered) {
      const bucket = map.get(item.section)
      if (bucket) bucket.push(item)
      else map.set(item.section, [item])
    }
    return [...map.entries()]
  }, [filtered])

  const flat = useMemo(() => grouped.flatMap(([, bucket]) => bucket), [grouped])

  useEffect(() => {
    const focus = window.setTimeout(() => inputRef.current?.focus(), 20)
    return () => window.clearTimeout(focus)
  }, [])

  useEffect(() => {
    if (!open) return
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        setCursor((current) => (flat.length === 0 ? 0 : (current + 1) % flat.length))
        return
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault()
        setCursor((current) => (flat.length === 0 ? 0 : (current - 1 + flat.length) % flat.length))
        return
      }
      if (event.key === 'Enter') {
        event.preventDefault()
        const item = flat[cursor]
        if (item) {
          item.run()
          onClose()
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, flat, cursor, onClose])

  if (!open) return null

  let runningIndex = -1
  return (
    <div className="command-palette-scrim" onMouseDown={onClose}>
      <div
        className="command-palette"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <input
          ref={inputRef}
          className="command-palette-input"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value)
            setCursor(0)
          }}
          placeholder="Search pages, topics, actions…"
          aria-label="Command search"
        />
        {flat.length === 0 ? (
          <p className="command-palette-empty">No commands match “{query}”.</p>
        ) : (
          <div className="command-palette-list">
            {grouped.map(([section, bucket]) => (
              <div className="command-palette-section" key={section}>
                <p className="command-palette-section-label">{section}</p>
                {bucket.map((item) => {
                  runningIndex += 1
                  const active = runningIndex === cursor
                  const localIndex = flat.indexOf(item)
                  return (
                    <button
                      key={item.id}
                      type="button"
                      className={`command-palette-row${active ? ' active' : ''}`}
                      onMouseEnter={() => setCursor(localIndex)}
                      onClick={() => {
                        item.run()
                        onClose()
                      }}
                    >
                      <span className="command-palette-row-label">{item.label}</span>
                      {item.hint && <span className="command-palette-row-hint">{item.hint}</span>}
                    </button>
                  )
                })}
              </div>
            ))}
          </div>
        )}
        <div className="command-palette-footer">
          <span><kbd>↑</kbd><kbd>↓</kbd> navigate</span>
          <span><kbd>⏎</kbd> run</span>
          <span><kbd>esc</kbd> close</span>
        </div>
      </div>
    </div>
  )
}

export default CommandPalette
