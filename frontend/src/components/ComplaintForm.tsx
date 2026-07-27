import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';

import { useAppDispatch, useAppSelector } from '../app/hooks';
import {
  createComplaint,
  clearIntake,
  dismissSaveError,
  setFormField,
  validateBeforeSave,
} from '../features/complaints/complaintsSlice';
import {
  buildCreatePayload,
  isReporterReadyToLodge,
  validateForm,
} from '../features/complaints/formUtils';
import {
  COMPLAINT_SOURCES,
  COMPLAINT_TYPES,
  QUANTITY_UNITS,
} from '../features/complaints/labels';
import type { ComplaintFormField } from '../types/complaint';
import { ErrorAlert } from './ErrorAlert';
import { FormField } from './FormField';
import { SaveConfirmationDialog } from './SaveConfirmationDialog';

/** Reporter-owned factual record. Risk, severity, priority and CAPA stay in the lodged
 * complaint's internal QA workspace. */
export function ComplaintForm() {
  const dispatch = useAppDispatch();
  const {
    formData,
    fieldSources,
    validationErrors,
    analysis,
    intakeChat,
    saving,
    saveError,
    savedComplaint,
  } = useAppSelector((state) => state.complaints);

  const aiFieldCount = Object.entries(fieldSources).filter(
    ([field, source]) =>
      source === 'ai' && field !== 'initial_severity' && field !== 'priority',
  ).length;
  const reporterReadyToLodge = isReporterReadyToLodge(formData);
  const quantityRequired = new Set([
    'product_quality_defect',
    'packaging_defect',
    'contamination',
    'wrong_product_or_strength',
    'labelling_error',
  ]).has(formData.complaint_type);

  const bind = (field: ComplaintFormField) => ({
    name: field,
    value: formData[field],
    error: validationErrors[field],
    aiFilled: fieldSources[field] === 'ai',
    disabled: saving,
    onChange: (value: string) => dispatch(setFormField({ field, value })),
  });

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const errors = validateForm(formData);
    dispatch(validateBeforeSave());
    if (Object.keys(errors).length > 0) {
      document.getElementById(Object.keys(errors)[0])?.focus();
      return;
    }
    dispatch(createComplaint(buildCreatePayload(formData, analysis, intakeChat.messages)));
  };

  return (
    <form className="card" onSubmit={handleSubmit} noValidate>
      <div className="card__header">
        <div>
          <h2>Complaint details</h2>
          <p>Review the facts gathered by the assistant before lodging the complaint.</p>
        </div>
        {aiFieldCount > 0 && (
          <span className="badge badge--ai">{aiFieldCount} assisted fields · review</span>
        )}
      </div>

      <div className="card__body">
        {saveError && (
          <ErrorAlert
            title="Could not lodge the complaint"
            message={saveError}
            onDismiss={() => dispatch(dismissSaveError())}
          />
        )}
        {savedComplaint && (
          <p className="text-small">
            Lodged as <strong>{savedComplaint.complaint_number}</strong> ·{' '}
            <Link to={`/complaints/${savedComplaint.id}`}>Open the complaint →</Link>
          </p>
        )}

        <section className="form-section">
          <div className="form-section__title">
            <span className="form-section__step">1</span> Reporter details
          </div>
          <div className="form-grid">
            <FormField
              {...bind('complaint_source')}
              label="Complaint source"
              type="select"
              options={COMPLAINT_SOURCES}
              required
            />
            <FormField
              {...bind('customer_name')}
              label="Reporter / organisation"
              placeholder="Organisation or person"
              required
            />
            <FormField
              {...bind('customer_contact')}
              label="Contact details"
              placeholder="Email or phone"
              fullWidth
            />
          </div>
        </section>

        <section className="form-section">
          <div className="form-section__title">
            <span className="form-section__step">2</span> Product and batch
          </div>
          <div className="form-grid">
            <FormField {...bind('product_name')} label="Product name" required />
            <FormField
              {...bind('product_strength_grade')}
              label="Strength / grade"
              placeholder="e.g. 500 mg"
            />
            <FormField {...bind('batch_lot_number')} label="Batch / lot number" required />
            <FormField
              {...bind('quantity_affected')}
              label="Quantity affected"
              type="number"
              required={quantityRequired}
            />
            <FormField {...bind('manufacturing_date')} label="Manufacturing date" type="date" />
            <FormField {...bind('expiry_date')} label="Expiry date" type="date" />
            <FormField
              {...bind('quantity_unit')}
              label="Quantity unit"
              type="select"
              options={QUANTITY_UNITS}
            />
          </div>
        </section>

        <section className="form-section">
          <div className="form-section__title">
            <span className="form-section__step">3</span> What happened
          </div>
          <div className="form-grid">
            <FormField
              {...bind('complaint_type')}
              label="Complaint type"
              type="select"
              options={COMPLAINT_TYPES}
              required
            />
            <FormField {...bind('complaint_date')} label="Date observed" type="date" required />
            <FormField
              {...bind('complaint_details')}
              label="Complaint description"
              type="textarea"
              required
              fullWidth
              placeholder="What was observed, by whom, and in what condition was the product?"
            />
          </div>
        </section>

        <div className="form-actions">
          <button
            type="button"
            className="button button--ghost"
            onClick={() => dispatch(clearIntake())}
            disabled={saving}
          >
            Start over
          </button>
          <button
            type="submit"
            className="button button--primary"
            disabled={saving || !reporterReadyToLodge}
            title={
              !reporterReadyToLodge
                ? 'Answer the assistant’s required follow-up or complete the required facts'
                : undefined
            }
          >
            {saving && <span className="spinner" aria-hidden="true" />}
            {saving ? 'Lodging…' : 'Lodge complaint'}
          </button>
        </div>
      </div>

      <SaveConfirmationDialog />
    </form>
  );
}
