import { useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

const exampleTopics = ['AI agent reliability', 'Future of remote work', 'Climate tech in 2026']

function App() {
  const [topic, setTopic] = useState('')

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
  }

  return (
    <main className="mission-control">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true">
          R
        </div>
        <div>
          <p className="eyebrow">OMNIRUSH / RESEARCH SYSTEM</p>
          <p className="brand-name">One-Click Reports</p>
        </div>
        <div className="connection-status">
          <span className="status-dot" />
          SYSTEM READY
        </div>
      </header>

      <section className="hero-section">
        <p className="eyebrow accent">AUTONOMOUS RESEARCH, ON DEMAND</p>
        <h1>Turn a question into a report.</h1>
        <p className="hero-copy">
          Watch an AI research agent search the web, read the best sources, and assemble a
          citation-backed report you can share.
        </p>

        <form className="topic-form" onSubmit={handleSubmit}>
          <label htmlFor="topic">What should we research?</label>
          <div className="input-row">
            <input
              id="topic"
              type="text"
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              placeholder="e.g. How will AI change customer support?"
            />
            <button type="submit">Start research <span aria-hidden="true">→</span></button>
          </div>
        </form>

        <div className="examples" aria-label="Example topics">
          <span>TRY AN EXAMPLE</span>
          {exampleTopics.map((example) => (
            <button key={example} type="button" onClick={() => setTopic(example)}>
              {example}
            </button>
          ))}
        </div>
      </section>

      <section className="pipeline-preview" aria-label="Research pipeline">
        <div className="section-heading">
          <div>
            <p className="eyebrow">PIPELINE PREVIEW</p>
            <h2>From prompt to proof</h2>
          </div>
          <span className="phase-label">PHASE 01 / READY</span>
        </div>
        <div className="stage-grid">
          {['Plan the search', 'Read the sources', 'Write with citations'].map((stage, index) => (
            <article className="stage-card" key={stage}>
              <span className="stage-number">0{index + 1}</span>
              <h3>{stage}</h3>
              <p>
                {index === 0 && 'Break your topic into focused research questions.'}
                {index === 1 && 'Extract and rank evidence from trusted sources.'}
                {index === 2 && 'Deliver a clear report with verifiable references.'}
              </p>
            </article>
          ))}
        </div>
      </section>
    </main>
  )
}

export default App
