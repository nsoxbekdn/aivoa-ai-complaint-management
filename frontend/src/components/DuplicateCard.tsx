import { Link } from 'react-router-dom';

import type { DuplicateCandidate } from '../types/complaint';

interface DuplicateCardProps {
  candidates: DuplicateCandidate[];
}

export function DuplicateCard({ candidates }: DuplicateCardProps) {
  if (candidates.length === 0) return null;

  return (
    <section className="result-card">
      <div className="result-card__title">
        <span>Possible related complaints</span>
        <span className="badge badge--medium">{candidates.length} to check</span>
      </div>

      <ul className="bullet-list text-small">
        {candidates.map((candidate) => (
          <li key={candidate.complaint_id}>
            <Link to={`/complaints/${candidate.complaint_id}`}>{candidate.complaint_number}</Link>{' '}
            — {candidate.product_name ?? 'unknown product'}
            {candidate.batch_lot_number ? ` · batch ${candidate.batch_lot_number}` : ''}
            <div className="text-muted">
              {candidate.reason} · similarity {Math.round(candidate.similarity * 100)}%
            </div>
          </li>
        ))}
      </ul>

      <p className="text-small text-muted" style={{ marginBottom: 0 }}>
        Similarity is a hint, not a verdict — confirm manually before linking or closing as a
        duplicate.
      </p>
    </section>
  );
}
