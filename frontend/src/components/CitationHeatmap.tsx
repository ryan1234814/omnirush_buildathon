import { useMemo, useState } from 'react'
import type { SourceEntry } from '../api/client'

type CitationHeatmapProps = {
  report: string
  sources: SourceEntry[]
}

type SectionRow = {
  title: string
  counts: Map<number, number>
  total: number
}

function parseSections(report: string): SectionRow[] {
  // Split by `## ` (level-2) headings; skip a bare `# ` title block.
  const blocks = report.split(/\n(?=##\s)/)
  const rows: SectionRow[] = []
  for (const block of blocks) {
    const heading = /^##\s+(.+?)\s*$/m.exec(block)
    if (!heading) continue
    const title = heading[1].trim()
    if (/^sources$/i.test(title)) continue
    const counts = new Map<number, number>()
    let total = 0
    for (const match of block.matchAll(/\[(\d+)\]/g)) {
      const id = Number(match[1])
      counts.set(id, (counts.get(id) ?? 0) + 1)
      total += 1
    }
    rows.push({ title, counts, total })
  }
  return rows
}

function CitationHeatmap({ report, sources }: CitationHeatmapProps) {
  const rows = useMemo(() => parseSections(report), [report])
  const [hover, setHover] = useState<{ row: number; col: number } | null>(null)

  if (rows.length === 0 || sources.length === 0) return null

  const maxCount = Math.max(
    1,
    ...rows.flatMap((row) => sources.map((source) => row.counts.get(source.id) ?? 0)),
  )

  return (
    <section className="citation-heatmap" aria-label="Citation coverage by section">
      <div className="heatmap-heading">
        <div>
          <p className="eyebrow">CITATION COVERAGE</p>
          <h3>Which sources feed which sections?</h3>
        </div>
        <span className="panel-index">{rows.length} SECTIONS · {sources.length} SOURCES</span>
      </div>

      <div className="heatmap-grid" role="table" style={{ ['--heatmap-cols' as string]: sources.length }}>
        <div className="heatmap-row heatmap-row-head" role="row">
          <span className="heatmap-corner" />
          {sources.map((source) => (
            <span key={source.id} className="heatmap-col-label" role="columnheader" title={source.title}>
              [{source.id}]
            </span>
          ))}
        </div>
        {rows.map((row, rowIndex) => (
          <div className="heatmap-row" key={row.title} role="row">
            <span className="heatmap-row-label" title={row.title} role="rowheader">
              {row.title}
              <em>{row.total}</em>
            </span>
            {sources.map((source, colIndex) => {
              const count = row.counts.get(source.id) ?? 0
              const intensity = count === 0 ? 0 : 0.15 + 0.85 * (count / maxCount)
              const isHovered = hover?.row === rowIndex && hover?.col === colIndex
              return (
                <button
                  type="button"
                  key={source.id}
                  className={`heatmap-cell${count === 0 ? ' empty' : ''}${isHovered ? ' hovered' : ''}`}
                  style={{ ['--intensity' as string]: intensity }}
                  onMouseEnter={() => setHover({ row: rowIndex, col: colIndex })}
                  onMouseLeave={() => setHover(null)}
                  onFocus={() => setHover({ row: rowIndex, col: colIndex })}
                  onBlur={() => setHover(null)}
                  aria-label={`${row.title} cites source ${source.id} ${count} time${count === 1 ? '' : 's'}`}
                >
                  <span className="heatmap-cell-count">{count || ''}</span>
                </button>
              )
            })}
          </div>
        ))}
      </div>

      {hover && (
        <p className="heatmap-hover" role="status">
          <strong>{rows[hover.row].title}</strong> → [{sources[hover.col].id}] {sources[hover.col].title}
          <span className="heatmap-hover-count">
            {rows[hover.row].counts.get(sources[hover.col].id) ?? 0} citation
            {(rows[hover.row].counts.get(sources[hover.col].id) ?? 0) === 1 ? '' : 's'}
          </span>
        </p>
      )}
    </section>
  )
}

export default CitationHeatmap
