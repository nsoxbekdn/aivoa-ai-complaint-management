import { useEffect } from 'react';
import { Link } from 'react-router-dom';

import { useAppDispatch, useAppSelector } from '../app/hooks';
import {
  fetchComplaint,
  resetChat,
  updateComplaint,
} from '../features/complaints/complaintsSlice';
import { PRIORITIES, SEVERITIES, STATUSES, labelFor } from '../features/complaints/labels';
import { ComplaintChat } from './ComplaintChat';
import { DuplicateCard } from './DuplicateCard';
import { ErrorAlert } from './ErrorAlert';
import { LoadingIndicator } from './LoadingIndicator';

interface ComplaintDetailProps {
  complaintId: number;
}

function KeyValue({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div>
      <div className="key-value__label">{label}</div>
      <div className="key-value__value">{value === null || value === '' ? '—' : value}</div>
    </div>
  );
}

export function ComplaintDetail({ complaintId }: ComplaintDetailProps) {
  const dispatch = useAppDispatch();
  const { complaint, loading, error, updating } = useAppSelector(
    (state) => state.complaints.current,
  );

  useEffect(() => {
    dispatch(fetchComplaint(complaintId));
    dispatch(resetChat());
  }, [dispatch, complaintId]);

  if (loading) return <LoadingIndicator label="Loading complaint…" />;
  if (error) return <ErrorAlert title="Could not load this complaint" message={error} />;
  if (!complaint) return null;

  return (
    <>
      <div className="page__heading row-between">
        <div>
          <h1>{complaint.complaint_number}</h1>
          <p>
            Lodged {new Date(complaint.created_at).toLocaleString()} ·{' '}
            <Link to="/complaints">back to all complaints</Link>
          </p>
        </div>
        <div className="qa-controls">
          <label>
            <span>Status</span>
            <select
              value={complaint.status}
              disabled={updating}
              onChange={(event) =>
                dispatch(
                  updateComplaint({ id: complaint.id, payload: { status: event.target.value } }),
                )
              }
            >
              {STATUSES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>QA severity</span>
            <select
              value={complaint.initial_severity ?? ''}
              disabled={updating}
              onChange={(event) =>
                dispatch(
                  updateComplaint({
                    id: complaint.id,
                    payload: { initial_severity: event.target.value || null },
                  }),
                )
              }
            >
              <option value="">Not assigned</option>
              {SEVERITIES.filter((option) => option.value !== 'unknown').map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>QA priority</span>
            <select
              value={complaint.priority ?? ''}
              disabled={updating}
              onChange={(event) =>
                dispatch(
                  updateComplaint({
                    id: complaint.id,
                    payload: { priority: event.target.value || null },
                  }),
                )
              }
            >
              <option value="">Not assigned</option>
              {PRIORITIES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <div className="detail-grid">
        <div className="stack-3">
          <div className="card">
            <div className="card__header">
              <h2>Lodged complaint record</h2>
            </div>
            <div className="card__body stack-3">
              <div className="key-values">
                <KeyValue label="Source" value={labelFor(complaint.complaint_source)} />
                <KeyValue label="Reporter" value={complaint.customer_name} />
                <KeyValue label="Contact" value={complaint.customer_contact} />
                <KeyValue label="Product" value={complaint.product_name} />
                <KeyValue label="Strength / grade" value={complaint.product_strength_grade} />
                <KeyValue label="Batch / lot" value={complaint.batch_lot_number} />
                <KeyValue label="Manufactured" value={complaint.manufacturing_date} />
                <KeyValue label="Expiry" value={complaint.expiry_date} />
                <KeyValue
                  label="Quantity affected"
                  value={
                    complaint.quantity_affected === null
                      ? null
                      : `${complaint.quantity_affected} ${labelFor(complaint.quantity_unit)}`
                  }
                />
                <KeyValue label="Complaint type" value={labelFor(complaint.complaint_type)} />
                <KeyValue label="Date observed" value={complaint.complaint_date} />
                <KeyValue label="QA severity" value={labelFor(complaint.initial_severity)} />
                <KeyValue label="QA priority" value={labelFor(complaint.priority)} />
              </div>

              <div>
                <div className="sub-heading">Complaint description</div>
                <p style={{ marginBottom: 0 }}>{complaint.complaint_details ?? '—'}</p>
              </div>
            </div>
          </div>

          {complaint.original_text && (
            <div className="card">
              <div className="card__header">
                <div>
                  <h2>Original submission</h2>
                  <p>{complaint.input_filename ?? 'Pasted text'}</p>
                </div>
              </div>
              <div className="card__body">
                <pre className="source-text">{complaint.original_text}</pre>
              </div>
            </div>
          )}

          {complaint.intake_transcript?.length ? (
            <div className="card">
              <div className="card__header">
                <div>
                  <h2>Intake conversation</h2>
                  <p>How the reporter clarified the complaint details.</p>
                </div>
              </div>
              <div className="card__body">
                <div className="chat__messages">
                  {complaint.intake_transcript.map((message, index) => (
                    <div
                      key={`${message.role}-${index}`}
                      className={`chat__message chat__message--${message.role}`}
                    >
                      {message.text}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : null}
        </div>

        <div className="stack-3">
          <div className="card card--ai">
            <div className="card__header">
              <div>
                <h2>Internal QA copilot</h2>
                <p>Investigation support for the worker handling this lodged complaint.</p>
              </div>
              <span className="badge badge--ai">Internal · advisory</span>
            </div>
            <div className="card__body">
              {complaint.analysis_warnings?.length ? (
                <div className="alert alert--warning" style={{ marginBottom: 16 }}>
                  <strong>Analysis note</strong>
                  <ul className="bullet-list text-small" style={{ marginBottom: 0 }}>
                    {complaint.analysis_warnings.map((warning, index) => (
                      <li key={`${warning}-${index}`}>{warning}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <div className="key-values">
                <KeyValue label="Risk level" value={labelFor(complaint.risk_level)} />
                <KeyValue
                  label="Completeness"
                  value={
                    complaint.completeness_score === null
                      ? null
                      : `${complaint.completeness_score}%`
                  }
                />
                <KeyValue
                  label="Model confidence"
                  value={
                    complaint.risk_confidence === null
                      ? null
                      : `${Math.round(complaint.risk_confidence * 100)}%`
                  }
                />
              </div>

              <div className="chip-list" style={{ marginTop: 12 }}>
                <span className={`chip ${complaint.patient_safety_concern ? 'chip--critical' : ''}`}>
                  {complaint.patient_safety_concern
                    ? '⚠ Possible patient safety impact'
                    : 'No patient safety flag'}
                </span>
                <span className={`chip ${complaint.product_quality_concern ? 'chip--critical' : ''}`}>
                  {complaint.product_quality_concern
                    ? 'Product quality concern'
                    : 'No product quality flag'}
                </span>
              </div>

              {complaint.ai_summary && (
                <>
                  <div className="sub-heading">Formal complaint summary</div>
                  <p className="text-small">{complaint.ai_summary}</p>
                </>
              )}

              {complaint.risk_rationale && (
                <>
                  <div className="sub-heading">Risk rationale</div>
                  <p className="text-small">{complaint.risk_rationale}</p>
                </>
              )}

              {complaint.missing_fields?.length ? (
                <>
                  <div className="sub-heading">Information missing at intake</div>
                  <div className="chip-list">
                    {complaint.missing_fields.map((field) => (
                      <span key={field} className="chip">
                        {field}
                      </span>
                    ))}
                  </div>
                </>
              ) : null}

              {complaint.root_cause_recommendations?.length ? (
                <>
                  <div className="sub-heading">Possible root causes</div>
                  <ul className="bullet-list text-small">
                    {complaint.root_cause_recommendations.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </>
              ) : null}

              {complaint.initial_investigation_steps?.length ? (
                <>
                  <div className="sub-heading">Initial investigation steps</div>
                  <ul className="bullet-list text-small">
                    {complaint.initial_investigation_steps.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </>
              ) : null}

              {complaint.capa_recommendations?.length ? (
                <>
                  <div className="sub-heading">Preliminary CAPA suggestions</div>
                  <ul className="bullet-list text-small">
                    {complaint.capa_recommendations.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </>
              ) : null}

              <p className="text-small text-muted" style={{ marginTop: 12, marginBottom: 0 }}>
                AI-generated investigation support. QA review governs every decision.
              </p>
            </div>
          </div>

          <DuplicateCard candidates={complaint.duplicate_candidates ?? []} />

          {complaint.source_documents?.length ? (
            <div className="card">
              <div className="card__header">
                <div>
                  <h2>Source-document provenance</h2>
                  <p>Files retained in the final QA handoff.</p>
                </div>
              </div>
              <div className="card__body stack-3">
                {complaint.source_documents.map((document, index) => (
                  <div className="source-document" key={`${document.filename}-${index}`}>
                    <div className="row-between">
                      <strong>{document.filename}</strong>
                      <span className={`badge ${document.ocr_used ? 'badge--warn' : 'badge--success'}`}>
                        {document.ocr_used ? 'Groq Vision OCR' : 'Native text'}
                      </span>
                    </div>
                    <div className="text-small text-muted">
                      {document.page_count} page{document.page_count === 1 ? '' : 's'} ·{' '}
                      {document.extraction_method.replaceAll('_', ' ')}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <ComplaintChat complaintId={complaint.id} complaintNumber={complaint.complaint_number} />
        </div>
      </div>
    </>
  );
}
