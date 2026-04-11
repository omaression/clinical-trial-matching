export type ApiError = {
  detail: string;
  code?: string | null;
  request_id?: string | null;
};

export type TrialSummary = {
  id: string;
  nct_id: string;
  brief_title: string;
  status: string;
  phase?: string | null;
  extraction_status: string;
  ingested_at?: string | null;
};

export type TrialDetail = TrialSummary & {
  official_title?: string | null;
  conditions?: string[] | null;
  interventions?: Record<string, unknown>[] | Record<string, unknown> | null;
  eligibility_text?: string | null;
  eligible_min_age?: string | null;
  eligible_max_age?: string | null;
  eligible_sex?: string | null;
  accepts_healthy?: boolean | null;
  sponsor?: string | null;
  criteria_summary: {
    total: number;
    review_pending: number;
  };
};

export type TrialListResponse = {
  items: TrialSummary[];
  total: number;
  page: number;
  per_page: number;
};

export type IngestRequest = {
  nct_id: string;
};

export type IngestResponse = {
  nct_id: string;
  trial_id: string;
  criteria_count: number;
  review_count: number;
  skipped: boolean;
};

export type SearchIngestRequest = {
  condition?: string;
  status?: string;
  phase?: string;
  page_token?: string;
  limit?: number;
};

export type SearchIngestTrialResponse = {
  nct_id?: string | null;
  trial_id?: string | null;
  criteria_count: number;
  skipped: boolean;
  status: "ingested" | "skipped" | "failed";
  error_message?: string | null;
};

export type SearchIngestResponse = {
  attempted: number;
  returned: number;
  ingested: number;
  skipped: number;
  failed: number;
  total_count?: number | null;
  next_page_token?: string | null;
  trials: SearchIngestTrialResponse[];
};

export type CodedConcept = {
  system: string;
  code: string;
  display?: string | null;
  match_type?: string | null;
};

export type CriterionResponse = {
  id: string;
  trial_id: string;
  type: string;
  category: string;
  parse_status: string;
  original_text: string;
  operator?: string | null;
  value_low?: number | null;
  value_high?: number | null;
  value_text?: string | null;
  unit?: string | null;
  raw_expression?: string | null;
  negated: boolean;
  timeframe_operator?: string | null;
  timeframe_value?: number | null;
  timeframe_unit?: string | null;
  logic_group_id?: string | null;
  logic_operator: string;
  coded_concepts: CodedConcept[];
  confidence: number;
  review_required: boolean;
  review_reason?: string | null;
  review_status?: string | null;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  review_notes?: string | null;
  original_extracted?: Record<string, unknown> | null;
  pipeline_version: string;
  pipeline_run_id: string;
  created_at?: string | null;
};

export type CriteriaListResponse = {
  criteria: CriterionResponse[];
  total: number;
  page: number;
  per_page: number;
};

export type ReviewQueueResponse = {
  items: CriterionResponse[];
  total: number;
  page: number;
  per_page: number;
  breakdown_by_reason: Record<string, number>;
};

export type PipelineStatusResponse = {
  version: string;
  total_runs: number;
  completed: number;
  failed: number;
  total_trials: number;
  total_criteria: number;
  review_pending: number;
};

export type PipelineRunResponse = {
  id: string;
  trial_id: string;
  pipeline_version: string;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  criteria_extracted_count?: number | null;
  review_required_count?: number | null;
  error_message?: string | null;
  diff_summary?: Record<string, unknown> | null;
};

export type PipelineRunListResponse = {
  items: PipelineRunResponse[];
  total: number;
  page: number;
  per_page: number;
};

export type PatientSummary = {
  id: string;
  external_id?: string | null;
  sex?: string | null;
  birth_date?: string | null;
  ecog_status?: number | null;
  is_healthy_volunteer?: boolean | null;
  country?: string | null;
  state?: string | null;
  city?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type PatientFact = {
  id: string;
  description: string;
  coded_concepts: CodedConcept[];
};

export type PatientBiomarker = PatientFact & {
  value_text?: string | null;
};

export type PatientLab = PatientFact & {
  value_numeric?: number | null;
  value_text?: string | null;
  unit?: string | null;
};

export type PatientTherapy = PatientFact & {
  line_of_therapy?: number | null;
  completed?: boolean | null;
};

export type PatientMedication = PatientFact & {
  active: boolean;
};

export type PatientDetail = PatientSummary & {
  conditions: PatientFact[];
  biomarkers: PatientBiomarker[];
  labs: PatientLab[];
  therapies: PatientTherapy[];
  medications: PatientMedication[];
};

export type PatientListResponse = {
  items: PatientSummary[];
  total: number;
  page: number;
  per_page: number;
};

export type MatchResultSummary = {
  id: string;
  match_run_id: string;
  patient_id: string;
  trial_id: string;
  trial_nct_id: string;
  trial_brief_title: string;
  overall_status: "eligible" | "possible" | "ineligible";
  score: number;
  favorable_count: number;
  unfavorable_count: number;
  unknown_count: number;
  requires_review_count: number;
  summary_explanation?: string | null;
  created_at?: string | null;
};

export type MatchCriterionResult = {
  id: string;
  criterion_id?: string | null;
  pipeline_run_id?: string | null;
  source_type: string;
  source_label: string;
  criterion_type: string;
  category: string;
  criterion_text: string;
  outcome: "matched" | "not_matched" | "unknown" | "requires_review" | "not_triggered" | "triggered";
  explanation_text?: string | null;
  explanation_type?: string | null;
  evidence_payload?: Record<string, unknown> | null;
  created_at?: string | null;
};

export type MatchResultDetail = MatchResultSummary & {
  criteria: MatchCriterionResult[];
};

export type MatchRunResponse = {
  id: string;
  patient_id: string;
  status: string;
  total_trials_evaluated: number;
  eligible_trials: number;
  possible_trials: number;
  ineligible_trials: number;
  created_at?: string | null;
  completed_at?: string | null;
  results: MatchResultSummary[];
};

export type MatchResultListResponse = {
  items: MatchResultSummary[];
  total: number;
  page: number;
  per_page: number;
};

export type HealthResponse = {
  status: "healthy" | "degraded";
  pipeline_version: string;
  database: string;
  spacy_model: string;
};

export type ReviewAction = "accept" | "correct" | "reject";

export type ReviewRequest = {
  action: ReviewAction;
  reviewed_by: string;
  review_notes?: string;
  corrected_data?: Record<string, unknown>;
};

export type PatientCreatePayload = {
  external_id?: string;
  sex?: "male" | "female" | "other" | "unknown";
  birth_date?: string;
  ecog_status?: number;
  is_healthy_volunteer?: boolean;
  country?: string;
  state?: string;
  city?: string;
  latitude?: number;
  longitude?: number;
  conditions?: Array<{ description: string; coded_concepts?: CodedConcept[] }>;
  biomarkers?: Array<{ description: string; value_text?: string; coded_concepts?: CodedConcept[] }>;
  labs?: Array<{ description: string; value_numeric?: number; value_text?: string; unit?: string; coded_concepts?: CodedConcept[] }>;
  therapies?: Array<{ description: string; line_of_therapy?: number; completed?: boolean; coded_concepts?: CodedConcept[] }>;
  medications?: Array<{ description: string; active?: boolean; coded_concepts?: CodedConcept[] }>;
};
