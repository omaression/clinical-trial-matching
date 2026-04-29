from collections import Counter
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Query as SQLAlchemyQuery
from sqlalchemy.orm import Session

from app.api.dependencies import add_request_log_context, rate_limit_dependency, require_api_key
from app.api.errors import api_exception
from app.api.openapi import (
    COMMON_ERROR_RESPONSES,
    PROTECTED_OPERATIONAL_RESPONSES,
    PROTECTED_READ_RESPONSES,
    PROTECTED_REVIEW_RESPONSES,
    READ_ERROR_RESPONSES,
    SEARCH_OPERATIONAL_RESPONSES,
)
from app.api.schemas import (
    CriteriaListResponse,
    CriteriaSummary,
    CriterionFHIRProjectionListResponse,
    CriterionFHIRProjectionResponse,
    CriterionResponse,
    IngestRequest,
    IngestResponse,
    MatchReviewQueueItemResponse,
    MatchReviewQueueResponse,
    PipelineCoverageResponse,
    PipelineRunListResponse,
    PipelineRunResponse,
    PipelineStatusResponse,
    ReExtractResponse,
    ReviewQueueResponse,
    ReviewRequest,
    SearchIngestRequest,
    SearchIngestResponse,
    SearchIngestTrialResponse,
    TrialDetail,
    TrialListResponse,
    TrialSummary,
)
from app.api.state import criterion_state_from_extracted
from app.config import settings
from app.db.session import get_db
from app.fhir.criterion_projection import CriterionProjectionMapper
from app.fhir.mapper import FHIRMapper
from app.fhir.models import ResearchStudy
from app.ingestion.service import ExternalServiceValidationError, IngestionService
from app.models.database import ExtractedCriterion, FHIRResearchStudy, MatchReviewItem, MatchRun, PipelineRun, Trial
from app.reporting.coverage_dashboard import build_pipeline_coverage_payload
from app.time_utils import utc_now

router = APIRouter()
fhir_mapper = FHIRMapper()
ingest_rate_limit = rate_limit_dependency(
    "ingest",
    limit_setting="ingest_rate_limit_requests",
    window_setting="ingest_rate_limit_window_seconds",
)
search_ingest_rate_limit = rate_limit_dependency(
    "search_ingest",
    limit_setting="search_ingest_rate_limit_requests",
    window_setting="search_ingest_rate_limit_window_seconds",
)
reextract_rate_limit = rate_limit_dependency(
    "reextract",
    limit_setting="reextract_rate_limit_requests",
    window_setting="reextract_rate_limit_window_seconds",
)

def _get_ingestion_service(request: Request, db: Session = Depends(get_db)) -> IngestionService:
    pipeline = getattr(request.app.state, "extraction_pipeline", None)
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Extraction pipeline unavailable")
    return IngestionService(db, pipeline=pipeline)


@router.post(
    "/trials/ingest",
    status_code=201,
    response_model=IngestResponse,
    responses=PROTECTED_OPERATIONAL_RESPONSES,
)
def ingest_trial(
    payload: IngestRequest,
    request: Request,
    _: str = Depends(ingest_rate_limit),
    service: IngestionService = Depends(_get_ingestion_service),
):
    add_request_log_context(request, nct_id=payload.nct_id)
    result = service.ingest(payload.nct_id)
    return IngestResponse(
        nct_id=result.trial.nct_id,
        trial_id=result.trial.id,
        criteria_count=result.criteria_count,
        review_count=result.review_count,
        skipped=result.skipped,
    )


@router.post(
    "/trials/search-ingest",
    status_code=201,
    response_model=SearchIngestResponse,
    responses=SEARCH_OPERATIONAL_RESPONSES,
)
def search_and_ingest(
    payload: SearchIngestRequest,
    request: Request,
    _: str = Depends(search_ingest_rate_limit),
    service: IngestionService = Depends(_get_ingestion_service),
):
    add_request_log_context(request)
    try:
        results = service.search_and_ingest(
            condition=payload.condition,
            status=payload.status,
            phase=payload.phase,
            limit=payload.limit,
            page_token=payload.page_token,
        )
    except ExternalServiceValidationError as exc:
        raise api_exception(400, exc.detail, code="external_validation_error") from exc
    if isinstance(results, list):
        batch_results = results
        returned = len(results)
        total_count = None
        next_page_token = None
    else:
        batch_results = results.results
        returned = results.returned_count
        total_count = results.total_count
        next_page_token = results.next_page_token

    ingested = sum(1 for result in batch_results if result.trial and not result.skipped and not result.error_message)
    skipped = sum(1 for result in batch_results if result.skipped and not result.error_message)
    failed = sum(1 for result in batch_results if result.error_message)
    return SearchIngestResponse(
        attempted=len(batch_results),
        returned=returned,
        ingested=ingested,
        skipped=skipped,
        failed=failed,
        total_count=total_count,
        next_page_token=next_page_token,
        trials=[
            SearchIngestTrialResponse(
                nct_id=result.nct_id,
                trial_id=result.trial.id if result.trial else None,
                criteria_count=result.criteria_count,
                skipped=result.skipped,
                status=(
                    "failed"
                    if result.error_message
                    else "skipped" if result.skipped else "ingested"
                ),
                error_message=result.error_message,
            )
            for result in batch_results
        ],
    )


@router.get("/trials", response_model=TrialListResponse, responses=COMMON_ERROR_RESPONSES)
def list_trials(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = None,
    condition: str | None = None,
    phase: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Trial)
    if status:
        query = query.filter(Trial.status == status)
    if condition:
        query = query.filter(Trial.conditions.any(condition))
    if phase:
        query = query.filter(Trial.phase.ilike(f"%{phase}%"))

    total = query.count()
    trials = (
        query.order_by(Trial.ingested_at.desc(), Trial.nct_id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return TrialListResponse(
        items=[_trial_summary(trial) for trial in trials],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/trials/{trial_id}", response_model=TrialDetail, responses=READ_ERROR_RESPONSES)
def get_trial(trial_id: UUID, request: Request, db: Session = Depends(get_db)):
    add_request_log_context(request, trial_id=trial_id)
    trial = _get_trial_or_404(trial_id, db)
    return _trial_detail(trial, db)


@router.get("/trials/nct/{nct_id}", response_model=TrialDetail, responses=READ_ERROR_RESPONSES)
def get_trial_by_nct(nct_id: str, request: Request, db: Session = Depends(get_db)):
    add_request_log_context(request, nct_id=nct_id)
    trial = db.query(Trial).filter(Trial.nct_id == nct_id).first()
    if not trial:
        raise HTTPException(status_code=404, detail="Trial not found")
    return _trial_detail(trial, db)


@router.get(
    "/trials/{trial_id}/criteria",
    response_model=CriteriaListResponse,
    responses=READ_ERROR_RESPONSES,
)
def get_trial_criteria(
    trial_id: UUID,
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    type: str | None = None,
    category: str | None = None,
    review_required: bool | None = None,
    db: Session = Depends(get_db),
):
    add_request_log_context(request, trial_id=trial_id)
    _get_trial_or_404(trial_id, db)
    query = _latest_trial_criteria_query(trial_id, db)
    if type:
        query = query.filter(ExtractedCriterion.type == type)
    if category:
        query = query.filter(ExtractedCriterion.category == category)
    if review_required is not None:
        query = query.filter(ExtractedCriterion.review_required == review_required)

    total = query.count()
    criteria = (
        query.order_by(ExtractedCriterion.created_at.asc(), ExtractedCriterion.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return CriteriaListResponse(
        criteria=[_criterion_detail(c) for c in criteria],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/criteria/{criterion_id}", response_model=CriterionResponse, responses=READ_ERROR_RESPONSES)
def get_criterion(criterion_id: UUID, request: Request, db: Session = Depends(get_db)):
    criterion = db.query(ExtractedCriterion).filter(ExtractedCriterion.id == criterion_id).first()
    if not criterion:
        raise HTTPException(status_code=404, detail="Criterion not found")
    add_request_log_context(
        request,
        trial_id=criterion.trial_id,
        pipeline_run_id=criterion.pipeline_run_id,
    )
    return _criterion_detail(criterion)


@router.get(
    "/criteria/{criterion_id}/fhir-projections",
    response_model=CriterionFHIRProjectionListResponse,
    responses=READ_ERROR_RESPONSES,
)
def get_criterion_fhir_projections(criterion_id: UUID, request: Request, db: Session = Depends(get_db)):
    criterion = db.query(ExtractedCriterion).filter(ExtractedCriterion.id == criterion_id).first()
    if not criterion:
        raise HTTPException(status_code=404, detail="Criterion not found")
    add_request_log_context(
        request,
        trial_id=criterion.trial_id,
        pipeline_run_id=criterion.pipeline_run_id,
    )
    mapper = CriterionProjectionMapper(db)
    projections = mapper.project_criterion(criterion)
    return _projection_list_response(projections)


@router.get("/trials/{trial_id}/fhir", responses=READ_ERROR_RESPONSES)
def get_trial_fhir(trial_id: UUID, request: Request, db: Session = Depends(get_db)):
    add_request_log_context(request, trial_id=trial_id)
    trial = _get_trial_or_404(trial_id, db)
    latest_run = _latest_completed_run(trial.id, db)

    resource_payload: dict[str, Any] | None = None
    if latest_run:
        cached = (
            db.query(FHIRResearchStudy)
            .filter(
                FHIRResearchStudy.trial_id == trial.id,
                FHIRResearchStudy.pipeline_run_id == latest_run.id,
            )
            .order_by(FHIRResearchStudy.updated_at.desc().nullslast(), FHIRResearchStudy.created_at.desc())
            .first()
        )
        if cached:
            resource_payload = cached.resource

    if resource_payload is None:
        criteria = _latest_trial_criteria_query(trial.id, db).order_by(ExtractedCriterion.created_at.asc()).all()
        resource_payload = fhir_mapper.to_research_study(trial, criteria)

    resource = ResearchStudy.model_validate(resource_payload)
    return Response(
        content=resource.model_dump_json(exclude_none=True),
        media_type="application/fhir+json",
    )


@router.get(
    "/trials/{trial_id}/fhir-projections",
    response_model=CriterionFHIRProjectionListResponse,
    responses=READ_ERROR_RESPONSES,
)
def get_trial_fhir_projections(trial_id: UUID, request: Request, db: Session = Depends(get_db)):
    add_request_log_context(request, trial_id=trial_id)
    _get_trial_or_404(trial_id, db)
    criteria = _latest_trial_criteria_query(trial_id, db).order_by(ExtractedCriterion.created_at.asc()).all()
    mapper = CriterionProjectionMapper(db)
    projections = []
    for criterion in criteria:
        projections.extend(mapper.project_criterion(criterion))
    return _projection_list_response(projections)


@router.get("/review", response_model=ReviewQueueResponse, responses=PROTECTED_READ_RESPONSES)
def get_review_queue(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    reason: str | None = None,
    trial_id: UUID | None = None,
    _: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    add_request_log_context(request, trial_id=trial_id)
    latest_run_ids = _latest_completed_run_ids_subquery()
    query = db.query(ExtractedCriterion).filter(
        ExtractedCriterion.pipeline_run_id.in_(latest_run_ids),
        ExtractedCriterion.review_required == True,  # noqa: E712
        ExtractedCriterion.review_status == "pending",
    )
    if reason:
        query = query.filter(ExtractedCriterion.review_reason == reason)
    if trial_id:
        query = query.filter(ExtractedCriterion.trial_id == trial_id)

    total = query.count()
    criteria = (
        query.order_by(ExtractedCriterion.created_at.asc(), ExtractedCriterion.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    breakdown_query = (
        db.query(ExtractedCriterion.review_reason, func.count(ExtractedCriterion.id))
        .filter(
            ExtractedCriterion.pipeline_run_id.in_(latest_run_ids),
            ExtractedCriterion.review_required == True,  # noqa: E712
            ExtractedCriterion.review_status == "pending",
        )
    )
    if reason:
        breakdown_query = breakdown_query.filter(ExtractedCriterion.review_reason == reason)
    if trial_id:
        breakdown_query = breakdown_query.filter(ExtractedCriterion.trial_id == trial_id)
    breakdown_by_reason = {
        (row[0] or "unknown"): row[1]
        for row in breakdown_query.group_by(ExtractedCriterion.review_reason).all()
    }

    return ReviewQueueResponse(
        items=[_criterion_detail(c) for c in criteria],
        total=total,
        page=page,
        per_page=per_page,
        breakdown_by_reason=breakdown_by_reason,
    )


@router.get("/review/matches", response_model=MatchReviewQueueResponse, responses=PROTECTED_READ_RESPONSES)
def get_match_review_queue(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    reason: str | None = None,
    trial_id: UUID | None = None,
    patient_id: UUID | None = None,
    _: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    add_request_log_context(request, trial_id=trial_id)
    latest_runs = _latest_completed_match_run_ids_subquery().subquery()
    query = (
        db.query(MatchReviewItem, Trial)
        .join(Trial, Trial.id == MatchReviewItem.trial_id)
        .filter(MatchReviewItem.match_run_id.in_(select(latest_runs.c.id)))
    )
    if reason:
        query = query.filter(MatchReviewItem.reason_code == reason)
    if trial_id:
        query = query.filter(MatchReviewItem.trial_id == trial_id)
    if patient_id:
        query = query.filter(MatchReviewItem.patient_id == patient_id)

    total = query.count()
    rows = (
        query.order_by(MatchReviewItem.created_at.asc(), MatchReviewItem.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    breakdown_query = (
        db.query(MatchReviewItem.reason_code, func.count(MatchReviewItem.id))
        .filter(MatchReviewItem.match_run_id.in_(select(latest_runs.c.id)))
    )
    if reason:
        breakdown_query = breakdown_query.filter(MatchReviewItem.reason_code == reason)
    if trial_id:
        breakdown_query = breakdown_query.filter(MatchReviewItem.trial_id == trial_id)
    if patient_id:
        breakdown_query = breakdown_query.filter(MatchReviewItem.patient_id == patient_id)
    breakdown_rows = (
        breakdown_query.group_by(MatchReviewItem.reason_code)
        .order_by(MatchReviewItem.reason_code.asc())
        .all()
    )

    return MatchReviewQueueResponse(
        items=[_match_review_queue_item_from_model(item, trial) for item, trial in rows],
        total=total,
        page=page,
        per_page=per_page,
        breakdown_by_reason={str(reason_code or "unknown"): count for reason_code, count in breakdown_rows},
        breakdown_scope="filtered",
    )


@router.patch(
    "/criteria/{criterion_id}/review",
    response_model=CriterionResponse,
    responses=PROTECTED_REVIEW_RESPONSES,
)
def review_criterion(
    criterion_id: UUID,
    payload: ReviewRequest,
    request: Request,
    _: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    criterion = db.query(ExtractedCriterion).filter(ExtractedCriterion.id == criterion_id).first()
    if not criterion:
        raise HTTPException(status_code=404, detail="Criterion not found")
    add_request_log_context(
        request,
        trial_id=criterion.trial_id,
        pipeline_run_id=criterion.pipeline_run_id,
    )
    _ensure_reviewable_criterion(criterion, db)

    if payload.action == "accept":
        criterion.review_status = "accepted"
        criterion.review_required = False
    elif payload.action == "correct":
        criterion.original_extracted = _correction_snapshot(criterion)
        for key, value in payload.corrected_data.model_dump(exclude_unset=True).items():
            if hasattr(criterion, key):
                setattr(criterion, key, value)
        criterion.review_status = "corrected"
        criterion.review_required = False
    else:
        criterion.review_status = "rejected"
        criterion.review_required = False

    criterion.reviewed_by = payload.reviewed_by
    criterion.reviewed_at = utc_now()
    criterion.review_notes = payload.review_notes

    db.commit()
    db.refresh(criterion)
    return _criterion_detail(criterion)


@router.get("/pipeline/status", response_model=PipelineStatusResponse, responses=PROTECTED_READ_RESPONSES)
def pipeline_status(request: Request, _: str = Depends(require_api_key), db: Session = Depends(get_db)):
    add_request_log_context(request)
    latest_run_ids = _latest_completed_run_ids_subquery()
    total_runs = db.query(PipelineRun).count()
    completed = db.query(PipelineRun).filter(PipelineRun.status == "completed").count()
    failed = db.query(PipelineRun).filter(PipelineRun.status == "failed").count()
    total_trials = db.query(Trial).count()
    total_criteria = db.query(ExtractedCriterion).filter(
        ExtractedCriterion.pipeline_run_id.in_(latest_run_ids)
    ).count()
    review_pending = db.query(ExtractedCriterion).filter(
        ExtractedCriterion.pipeline_run_id.in_(latest_run_ids),
        ExtractedCriterion.review_required == True,  # noqa: E712
        ExtractedCriterion.review_status == "pending",
    ).count()
    return PipelineStatusResponse(
        version=settings.pipeline_version,
        total_runs=total_runs,
        completed=completed,
        failed=failed,
        total_trials=total_trials,
        total_criteria=total_criteria,
        review_pending=review_pending,
    )


@router.get("/pipeline/coverage", response_model=PipelineCoverageResponse, responses=PROTECTED_READ_RESPONSES)
def pipeline_coverage(request: Request, _: str = Depends(require_api_key), db: Session = Depends(get_db)):
    add_request_log_context(request)
    return PipelineCoverageResponse.model_validate(build_pipeline_coverage_payload(db))


@router.get("/pipeline/runs", response_model=PipelineRunListResponse, responses=PROTECTED_READ_RESPONSES)
def list_pipeline_runs(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    trial_id: UUID | None = None,
    pipeline_version: str | None = None,
    status: str | None = None,
    _: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    add_request_log_context(request, trial_id=trial_id)
    query = db.query(PipelineRun).order_by(PipelineRun.started_at.desc())
    if trial_id:
        query = query.filter(PipelineRun.trial_id == trial_id)
    if pipeline_version:
        query = query.filter(PipelineRun.pipeline_version == pipeline_version)
    if status:
        query = query.filter(PipelineRun.status == status)

    total = query.count()
    runs = query.offset((page - 1) * per_page).limit(per_page).all()
    return PipelineRunListResponse(
        items=[_run_detail(run) for run in runs],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/pipeline/runs/{run_id}",
    response_model=PipelineRunResponse,
    responses={**PROTECTED_READ_RESPONSES, 404: READ_ERROR_RESPONSES[404]},
)
def get_pipeline_run(run_id: UUID, request: Request, _: str = Depends(require_api_key), db: Session = Depends(get_db)):
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    add_request_log_context(request, trial_id=run.trial_id, pipeline_run_id=run.id)
    return _run_detail(run)


@router.post(
    "/trials/{trial_id}/re-extract",
    response_model=ReExtractResponse,
    responses={**PROTECTED_OPERATIONAL_RESPONSES, 404: READ_ERROR_RESPONSES[404]},
)
def re_extract_trial(
    trial_id: UUID,
    request: Request,
    _: str = Depends(reextract_rate_limit),
    db: Session = Depends(get_db),
    service: IngestionService = Depends(_get_ingestion_service),
):
    add_request_log_context(request, trial_id=trial_id)
    trial = _get_trial_or_404(trial_id, db)
    result = service.re_extract(trial)
    return ReExtractResponse(
        trial_id=trial.id,
        criteria_count=result.criteria_count,
        review_count=result.review_count,
        diff_summary=result.diff_summary,
    )


def _match_review_queue_item_from_model(item: MatchReviewItem, trial: Trial) -> MatchReviewQueueItemResponse:
    return MatchReviewQueueItemResponse(
        id=str(item.id),
        kind="match_review_item",
        reason_code=item.reason_code,
        reason_codes=[item.reason_code],
        trial_id=item.trial_id,
        trial_nct_id=trial.nct_id,
        trial_brief_title=trial.brief_title,
        patient_id=item.patient_id,
        match_run_id=item.match_run_id,
        match_result_id=item.match_result_id,
        bucket=item.bucket,
        category=item.category,
        original_text=item.criterion_text,
        outcome=item.outcome,
        state=item.state,
        state_reason=item.state_reason,
        review_required=item.bucket == "review_required",
        review_reason=item.reason_code,
        review_status="pending" if item.bucket == "review_required" else None,
        source_snippet=item.source_snippet,
        evidence_payload=item.evidence_payload,
        created_at=item.created_at,
    )


def _latest_completed_match_run_ids_subquery():
    ranked_runs = (
        select(
            MatchRun.id.label("id"),
            MatchRun.patient_id.label("patient_id"),
            func.row_number()
            .over(
                partition_by=MatchRun.patient_id,
                order_by=(
                    MatchRun.completed_at.desc(),
                    MatchRun.created_at.desc(),
                    MatchRun.id.desc(),
                ),
            )
            .label("run_rank"),
        )
        .where(MatchRun.status == "completed")
        .subquery()
    )
    return select(ranked_runs.c.id, ranked_runs.c.patient_id).where(ranked_runs.c.run_rank == 1)


def _get_trial_or_404(trial_id: UUID, db: Session) -> Trial:
    trial = db.query(Trial).filter(Trial.id == trial_id).first()
    if not trial:
        raise HTTPException(status_code=404, detail="Trial not found")
    return trial


def _latest_completed_run(trial_id: UUID, db: Session) -> PipelineRun | None:
    return (
        db.query(PipelineRun)
        .filter(
            PipelineRun.trial_id == trial_id,
            PipelineRun.status == "completed",
        )
        .order_by(PipelineRun.finished_at.desc().nullslast(), PipelineRun.started_at.desc())
        .first()
    )


def _latest_completed_run_ids_subquery():
    ranked_runs = (
        select(
            PipelineRun.id.label("id"),
            func.row_number()
            .over(
                partition_by=PipelineRun.trial_id,
                order_by=(
                    PipelineRun.finished_at.desc().nullslast(),
                    PipelineRun.started_at.desc(),
                    PipelineRun.id.desc(),
                ),
            )
            .label("run_rank"),
        )
        .where(PipelineRun.status == "completed")
        .subquery()
    )
    return select(ranked_runs.c.id).where(ranked_runs.c.run_rank == 1)


def _latest_trial_criteria_query(trial_id: UUID, db: Session) -> SQLAlchemyQuery:
    query = db.query(ExtractedCriterion).filter(ExtractedCriterion.trial_id == trial_id)
    latest_run = _latest_completed_run(trial_id, db)
    if latest_run:
        query = query.filter(ExtractedCriterion.pipeline_run_id == latest_run.id)
    return query


def _ensure_reviewable_criterion(criterion: ExtractedCriterion, db: Session) -> None:
    latest_run = _latest_completed_run(criterion.trial_id, db)
    if latest_run and criterion.pipeline_run_id != latest_run.id:
        raise HTTPException(
            status_code=409,
            detail="Criterion belongs to a superseded pipeline run and cannot be reviewed",
        )
    if criterion.review_status != "pending" or not criterion.review_required:
        raise HTTPException(
            status_code=409,
            detail="Criterion review has already been resolved",
        )


def _correction_snapshot(criterion: ExtractedCriterion) -> dict[str, Any]:
    snapshot = {
        "type": criterion.type,
        "category": criterion.category,
        "primary_semantic_category": criterion.primary_semantic_category,
        "secondary_semantic_tags": criterion.secondary_semantic_tags or [],
        "parse_status": criterion.parse_status,
        "operator": criterion.operator,
        "value_low": criterion.value_low,
        "value_high": criterion.value_high,
        "value_text": criterion.value_text,
        "unit": criterion.unit,
        "raw_expression": criterion.raw_expression,
        "negated": criterion.negated,
        "timeframe_operator": criterion.timeframe_operator,
        "timeframe_value": criterion.timeframe_value,
        "timeframe_unit": criterion.timeframe_unit,
        "specimen_type": criterion.specimen_type,
        "testing_modality": criterion.testing_modality,
        "disease_subtype": criterion.disease_subtype,
        "histology_text": criterion.histology_text,
        "assay_context": criterion.assay_context,
        "exception_logic": criterion.exception_logic,
        "exception_entities": criterion.exception_entities or [],
        "allowance_text": criterion.allowance_text,
        "logic_group_id": str(criterion.logic_group_id) if criterion.logic_group_id else None,
        "logic_operator": criterion.logic_operator,
        "coded_concepts": criterion.coded_concepts,
        "confidence": criterion.confidence,
    }
    source_sentence = criterion.source_sentence
    if not source_sentence and isinstance(criterion.original_extracted, dict):
        source_sentence = criterion.original_extracted.get("source_sentence")
    if source_sentence:
        snapshot["source_sentence"] = source_sentence
    source_clause_text = criterion.source_clause_text
    if not source_clause_text and isinstance(criterion.original_extracted, dict):
        source_clause_text = criterion.original_extracted.get("source_clause_text")
    if source_clause_text:
        snapshot["source_clause_text"] = source_clause_text
    return snapshot


def _trial_summary(trial: Trial) -> TrialSummary:
    return TrialSummary(
        id=trial.id,
        nct_id=trial.nct_id,
        brief_title=trial.brief_title,
        status=trial.status,
        phase=trial.phase,
        extraction_status=trial.extraction_status,
        ingested_at=trial.ingested_at,
    )


def _trial_detail(trial: Trial, db: Session) -> TrialDetail:
    criteria_total = _latest_trial_criteria_query(trial.id, db).count()
    review_pending = _latest_trial_criteria_query(trial.id, db).filter(
        ExtractedCriterion.review_required == True,  # noqa: E712
        ExtractedCriterion.review_status == "pending",
    ).count()

    return TrialDetail(
        **_trial_summary(trial).model_dump(),
        official_title=trial.official_title,
        conditions=trial.conditions,
        interventions=trial.interventions,
        eligibility_text=trial.eligibility_text,
        eligible_min_age=trial.eligible_min_age,
        eligible_max_age=trial.eligible_max_age,
        eligible_sex=trial.eligible_sex,
        accepts_healthy=trial.accepts_healthy,
        sponsor=trial.sponsor,
        criteria_summary=CriteriaSummary(
            total=criteria_total,
            review_pending=review_pending,
        ),
    )


def _criterion_detail(criterion: ExtractedCriterion) -> CriterionResponse:
    source_sentence = criterion.source_sentence
    source_clause_text = criterion.source_clause_text
    if isinstance(criterion.original_extracted, dict):
        if not source_sentence:
            source_sentence = criterion.original_extracted.get("source_sentence")
        if not source_clause_text:
            source_clause_text = criterion.original_extracted.get("source_clause_text")
    state, state_reason = criterion_state_from_extracted(criterion)
    return CriterionResponse(
        id=criterion.id,
        trial_id=criterion.trial_id,
        type=criterion.type,
        category=criterion.category,
        state=state,
        state_reason=state_reason,
        primary_semantic_category=criterion.primary_semantic_category,
        secondary_semantic_tags=criterion.secondary_semantic_tags or [],
        parse_status=criterion.parse_status,
        original_text=criterion.original_text,
        source_sentence=source_sentence,
        source_clause_text=source_clause_text,
        operator=criterion.operator,
        value_low=criterion.value_low,
        value_high=criterion.value_high,
        value_text=criterion.value_text,
        unit=criterion.unit,
        raw_expression=criterion.raw_expression,
        negated=criterion.negated,
        timeframe_operator=criterion.timeframe_operator,
        timeframe_value=criterion.timeframe_value,
        timeframe_unit=criterion.timeframe_unit,
        specimen_type=criterion.specimen_type,
        testing_modality=criterion.testing_modality,
        disease_subtype=criterion.disease_subtype,
        histology_text=criterion.histology_text,
        assay_context=criterion.assay_context,
        exception_logic=criterion.exception_logic,
        exception_entities=criterion.exception_entities or [],
        allowance_text=criterion.allowance_text,
        logic_group_id=criterion.logic_group_id,
        logic_operator=criterion.logic_operator,
        coded_concepts=criterion.coded_concepts or [],
        confidence=criterion.confidence,
        confidence_factors=criterion.confidence_factors,
        review_required=criterion.review_required,
        review_reason=criterion.review_reason,
        review_status=criterion.review_status,
        reviewed_by=criterion.reviewed_by,
        reviewed_at=criterion.reviewed_at,
        review_notes=criterion.review_notes,
        original_extracted=criterion.original_extracted,
        pipeline_version=criterion.pipeline_version,
        pipeline_run_id=criterion.pipeline_run_id,
        created_at=criterion.created_at,
    )


def _projection_list_response(projections) -> CriterionFHIRProjectionListResponse:
    breakdown_by_status = Counter(projection.projection_status for projection in projections)
    breakdown_by_resource_type = Counter(
        projection.resource_type or "none" for projection in projections
    )
    return CriterionFHIRProjectionListResponse(
        items=[
            CriterionFHIRProjectionResponse(
                criterion_id=projection.criterion_id,
                trial_id=projection.trial_id,
                criterion_category=projection.criterion_category,
                criterion_type=projection.criterion_type,
                mention_text=projection.mention_text,
                normalized_term=projection.normalized_term,
                resource_type=projection.resource_type,
                projection_status=projection.projection_status,
                terminology_status=projection.terminology_status,
                review_required=projection.review_required,
                system=projection.system,
                code=projection.code,
                display=projection.display,
                resource=projection.resource,
            )
            for projection in projections
        ],
        total=len(projections),
        breakdown_by_status=dict(sorted(breakdown_by_status.items())),
        breakdown_by_resource_type=dict(sorted(breakdown_by_resource_type.items())),
    )


def _run_detail(run: PipelineRun) -> PipelineRunResponse:
    return PipelineRunResponse(
        id=run.id,
        trial_id=run.trial_id,
        pipeline_version=run.pipeline_version,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        criteria_extracted_count=run.criteria_extracted_count,
        review_required_count=run.review_required_count,
        error_message=run.error_message,
        diff_summary=run.diff_summary,
    )
