/** Types mirroring the backend Pydantic schemas. */

export type ComplaintSource =
  | 'customer_email'
  | 'distributor'
  | 'healthcare_professional'
  | 'patient'
  | 'regulatory_authority'
  | 'sales_representative'
  | 'internal'
  | 'other';

export type ComplaintType =
  | 'product_quality_defect'
  | 'packaging_defect'
  | 'labelling_error'
  | 'contamination'
  | 'adverse_event'
  | 'lack_of_efficacy'
  | 'wrong_product_or_strength'
  | 'documentation'
  | 'shipping_and_delivery'
  | 'other';

export type Severity = 'minor' | 'major' | 'critical' | 'unknown';
export type Priority = 'low' | 'medium' | 'high' | 'urgent';
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical' | 'unknown';
export type ComplaintStatus = 'open' | 'under_investigation' | 'closed';

/** The editable form. Everything is a string so inputs stay controlled; conversion to
 *  numbers/dates happens once, when the payload is built. */
export interface ComplaintFormData {
  complaint_source: string;
  customer_name: string;
  customer_contact: string;
  product_name: string;
  product_strength_grade: string;
  batch_lot_number: string;
  manufacturing_date: string;
  expiry_date: string;
  quantity_affected: string;
  quantity_unit: string;
  complaint_type: string;
  complaint_date: string;
  complaint_details: string;
  initial_severity: string;
  priority: string;
}

export type ComplaintFormField = keyof ComplaintFormData;

export interface ExtractedComplaintFields {
  complaint_source: ComplaintSource | null;
  customer_name: string | null;
  customer_contact: string | null;
  product_name: string | null;
  product_strength_grade: string | null;
  batch_lot_number: string | null;
  manufacturing_date: string | null;
  expiry_date: string | null;
  quantity_affected: number | null;
  quantity_unit: string | null;
  complaint_type: ComplaintType | null;
  complaint_date: string | null;
  complaint_details: string | null;
  initial_severity: Severity | null;
  priority: Priority | null;
}

export interface CompletenessAssessment {
  score: number;
  is_complete: boolean;
  missing_critical_fields: string[];
  missing_optional_fields: string[];
  follow_up_questions: string[];
}

export interface RiskAssessment {
  risk_level: RiskLevel;
  severity: Severity;
  priority: Priority;
  patient_safety_concern: boolean;
  product_quality_concern: boolean;
  rationale: string;
  confidence: number;
}

export interface ComplaintRecommendations {
  possible_root_causes: string[];
  initial_investigation_steps: string[];
  preliminary_capa_suggestions: string[];
}

export interface DuplicateCandidate {
  complaint_id: number;
  complaint_number: string;
  product_name: string | null;
  batch_lot_number: string | null;
  complaint_type: string | null;
  similarity: number;
  reason: string;
}

export interface SourceDocument {
  filename: string;
  media_type: string;
  extraction_method: 'native_text' | 'groq_vision' | 'mixed';
  text: string;
  page_count: number;
  ocr_used: boolean;
}

export interface ComplaintAnalysisResponse {
  extracted_fields: ExtractedComplaintFields;
  completeness: CompletenessAssessment;
  risk_assessment: RiskAssessment;
  summary: string;
  recommendations: ComplaintRecommendations;
  warnings: string[];
  duplicate_candidates: DuplicateCandidate[];
  original_text: string;
  input_filename: string | null;
  source_documents: SourceDocument[];
  disclaimer: string;
}

export interface IntakeChatResponse {
  assistant_message: string;
  updated_fields: ExtractedComplaintFields;
  completeness: CompletenessAssessment;
  changed_fields: string[];
  ready_to_lodge: boolean;
  warnings: string[];
  source_document: SourceDocument | null;
}

export interface Complaint {
  id: number;
  complaint_number: string;
  complaint_source: ComplaintSource | null;
  customer_name: string | null;
  customer_contact: string | null;
  product_name: string | null;
  product_strength_grade: string | null;
  batch_lot_number: string | null;
  manufacturing_date: string | null;
  expiry_date: string | null;
  quantity_affected: number | null;
  quantity_unit: string | null;
  complaint_type: ComplaintType | null;
  complaint_date: string | null;
  complaint_details: string | null;
  initial_severity: Severity | null;
  priority: Priority | null;
  risk_level: RiskLevel | null;
  risk_rationale: string | null;
  risk_confidence: number | null;
  patient_safety_concern: boolean | null;
  product_quality_concern: boolean | null;
  ai_summary: string | null;
  completeness_score: number | null;
  missing_fields: string[] | null;
  root_cause_recommendations: string[] | null;
  initial_investigation_steps: string[] | null;
  capa_recommendations: string[] | null;
  duplicate_candidates: DuplicateCandidate[] | null;
  analysis_warnings: string[] | null;
  original_text: string | null;
  input_filename: string | null;
  intake_transcript: { role: 'user' | 'assistant'; text: string }[] | null;
  source_documents: SourceDocument[] | null;
  status: ComplaintStatus;
  created_at: string;
  updated_at: string;
}

export interface ComplaintListResponse {
  items: Complaint[];
  total: number;
  limit: number;
  offset: number;
}

/** Where a form value came from — drives the subtle "AI-populated" highlight. */
export type FieldSource = 'ai' | 'user';
export type FieldSourceMap = Partial<Record<ComplaintFormField, FieldSource>>;
