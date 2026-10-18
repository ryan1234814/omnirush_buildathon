import { Children, cloneElement, isValidElement, type ReactNode } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { SourceEntry } from '../api/client'

type ReportViewProps = {
  report: string
  sources: SourceEntry[]
  isStreaming: boolean
  isPartial?: boolean
  partialReason?: string
}

function citationNodes(children: ReactNode): ReactNode {
  return Children.map(children, (child) => {
    if (isValidElement<{ children?: ReactNode }>(child)) {
      return cloneElement(child, {}, citationNodes(child.props.children))
    }
    if (typeof child !== 'string') return child

    return child.split(/(\[\d+\])/g).map((part, index) => {
      const match = /^\[(\d+)\]$/.exec(part)
      if (!match) return part
      const sourceId = Number(match[1])
      return (
        <sup className="citation" key={`${sourceId}-${index}`}>
          <a href={`#source-${sourceId}`} aria-label={`Jump to source ${sourceId}`}>
            {sourceId}
          </a>
        </sup>
      )
    })
  })
}

const markdownComponents: Components = {
  text: ({ children }) => <>{citationNodes(children)}</>,
  p: ({ children }) => <p>{citationNodes(children)}</p>,
  li: ({ children }) => <li>{citationNodes(children)}</li>,
  blockquote: ({ children }) => <blockquote>{citationNodes(children)}</blockquote>,
  h1: ({ children }) => <h1>{citationNodes(children)}</h1>,
  h2: ({ children }) => <h2>{citationNodes(children)}</h2>,
  h3: ({ children }) => <h3>{citationNodes(children)}</h3>,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noreferrer">
      {children}
    </a>
  ),
}

function sourceDetails(source: SourceEntry): { domain: string; favicon: string } {
  try {
    const url = new URL(source.url)
    return {
      domain: url.hostname.replace(/^www\./, ''),
      favicon: `https://www.google.com/s2/favicons?domain=${encodeURIComponent(url.hostname)}&sz=64`,
    }
  } catch {
    return { domain: source.url, favicon: 'https://www.google.com/favicon.ico' }
  }
}

function SourceCard({ source }: { source: SourceEntry }) {
  const details = sourceDetails(source)
  return (
    <a className="source-card" id={`source-${source.id}`} href={source.url} target="_blank" rel="noreferrer">
      <div className="source-heading">
        <img src={details.favicon} alt="" width="20" height="20" />
        <span>{details.domain}</span>
        <span className="source-number">[{source.id}]</span>
      </div>
      <strong>{source.title}</strong>
      <p>{source.excerpt}</p>
    </a>
  )
}

function ReportView({ report, sources, isStreaming, isPartial = false, partialReason }: ReportViewProps) {
  const reportBody = report.replace(/(?:^|\n)##\s+Sources\s*[\s\S]*$/i, '').trim()

  return (
    <article className="report-panel">
      <div className="run-panel-heading">
        <div>
          <p className="eyebrow accent">CITATION-BACKED OUTPUT</p>
          <h2>Research report</h2>
        </div>
        <span className="phase-label">{isStreaming ? 'STREAMING' : 'MARKDOWN'}</span>
      </div>

      {isPartial && (
        <div className="report-incomplete-note" role="status">
          <strong>Incomplete report</strong>
          <span>{partialReason || 'Synthesis stopped before all planned evidence could be incorporated.'} Review the available citations before relying on this report.</span>
        </div>
      )}

      <div className="report-body">
         {reportBody ? (
           <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
             {reportBody}
          </ReactMarkdown>
        ) : (
          <p className="report-placeholder">The agent is preparing the report…</p>
        )}
      </div>

      {sources.length > 0 && (
        <section className="sources-section" aria-label="Report sources">
          <div className="sources-heading">
            <p className="eyebrow">REFERENCES</p>
            <span>{sources.length} sources</span>
          </div>
          <div className="source-grid">
            {sources.map((source) => <SourceCard key={source.id} source={source} />)}
          </div>
        </section>
      )}
    </article>
  )
}

export default ReportView
