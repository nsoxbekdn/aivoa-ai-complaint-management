import type { CompletenessAssessment } from '../types/complaint';

interface CompletenessCardProps {
  completeness: CompletenessAssessment;
}

export function CompletenessCard({ completeness }: CompletenessCardProps) {
  const { score, is_complete, missing_critical_fields, missing_optional_fields, follow_up_questions } =
    completeness;
  const fill = score >= 80 ? 'ok' : score >= 50 ? 'warn' : 'danger';

  return (
    <section className="result-card">
      <div className="result-card__title">
        <span>Completeness</span>
        <span className={`badge badge--${is_complete ? 'low' : 'medium'}`}>
          {is_complete ? 'Ready to log' : 'Needs follow-up'}
        </span>
      </div>

      <div className="row-between" style={{ marginBottom: 6 }}>
        <span className="text-small text-muted">Intake record completeness</span>
        <strong>{score}%</strong>
      </div>
      <div className="meter">
        <div className={`meter__fill meter__fill--${fill}`} style={{ width: `${score}%` }} />
      </div>

      {missing_critical_fields.length > 0 && (
        <>
          <div className="sub-heading">Missing critical information</div>
          <div className="chip-list">
            {missing_critical_fields.map((field) => (
              <span key={field} className="chip chip--critical">
                {field}
              </span>
            ))}
          </div>
        </>
      )}

      {missing_optional_fields.length > 0 && (
        <>
          <div className="sub-heading">Missing optional information</div>
          <div className="chip-list">
            {missing_optional_fields.map((field) => (
              <span key={field} className="chip">
                {field}
              </span>
            ))}
          </div>
        </>
      )}

      {follow_up_questions.length > 0 && (
        <>
          <div className="sub-heading">Suggested follow-up questions</div>
          <ul className="bullet-list text-small">
            {follow_up_questions.map((question) => (
              <li key={question}>{question}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
