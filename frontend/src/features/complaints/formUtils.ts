/** Pure helpers shared by the slice and the form: no React, no Redux, easy to reason about. */

import type {
  Complaint,
  ComplaintAnalysisResponse,
  ComplaintFormData,
  ComplaintFormField,
  FieldSourceMap,
} from '../../types/complaint';

export const EMPTY_FORM: ComplaintFormData = {
  complaint_source: '',
  customer_name: '',
  customer_contact: '',
  product_name: '',
  product_strength_grade: '',
  batch_lot_number: '',
  manufacturing_date: '',
  expiry_date: '',
  quantity_affected: '',
  quantity_unit: '',
  complaint_type: '',
  complaint_date: '',
  complaint_details: '',
  initial_severity: '',
  priority: '',
};

/** Reporter-owned facts required before final QA analysis and lodging. */
export const REQUIRED_FIELDS: ComplaintFormField[] = [
  'complaint_source',
  'product_name',
  'complaint_type',
  'complaint_date',
  'complaint_details',
];

const REPORTER_CRITICAL_FIELDS: ComplaintFormField[] = [
  'complaint_source',
  'customer_name',
  'product_name',
  'batch_lot_number',
  'complaint_date',
  'complaint_details',
];

const QUANTITY_CRITICAL_TYPES = new Set([
  'product_quality_defect',
  'packaging_defect',
  'contamination',
  'wrong_product_or_strength',
  'labelling_error',
]);

const REQUIRED_LABELS: Record<string, string> = {
  complaint_source: 'Complaint source is required',
  product_name: 'Product name is required',
  complaint_type: 'Complaint type is required',
  complaint_date: 'Complaint date is required',
  complaint_details: 'Complaint details are required',
};

/** Map the AI result onto the form, and record which fields the AI filled. */
export function formFromAnalysis(analysis: ComplaintAnalysisResponse): {
  form: ComplaintFormData;
  sources: FieldSourceMap;
} {
  const fields = analysis.extracted_fields;
  const form = { ...EMPTY_FORM };
  const sources: FieldSourceMap = {};

  (Object.keys(EMPTY_FORM) as ComplaintFormField[]).forEach((key) => {
    const value = fields[key as keyof typeof fields];
    if (value !== null && value !== undefined && value !== '') {
      form[key] = String(value);
      sources[key] = 'ai';
    }
  });

  return { form, sources };
}

export function formFromComplaint(complaint: Complaint): ComplaintFormData {
  const form = { ...EMPTY_FORM };
  (Object.keys(EMPTY_FORM) as ComplaintFormField[]).forEach((key) => {
    const value = complaint[key as keyof Complaint];
    if (value !== null && value !== undefined) form[key] = String(value);
  });
  return form;
}

export function validateForm(form: ComplaintFormData): Partial<Record<ComplaintFormField, string>> {
  const errors: Partial<Record<ComplaintFormField, string>> = {};

  REQUIRED_FIELDS.forEach((field) => {
    if (!form[field].trim()) errors[field] = REQUIRED_LABELS[field];
  });

  if (form.complaint_details.trim() && form.complaint_details.trim().length < 10) {
    errors.complaint_details = 'Please describe the complaint in at least 10 characters';
  }
  if (form.complaint_date && form.complaint_date > new Date().toISOString().slice(0, 10)) {
    errors.complaint_date = 'The complaint date cannot be in the future';
  }
  if (form.manufacturing_date && form.expiry_date && form.expiry_date < form.manufacturing_date) {
    errors.expiry_date = 'Expiry cannot be earlier than the manufacturing date';
  }
  if (form.quantity_affected && Number.isNaN(Number(form.quantity_affected))) {
    errors.quantity_affected = 'Quantity must be a number';
  }
  if (form.quantity_affected && Number(form.quantity_affected) <= 0) {
    errors.quantity_affected = 'Quantity must be greater than zero';
  }

  return errors;
}

/** Mirror the backend completeness gate so a direct form correction can enable lodging too. */
export function isReporterReadyToLodge(form: ComplaintFormData): boolean {
  const hasCoreFields = REPORTER_CRITICAL_FIELDS.every((field) => form[field].trim());
  const needsQuantity = QUANTITY_CRITICAL_TYPES.has(form.complaint_type);
  return Boolean(hasCoreFields && (!needsQuantity || form.quantity_affected.trim()));
}

/** Whether the reporter has already entered any factual complaint information manually. */
export function hasReporterFacts(form: ComplaintFormData): boolean {
  return (Object.keys(form) as ComplaintFormField[]).some(
    (field) =>
      field !== 'initial_severity' &&
      field !== 'priority' &&
      Boolean(form[field].trim()),
  );
}

/** Build the atomic finalize request. The server regenerates QA output from these final facts. */
export function buildCreatePayload(
  form: ComplaintFormData,
  analysis: ComplaintAnalysisResponse | null,
  intakeTranscript: { role: 'user' | 'assistant'; text: string }[] = [],
): Record<string, unknown> {
  const value = (field: ComplaintFormField) => (form[field].trim() ? form[field].trim() : null);

  const fields = {
    complaint_source: value('complaint_source'),
    customer_name: value('customer_name'),
    customer_contact: value('customer_contact'),
    product_name: value('product_name'),
    product_strength_grade: value('product_strength_grade'),
    batch_lot_number: value('batch_lot_number'),
    manufacturing_date: value('manufacturing_date'),
    expiry_date: value('expiry_date'),
    quantity_affected: form.quantity_affected.trim() ? Number(form.quantity_affected) : null,
    quantity_unit: value('quantity_unit'),
    complaint_type: value('complaint_type'),
    complaint_date: value('complaint_date'),
    complaint_details: value('complaint_details'),
    initial_severity: value('initial_severity'),
    priority: value('priority'),
  };
  return {
    fields,
    original_text: analysis?.original_text ?? null,
    input_filename: analysis?.input_filename ?? null,
    intake_transcript: intakeTranscript,
    source_documents: analysis?.source_documents ?? [],
    warnings: analysis?.warnings ?? [],
  };
}
