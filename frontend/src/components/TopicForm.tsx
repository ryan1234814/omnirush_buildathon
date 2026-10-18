import type { FormEvent } from 'react'

const EXAMPLE_TOPICS = [
  'Quantum computing 2026',
  'AI agent reliability',
  'Future of remote work',
  'Climate tech in 2026',
]

type TopicFormProps = {
  topic: string
  isRunning: boolean
  onTopicChange: (topic: string) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

function TopicForm({ topic, isRunning, onTopicChange, onSubmit }: TopicFormProps) {
  return (
    <div className="topic-form-wrap">
      <form className="topic-form" onSubmit={onSubmit}>
        <label htmlFor="topic">What should we research?</label>
        <div className="input-row">
          <input
            id="topic"
            type="text"
            value={topic}
            onChange={(event) => onTopicChange(event.target.value)}
            placeholder="e.g. How will AI change customer support?"
            maxLength={500}
            disabled={isRunning}
          />
          <button type="submit" disabled={isRunning}>
            {isRunning ? 'Researching…' : 'Start research'} <span aria-hidden="true">→</span>
          </button>
        </div>
      </form>

      <div className="examples" aria-label="Example topics">
        <span>TRY AN EXAMPLE</span>
        {EXAMPLE_TOPICS.map((example) => (
          <button key={example} type="button" onClick={() => onTopicChange(example)} disabled={isRunning}>
            {example}
          </button>
        ))}
      </div>
    </div>
  )
}

export default TopicForm
