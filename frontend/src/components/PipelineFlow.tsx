import type { RunStage } from '../api/client'

const NODES: Array<{ stage: RunStage; label: string; tint: string }> = [
  { stage: 'PLANNING', label: 'Plan', tint: '#FFE23A' },
  { stage: 'SEARCHING', label: 'Search', tint: '#AD69FF' },
  { stage: 'EXTRACTING', label: 'Extract', tint: '#4080FB' },
  { stage: 'RANKING', label: 'Rank', tint: '#F57EB4' },
  { stage: 'SYNTHESIZING', label: 'Synthesize', tint: '#22AC5F' },
  { stage: 'RENDERING', label: 'Render', tint: '#EF4225' },
]

const SEGMENT_D = 'M 40 60 C 90 20, 130 100, 180 60 C 230 20, 270 100, 320 60 C 370 20, 410 100, 460 60 C 510 20, 550 100, 600 60 C 650 20, 690 100, 740 60'
const NODE_X = [40, 180, 320, 460, 600, 740]
const NODE_Y = 60

type PipelineFlowProps = {
  stage: RunStage
}

function PipelineFlow({ stage }: PipelineFlowProps) {
  // The self-evaluation and research-round stages happen between Synthesize and Render.
  const stageOverrides: Partial<Record<RunStage, number>> = {
    SELF_EVALUATING: 4,
    RESEARCH_ROUND: 4,
  }
  const currentIndex = stage in stageOverrides ? stageOverrides[stage]! : NODES.findIndex((node) => node.stage === stage)
  const isDone = stage === 'DONE'
  const isFailed = stage === 'FAILED'
  const resolvedIndex = isDone ? NODES.length : currentIndex

  return (
    <div className="pipeline-flow" role="img" aria-label={`Pipeline stage: ${stage}`}>
      <svg viewBox="0 0 780 120" width="100%" height="120" preserveAspectRatio="none">
        <defs>
          <pattern id="pipeline-ink-dots" width="10" height="10" patternUnits="userSpaceOnUse">
            <circle cx="2" cy="2" r="1" fill="rgba(12,14,15,0.35)" />
          </pattern>
        </defs>

        {/* Ink outline path (thick) with dashed interior to look like a hand-drawn wire. */}
        <path d={SEGMENT_D} fill="none" stroke="#0C0E0F" strokeWidth="7" strokeLinecap="round" />
        <path d={SEGMENT_D} fill="none" stroke="#FFF8EE" strokeWidth="4" strokeLinecap="round" strokeDasharray="10 8" />
        {!isFailed && currentIndex >= 0 && (
          <path
            className="pipeline-flow-ants"
            d={SEGMENT_D}
            fill="none"
            stroke="#FBC93E"
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray="6 14"
          />
        )}

        {NODES.map((node, index) => {
          const state = index < resolvedIndex ? 'complete' : index === currentIndex ? 'active' : 'pending'
          const cx = NODE_X[index]
          const cy = NODE_Y
          const fill = state === 'pending' ? '#FFF8EE' : node.tint
          return (
            <g key={node.stage} className={`pipeline-node pipeline-node-${state}`} transform={`translate(${cx}, ${cy})`}>
              {/* Hard offset shadow */}
              <circle r="18" cx="4" cy="5" fill="#0C0E0F" opacity={state === 'pending' ? 0.35 : 1} />
              <circle r="18" cx="0" cy="0" className="pipeline-dot" fill={fill} stroke="#0C0E0F" strokeWidth="3" />
              {state === 'complete' ? (
                <path d="M -6 0 L -1 5 L 7 -5" fill="none" stroke="#0C0E0F" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" />
              ) : state === 'active' ? (
                <text y="6" textAnchor="middle" className="pipeline-index" fontSize="16" fontFamily="Bangers, sans-serif" fill="#0C0E0F">●</text>
              ) : (
                <text y="6" textAnchor="middle" className="pipeline-index" fontSize="16" fontFamily="Bangers, sans-serif" fill="rgba(12,14,15,0.55)">{index + 1}</text>
              )}
              <text
                y="50"
                textAnchor="middle"
                className="pipeline-label"
                fontSize="13"
                fontFamily="Titan One, sans-serif"
                fill={state === 'pending' ? 'rgba(12,14,15,0.55)' : '#0C0E0F'}
                stroke="#FFF8EE"
                strokeWidth="3"
                paintOrder="stroke"
              >
                {node.label.toUpperCase()}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

export default PipelineFlow
