import { useEffect, useState } from 'react';

import type { ComplaintAnalysisResponse } from '../types/complaint';

interface ExtractionProgressProps {
  analyzing: boolean;
  startedAt: number | null;
  analysis: ComplaintAnalysisResponse | null;
}

/** The nodes of the backend LangGraph, in execution order. */
const STAGES: { key: string; label: string; done: (a: ComplaintAnalysisResponse) => boolean }[] = [
  { key: 'prepare', label: 'Prepare input', done: (a) => a.original_text.length > 0 },
  {
    key: 'extract',
    label: 'Extract complaint fields',
    done: (a) => Object.values(a.extracted_fields).some((value) => value !== null),
  },
  { key: 'validate', label: 'Validate structured output', done: () => true },
  { key: 'completeness', label: 'Assess completeness', done: (a) => a.completeness.score >= 0 },
  {
    key: 'risk',
    label: 'Classify risk',
    done: (a) => a.risk_assessment.risk_level !== 'unknown',
  },
  { key: 'summary', label: 'Generate summary', done: (a) => a.summary.length > 0 },
  {
    key: 'recommendations',
    label: 'Generate root causes & CAPA',
    done: (a) => a.recommendations.possible_root_causes.length > 0,
  },
  { key: 'assemble', label: 'Assemble result', done: () => true },
];

export function ExtractionProgress({ analyzing, startedAt, analysis }: ExtractionProgressProps) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!analyzing || !startedAt) return;
    const tick = () => setElapsed(Math.round((Date.now() - startedAt) / 1000));
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [analyzing, startedAt]);

  if (!analyzing && !analysis) return null;

  return (
    <div className="progress" aria-live="polite">
      <div className="progress__header">
        <span>{analyzing ? 'Analysing complaint…' : 'Analysis complete'}</span>
        <span className="text-muted text-small">
          {analyzing ? `${elapsed}s elapsed` : `${STAGES.length} workflow stages`}
        </span>
      </div>

      <ul className="progress__stages">
        {STAGES.map((stage) => {
          const done = !analyzing && analysis ? stage.done(analysis) : false;
          const state = analyzing ? 'running' : done ? 'done' : '';
          return (
            <li key={stage.key} className={`progress__stage ${state ? `progress__stage--${state}` : ''}`}>
              <span className="progress__dot" aria-hidden="true">
                {done ? '✓' : ''}
              </span>
              <span>{stage.label}</span>
              {!analyzing && !done && <span className="text-muted"> · no output</span>}
            </li>
          );
        })}
      </ul>

      <p className="progress__note">
        The backend runs these LangGraph nodes in a single request, so each stage is confirmed
        from the response rather than streamed live.
      </p>
    </div>
  );
}
