from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IngestRequest(APIModel):
    nct_id: str = Field(min_length=4, max_length=32)


class SearchIngestRequest(APIModel):
    condition: str | None = None
    status: str | None = None
    phase: str | None = None
    limit: int = Field(default=25, ge=1, le=100)


class ReviewRequest(APIModel):
    action: Literal["accept", "correct", "reject"]
    reviewed_by: str = Field(min_length=1)
    review_notes: str | None = None
    corrected_data: dict[str, Any] | None = None

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
    nct_id: str
    trial_id: UUID
    criteria_count: int
    skipped: bool


class SearchIngestResponse(APIModel):
    ingested: int
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


class ErrorResponse(APIModel):
    detail: str
    code: str | None = None
