import type { ComplaintRecommendations } from '../types/complaint';

interface RecommendationCardProps {
  recommendations: ComplaintRecommendations;
}

const SECTIONS: { key: keyof ComplaintRecommendations; title: string }[] = [
  { key: 'possible_root_causes', title: 'Possible root causes' },
  { key: 'initial_investigation_steps', title: 'Initial investigation steps' },
  { key: 'preliminary_capa_suggestions', title: 'Preliminary CAPA suggestions' },
];

export function RecommendationCard({ recommendations }: RecommendationCardProps) {
  const isEmpty = SECTIONS.every((section) => recommendations[section.key].length === 0);
  if (isEmpty) return null;

  return (
    <section className="result-card">
      <div className="result-card__title">
        <span>Investigation suggestions</span>
        <span className="badge badge--ai">Preliminary</span>
      </div>

      {SECTIONS.map((section) =>
        recommendations[section.key].length ? (
          <div key={section.key}>
            <div className="sub-heading">{section.title}</div>
            <ul className="bullet-list text-small">
              {recommendations[section.key].map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null,
      )}

      <p className="text-small text-muted" style={{ marginTop: 12, marginBottom: 0 }}>
        These are starting points for a qualified investigator — not conclusions, and not an
        approved CAPA plan.
      </p>
    </section>
  );
}
