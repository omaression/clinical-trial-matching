from pydantic import BaseModel


class IngestRequest(BaseModel):
    nct_id: str


class SearchIngestRequest(BaseModel):
    condition: str | None = None
    status: str | None = None
    phase: str | None = None
    limit: int = 25


class ReviewRequest(BaseModel):
    action: str  # accept, correct, reject
    reviewed_by: str
    review_notes: str | None = None
    corrected_data: dict | None = None


class ErrorResponse(BaseModel):
    detail: str
    code: str
