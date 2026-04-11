from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Query as SQLAlchemyQuery
from sqlalchemy.orm import Session

from app.api.schemas import (
    CriteriaListResponse,
    CriteriaSummary,
    CriterionResponse,
    IngestRequest,
    IngestResponse,
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
from app.config import settings
from app.db.session import get_db
from app.fhir.mapper import FHIRMapper
from app.fhir.models import ResearchStudy
from app.ingestion.service import IngestionService
from app.models.database import ExtractedCriterion, FHIRResearchStudy, PipelineRun, Trial
from app.time_utils import utc_now

router = APIRouter()
fhir_mapper = FHIRMapper()


def _get_ingestion_service(request: Request, db: Session = Depends(get_db)) -> IngestionService:
    pipeline = getattr(request.app.state, "extraction_pipeline", None)
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Extraction pipeline unavailable")
    return IngestionService(db, pipeline=pipeline)


@router.post("/trials/ingest", status_code=201, response_model=IngestResponse)
def ingest_trial(request: IngestRequest, service: IngestionService = Depends(_get_ingestion_service)):
    result = service.ingest(request.nct_id)
    return IngestResponse(
        nct_id=result.trial.nct_id,
        trial_id=result.trial.id,
        criteria_count=result.criteria_count,
        review_count=result.review_count,
        skipped=result.skipped,
    )


@router.post("/trials/search-ingest", status_code=201, response_model=SearchIngestResponse)
def search_and_ingest(
    request: SearchIngestRequest,
    service: IngestionService = Depends(_get_ingestion_service),
):
    results = service.search_and_ingest(
        condition=request.condition,
        status=request.status,
        phase=request.phase,
        limit=request.limit,
        page_token=request.page_token,
    )
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


@router.get("/trials", response_model=TrialListResponse)
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


@router.get("/trials/{trial_id}", response_model=TrialDetail)
def get_trial(trial_id: UUID, db: Session = Depends(get_db)):
    trial = _get_trial_or_404(trial_id, db)
    return _trial_detail(trial, db)


@router.get("/trials/nct/{nct_id}", response_model=TrialDetail)
def get_trial_by_nct(nct_id: str, db: Session = Depends(get_db)):
    trial = db.query(Trial).filter(Trial.nct_id == nct_id).first()
    if not trial:
        raise HTTPException(status_code=404, detail="Trial not found")
    return _trial_detail(trial, db)


@router.get("/trials/{trial_id}/criteria", response_model=CriteriaListResponse)
def get_trial_criteria(
    trial_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    type: str | None = None,
    category: str | None = None,
    review_required: bool | None = None,
    db: Session = Depends(get_db),
):
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


@router.get("/criteria/{criterion_id}", response_model=CriterionResponse)
def get_criterion(criterion_id: UUID, db: Session = Depends(get_db)):
    criterion = db.query(ExtractedCriterion).filter(ExtractedCriterion.id == criterion_id).first()
    if not criterion:
        raise HTTPException(status_code=404, detail="Criterion not found")
    return _criterion_detail(criterion)


@router.get("/trials/{trial_id}/fhir")
def get_trial_fhir(trial_id: UUID, db: Session = Depends(get_db)):
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


@router.get("/review", response_model=ReviewQueueResponse)
def get_review_queue(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    reason: str | None = None,
    trial_id: UUID | None = None,
    db: Session = Depends(get_db),
):
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
    criteria = query.order_by(ExtractedCriterion.created_at.asc()).offset((page - 1) * per_page).limit(per_page).all()

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
    breakdown_query = breakdown_query.group_by(ExtractedCriterion.review_reason)
    breakdown_by_reason = {row[0] or "unknown": row[1] for row in breakdown_query.all()}

    return ReviewQueueResponse(
        items=[_criterion_detail(c) for c in criteria],
        total=total,
        page=page,
        per_page=per_page,
        breakdown_by_reason=breakdown_by_reason,
    )


@router.patch("/criteria/{criterion_id}/review", response_model=CriterionResponse)
def review_criterion(
    criterion_id: UUID,
    request: ReviewRequest,
    db: Session = Depends(get_db),
):
    criterion = db.query(ExtractedCriterion).filter(ExtractedCriterion.id == criterion_id).first()
    if not criterion:
        raise HTTPException(status_code=404, detail="Criterion not found")
    _ensure_reviewable_criterion(criterion, db)

    if request.action == "accept":
        criterion.review_status = "accepted"
        criterion.review_required = False
    elif request.action == "correct":
        criterion.original_extracted = _correction_snapshot(criterion)
        for key, value in request.corrected_data.model_dump(exclude_unset=True).items():
            if hasattr(criterion, key):
                setattr(criterion, key, value)
        criterion.review_status = "corrected"
        criterion.review_required = False
    else:
        criterion.review_status = "rejected"
        criterion.review_required = False

    criterion.reviewed_by = request.reviewed_by
    criterion.reviewed_at = utc_now()
    criterion.review_notes = request.review_notes

    db.commit()
    db.refresh(criterion)
    return _criterion_detail(criterion)


@router.get("/pipeline/status", response_model=PipelineStatusResponse)
def pipeline_status(db: Session = Depends(get_db)):
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


@router.get("/pipeline/runs", response_model=PipelineRunListResponse)
def list_pipeline_runs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    trial_id: UUID | None = None,
    pipeline_version: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
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


@router.get("/pipeline/runs/{run_id}", response_model=PipelineRunResponse)
def get_pipeline_run(run_id: UUID, db: Session = Depends(get_db)):
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return _run_detail(run)


@router.post("/trials/{trial_id}/re-extract", response_model=ReExtractResponse)
def re_extract_trial(
    trial_id: UUID,
    db: Session = Depends(get_db),
    service: IngestionService = Depends(_get_ingestion_service),
):
    trial = _get_trial_or_404(trial_id, db)
    result = service.re_extract(trial)
    return ReExtractResponse(
        trial_id=trial.id,
        criteria_count=result.criteria_count,
        review_count=result.review_count,
        diff_summary=result.diff_summary,
    )


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
    return {
        "type": criterion.type,
        "category": criterion.category,
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
        "logic_group_id": str(criterion.logic_group_id) if criterion.logic_group_id else None,
        "logic_operator": criterion.logic_operator,
        "coded_concepts": criterion.coded_concepts,
        "confidence": criterion.confidence,
    }


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
    return CriterionResponse(
        id=criterion.id,
        trial_id=criterion.trial_id,
        type=criterion.type,
        category=criterion.category,
        parse_status=criterion.parse_status,
        original_text=criterion.original_text,
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
        logic_group_id=criterion.logic_group_id,
        logic_operator=criterion.logic_operator,
        coded_concepts=criterion.coded_concepts or [],
        confidence=criterion.confidence,
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
