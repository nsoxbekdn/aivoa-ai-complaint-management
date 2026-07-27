/** Human-readable labels for the controlled vocabularies the backend stores. */

export const COMPLAINT_SOURCES: { value: string; label: string }[] = [
  { value: 'customer_email', label: 'Customer email' },
  { value: 'distributor', label: 'Distributor' },
  { value: 'healthcare_professional', label: 'Healthcare professional' },
  { value: 'patient', label: 'Patient' },
  { value: 'regulatory_authority', label: 'Regulatory authority' },
  { value: 'sales_representative', label: 'Sales representative' },
  { value: 'internal', label: 'Internal' },
  { value: 'other', label: 'Other' },
];

export const COMPLAINT_TYPES: { value: string; label: string }[] = [
  { value: 'product_quality_defect', label: 'Product quality defect' },
  { value: 'packaging_defect', label: 'Packaging defect' },
  { value: 'labelling_error', label: 'Labelling error' },
  { value: 'contamination', label: 'Contamination' },
  { value: 'adverse_event', label: 'Adverse event' },
  { value: 'lack_of_efficacy', label: 'Lack of efficacy' },
  { value: 'wrong_product_or_strength', label: 'Wrong product / strength' },
  { value: 'documentation', label: 'Documentation' },
  { value: 'shipping_and_delivery', label: 'Shipping & delivery' },
  { value: 'other', label: 'Other' },
];

export const SEVERITIES: { value: string; label: string }[] = [
  { value: 'minor', label: 'Minor' },
  { value: 'major', label: 'Major' },
  { value: 'critical', label: 'Critical' },
];

export const PRIORITIES: { value: string; label: string }[] = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'urgent', label: 'Urgent' },
];

export const QUANTITY_UNITS: { value: string; label: string }[] = [
  { value: 'tablets', label: 'Tablets' },
  { value: 'capsules', label: 'Capsules' },
  { value: 'bottles', label: 'Bottles' },
  { value: 'vials', label: 'Vials' },
  { value: 'ampoules', label: 'Ampoules' },
  { value: 'blisters', label: 'Blisters' },
  { value: 'cartons', label: 'Cartons' },
  { value: 'packs', label: 'Packs' },
  { value: 'units', label: 'Units' },
  { value: 'kg', label: 'Kilograms' },
  { value: 'litres', label: 'Litres' },
];

export const STATUSES: { value: string; label: string }[] = [
  { value: 'open', label: 'Open' },
  { value: 'under_investigation', label: 'Under investigation' },
  { value: 'closed', label: 'Closed' },
];

const ALL = [
  ...COMPLAINT_SOURCES,
  ...COMPLAINT_TYPES,
  ...SEVERITIES,
  ...PRIORITIES,
  ...QUANTITY_UNITS,
  ...STATUSES,
];

/** Fall back to a de-snake-cased version so an unknown value still reads sensibly. */
export function labelFor(value: string | null | undefined): string {
  if (!value) return '—';
  return ALL.find((option) => option.value === value)?.label ?? value.replace(/_/g, ' ');
}
