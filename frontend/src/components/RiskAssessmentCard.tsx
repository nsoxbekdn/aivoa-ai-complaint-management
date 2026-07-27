import { labelFor } from '../features/complaints/labels';
import type { RiskAssessment } from '../types/complaint';

interface RiskAssessmentCardProps {
  risk: RiskAssessment;
}

export function RiskAssessmentCard({ risk }: RiskAssessmentCardProps) {
  return (
    <section className="result-card">
      <div className="result-card__title">
        <span>Preliminary risk assessment</span>
        <span className={`badge badge--${risk.risk_level}`}>{risk.risk_level} risk</span>
      </div>

      <div className="key-values">
        <div>
          <div className="key-value__label">Severity</div>
          <div className="key-value__value">{labelFor(risk.severity)}</div>
        </div>
        <div>
          <div className="key-value__label">Priority</div>
          <div className="key-value__value">{labelFor(risk.priority)}</div>
        </div>
        <div>
          <div className="key-value__label">Model confidence</div>
          <div className="key-value__value">{Math.round(risk.confidence * 100)}%</div>
        </div>
      </div>

      <div className="chip-list" style={{ marginTop: 12 }}>
        <span className={`chip ${risk.patient_safety_concern ? 'chip--critical' : ''}`}>
          {risk.patient_safety_concern ? '⚠ Possible patient safety impact' : 'No patient safety flag'}
        </span>
        <span className={`chip ${risk.product_quality_concern ? 'chip--critical' : ''}`}>
          {risk.product_quality_concern ? 'Product quality concern' : 'No product quality flag'}
        </span>
      </div>

      {risk.rationale && (
        <>
          <div className="sub-heading">Rationale</div>
          <p className="text-small" style={{ marginBottom: 0 }}>
            {risk.rationale}
          </p>
        </>
      )}

      <p className="text-small text-muted" style={{ marginTop: 12, marginBottom: 0 }}>
        Triage support only. The final severity and regulatory classification are decided by
        qualified QA / pharmacovigilance personnel.
      </p>
    </section>
  );
}
