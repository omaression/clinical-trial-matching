from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IngestRequest(APIModel):
    nct_id: str = Field(min_length=11, max_length=11, pattern=r"^NCT\d{8}$")


class SearchIngestRequest(APIModel):
    condition: str | None = None
    status: str | None = None
    phase: str | None = None
    page_token: str | None = None
    limit: int = Field(default=25, ge=1, le=100)


class CodedConceptUpdate(APIModel):
    system: str = Field(min_length=1)
    code: str = Field(min_length=1)
    display: str | None = None
    match_type: str | None = None


class CriterionCorrectionData(APIModel):
    type: Literal["inclusion", "exclusion"] | None = None
    category: str | None = None
    parse_status: Literal["parsed", "partial", "unparsed"] | None = None
    operator: str | None = None
    value_low: float | None = None
    value_high: float | None = None
    value_text: str | None = None
    unit: str | None = None
    raw_expression: str | None = None
    negated: bool | None = None
    timeframe_operator: str | None = None
    timeframe_value: float | None = None
    timeframe_unit: str | None = None
    logic_group_id: UUID | None = None
    logic_operator: Literal["AND", "OR"] | None = None
    coded_concepts: list[CodedConceptUpdate] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_has_fields(self):
        if not self.model_fields_set:
            raise ValueError("corrected_data must include at least one editable field")
        return self


class ReviewRequest(APIModel):
    action: Literal["accept", "correct", "reject"]
    reviewed_by: str = Field(min_length=1)
    review_notes: str | None = None
    corrected_data: CriterionCorrectionData | None = None

    @model_validator(mode="after")
    def validate_correction_payload(self):
        if self.action == "correct" and not self.corrected_data:
            raise ValueError("corrected_data is required when action='correct'")
        if self.action != "correct" and self.corrected_data is not None:
            raise ValueError("corrected_data is only allowed when action='correct'")
        return self


class IngestResponse(APIModel):
    nct_id: str
    trial_id: UUID
    criteria_count: int
    review_count: int
    skipped: bool


class SearchIngestTrialResponse(APIModel):
    nct_id: str | None = None
    trial_id: UUID | None = None
    criteria_count: int
    skipped: bool
    status: Literal["ingested", "skipped", "failed"]
    error_message: str | None = None


class SearchIngestResponse(APIModel):
    attempted: int
    returned: int
    ingested: int
    skipped: int
    failed: int
    total_count: int | None = None
    next_page_token: str | None = None
    trials: list[SearchIngestTrialResponse]


class CriteriaSummary(APIModel):
    total: int
    review_pending: int


class TrialSummary(APIModel):
    id: UUID
    nct_id: str
    brief_title: str
    status: str
    phase: str | None = None
    extraction_status: str
    ingested_at: datetime | None = None


class TrialDetail(TrialSummary):
    official_title: str | None = None
    conditions: list[str] | None = None
    interventions: list[dict[str, Any]] | dict[str, Any] | None = None
    eligibility_text: str | None = None
    eligible_min_age: str | None = None
    eligible_max_age: str | None = None
    eligible_sex: str | None = None
    accepts_healthy: bool | None = None
    sponsor: str | None = None
    criteria_summary: CriteriaSummary


class TrialListResponse(APIModel):
    items: list[TrialSummary]
    total: int
    page: int
    per_page: int


class CodedConceptResponse(APIModel):
    system: str
    code: str
    display: str | None = None
    match_type: str | None = None


class CriterionResponse(APIModel):
    id: UUID
    trial_id: UUID
    type: str
    category: str
    parse_status: str
    original_text: str
    operator: str | None = None
    value_low: float | None = None
    value_high: float | None = None
    value_text: str | None = None
    unit: str | None = None
    raw_expression: str | None = None
    negated: bool
    timeframe_operator: str | None = None
    timeframe_value: float | None = None
    timeframe_unit: str | None = None
    logic_group_id: UUID | None = None
    logic_operator: str
    coded_concepts: list[CodedConceptResponse] = Field(default_factory=list)
    confidence: float
    review_required: bool
    review_reason: str | None = None
    review_status: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    original_extracted: dict[str, Any] | None = None
    pipeline_version: str
    pipeline_run_id: UUID
    created_at: datetime | None = None


class CriteriaListResponse(APIModel):
    criteria: list[CriterionResponse]
    total: int
    page: int
    per_page: int


class ReviewQueueResponse(APIModel):
    items: list[CriterionResponse]
    total: int
    page: int
    per_page: int
    breakdown_by_reason: dict[str, int]


class PipelineStatusResponse(APIModel):
    version: str
    total_runs: int
    completed: int
    failed: int
    total_trials: int
    total_criteria: int
    review_pending: int


class PipelineRunResponse(APIModel):
    id: UUID
    trial_id: UUID
    pipeline_version: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    criteria_extracted_count: int | None = None
    review_required_count: int | None = None
    error_message: str | None = None
    diff_summary: dict[str, Any] | None = None


class PipelineRunListResponse(APIModel):
    items: list[PipelineRunResponse]
    total: int
    page: int
    per_page: int


class ReExtractResponse(APIModel):
    trial_id: UUID
    criteria_count: int
    review_count: int
    diff_summary: dict[str, Any] | None = None


class HealthResponse(APIModel):
    status: Literal["healthy", "degraded"]
    pipeline_version: str
    database: str
    spacy_model: str


class PatientConditionInput(APIModel):
    description: str = Field(min_length=1)
    coded_concepts: list[CodedConceptUpdate] = Field(default_factory=list)


class PatientBiomarkerInput(APIModel):
    description: str = Field(min_length=1)
    coded_concepts: list[CodedConceptUpdate] = Field(default_factory=list)
    value_text: str | None = None


class PatientLabInput(APIModel):
    description: str = Field(min_length=1)
    coded_concepts: list[CodedConceptUpdate] = Field(default_factory=list)
    value_numeric: float | None = None
    value_text: str | None = None
    unit: str | None = None


class PatientTherapyInput(APIModel):
    description: str = Field(min_length=1)
    coded_concepts: list[CodedConceptUpdate] = Field(default_factory=list)
    line_of_therapy: int | None = Field(default=None, ge=0)
    completed: bool | None = None


class PatientMedicationInput(APIModel):
    description: str = Field(min_length=1)
    coded_concepts: list[CodedConceptUpdate] = Field(default_factory=list)
    active: bool = True


class PatientCreateRequest(APIModel):
    external_id: str | None = None
    sex: Literal["male", "female", "other", "unknown"] | None = None
    birth_date: date | None = None
    ecog_status: int | None = Field(default=None, ge=0, le=5)
    is_healthy_volunteer: bool | None = None
    can_consent: bool | None = None
    protocol_compliant: bool | None = None
    claustrophobic: bool | None = None
    motion_intolerant: bool | None = None
    pregnant: bool | None = None
    mr_device_present: bool | None = None
    country: str | None = None
    state: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    conditions: list[PatientConditionInput] = Field(default_factory=list)
    biomarkers: list[PatientBiomarkerInput] = Field(default_factory=list)
    labs: list[PatientLabInput] = Field(default_factory=list)
    therapies: list[PatientTherapyInput] = Field(default_factory=list)
    medications: list[PatientMedicationInput] = Field(default_factory=list)


class PatientUpdateRequest(APIModel):
    external_id: str | None = None
    sex: Literal["male", "female", "other", "unknown"] | None = None
    birth_date: date | None = None
    ecog_status: int | None = Field(default=None, ge=0, le=5)
    is_healthy_volunteer: bool | None = None
    can_consent: bool | None = None
    protocol_compliant: bool | None = None
    claustrophobic: bool | None = None
    motion_intolerant: bool | None = None
    pregnant: bool | None = None
    mr_device_present: bool | None = None
    country: str | None = None
    state: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    conditions: list[PatientConditionInput] | None = None
    biomarkers: list[PatientBiomarkerInput] | None = None
    labs: list[PatientLabInput] | None = None
    therapies: list[PatientTherapyInput] | None = None
    medications: list[PatientMedicationInput] | None = None

    @model_validator(mode="after")
    def validate_has_fields(self):
        if not self.model_fields_set:
            raise ValueError("patient update must include at least one field")
        return self


class PatientConditionResponse(APIModel):
    id: UUID
    description: str
    coded_concepts: list["CodedConceptResponse"] = Field(default_factory=list)


class PatientBiomarkerResponse(APIModel):
    id: UUID
    description: str
    coded_concepts: list["CodedConceptResponse"] = Field(default_factory=list)
    value_text: str | None = None


class PatientLabResponse(APIModel):
    id: UUID
    description: str
    coded_concepts: list["CodedConceptResponse"] = Field(default_factory=list)
    value_numeric: float | None = None
    value_text: str | None = None
    unit: str | None = None


class PatientTherapyResponse(APIModel):
    id: UUID
    description: str
    coded_concepts: list["CodedConceptResponse"] = Field(default_factory=list)
    line_of_therapy: int | None = None
    completed: bool | None = None


class PatientMedicationResponse(APIModel):
    id: UUID
    description: str
    coded_concepts: list["CodedConceptResponse"] = Field(default_factory=list)
    active: bool


class PatientSummary(APIModel):
    id: UUID
    external_id: str | None = None
    sex: str | None = None
    birth_date: date | None = None
    ecog_status: int | None = None
    is_healthy_volunteer: bool | None = None
    can_consent: bool | None = None
    protocol_compliant: bool | None = None
    claustrophobic: bool | None = None
    motion_intolerant: bool | None = None
    pregnant: bool | None = None
    mr_device_present: bool | None = None
    country: str | None = None
    state: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PatientDetail(PatientSummary):
    conditions: list[PatientConditionResponse] = Field(default_factory=list)
    biomarkers: list[PatientBiomarkerResponse] = Field(default_factory=list)
    labs: list[PatientLabResponse] = Field(default_factory=list)
    therapies: list[PatientTherapyResponse] = Field(default_factory=list)
    medications: list[PatientMedicationResponse] = Field(default_factory=list)


class PatientListResponse(APIModel):
    items: list[PatientSummary]
    total: int
    page: int
    per_page: int


CriterionMatchOutcome = Literal[
    "matched",
    "not_matched",
    "unknown",
    "requires_review",
    "not_triggered",
    "triggered",
]


class MatchCriterionResultResponse(APIModel):
    id: UUID
    criterion_id: UUID | None = None
    pipeline_run_id: UUID | None = None
    source_type: str
    source_label: str
    criterion_type: str
    category: str
    criterion_text: str
    outcome: CriterionMatchOutcome
    explanation_text: str | None = None
    explanation_type: str | None = None
    evidence_payload: dict[str, Any] | None = None
    created_at: datetime | None = None


class MatchResultSummary(APIModel):
    id: UUID
    match_run_id: UUID
    patient_id: UUID
    trial_id: UUID
    trial_nct_id: str
    trial_brief_title: str
    overall_status: Literal["eligible", "possible", "ineligible"]
    score: float
    favorable_count: int
    unfavorable_count: int
    unknown_count: int
    requires_review_count: int
    summary_explanation: str | None = None
    created_at: datetime | None = None


class MatchResultDetail(MatchResultSummary):
    criteria: list[MatchCriterionResultResponse] = Field(default_factory=list)


class MatchRunResponse(APIModel):
    id: UUID
    patient_id: UUID
    status: str
    total_trials_evaluated: int
    eligible_trials: int
    possible_trials: int
    ineligible_trials: int
    created_at: datetime | None = None
    completed_at: datetime | None = None
    results: list[MatchResultSummary] = Field(default_factory=list)


class MatchResultListResponse(APIModel):
    items: list[MatchResultSummary]
    total: int
    page: int
    per_page: int


class ErrorResponse(APIModel):
    detail: str
    code: str | None = None
    request_id: str | None = None


PatientConditionResponse.model_rebuild()
PatientBiomarkerResponse.model_rebuild()
PatientLabResponse.model_rebuild()
PatientTherapyResponse.model_rebuild()
PatientMedicationResponse.model_rebuild()
