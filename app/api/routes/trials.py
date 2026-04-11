from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas import IngestRequest, ReviewRequest, SearchIngestRequest
from app.config import settings
from app.db.session import get_db
from app.fhir.mapper import FHIRMapper
from app.ingestion.service import IngestionService
from app.models.database import ExtractedCriterion, PipelineRun, Trial

router = APIRouter()
fhir_mapper = FHIRMapper()


# --- Ingestion ---

@router.post("/trials/ingest", status_code=201)
def ingest_trial(request: IngestRequest, db: Session = Depends(get_db)):
    service = IngestionService(db)
    result = service.ingest(request.nct_id)
    return {
        "nct_id": result.trial.nct_id,
        "trial_id": str(result.trial.id),
        "criteria_count": result.criteria_count,
        "review_count": result.review_count,
        "skipped": result.skipped,
    }


@router.post("/trials/search-ingest", status_code=201)
def search_and_ingest(request: SearchIngestRequest, db: Session = Depends(get_db)):
    service = IngestionService(db)
    results = service.search_and_ingest(
        condition=request.condition,
        status=request.status,
        phase=request.phase,
        limit=request.limit,
    )
    return {
        "ingested": len(results),
        "trials": [
            {
                "nct_id": r.trial.nct_id,
                "trial_id": str(r.trial.id),
                "criteria_count": r.criteria_count,
                "skipped": r.skipped,
            }
            for r in results
        ],
    }


# --- Trial retrieval ---

@router.get("/trials")
def list_trials(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Trial)
    if status:
        query = query.filter(Trial.status == status)
    total = query.count()
    trials = query.offset((page - 1) * per_page).limit(per_page).all()
    return {
        "items": [_trial_summary(t) for t in trials],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/trials/{trial_id}")
def get_trial(trial_id: UUID, db: Session = Depends(get_db)):
    trial = db.query(Trial).filter(Trial.id == trial_id).first()
    if not trial:
        raise HTTPException(status_code=404, detail="Trial not found")
    return _trial_detail(trial)


@router.get("/trials/nct/{nct_id}")
def get_trial_by_nct(nct_id: str, db: Session = Depends(get_db)):
    trial = db.query(Trial).filter(Trial.nct_id == nct_id).first()
    if not trial:
        raise HTTPException(status_code=404, detail="Trial not found")
    return _trial_detail(trial)


@router.get("/trials/{trial_id}/criteria")
def get_trial_criteria(trial_id: UUID, db: Session = Depends(get_db)):
    criteria = db.query(ExtractedCriterion).filter(
        ExtractedCriterion.trial_id == trial_id
    ).all()
    return {"criteria": [_criterion_detail(c) for c in criteria]}


@router.get("/criteria/{criterion_id}")
def get_criterion(criterion_id: UUID, db: Session = Depends(get_db)):
    criterion = db.query(ExtractedCriterion).filter(
        ExtractedCriterion.id == criterion_id
    ).first()
    if not criterion:
        raise HTTPException(status_code=404, detail="Criterion not found")
    return _criterion_detail(criterion)


# --- FHIR export ---

@router.get("/trials/{trial_id}/fhir")
def get_trial_fhir(trial_id: UUID, db: Session = Depends(get_db)):
    trial = db.query(Trial).filter(Trial.id == trial_id).first()
    if not trial:
        raise HTTPException(status_code=404, detail="Trial not found")
    criteria = db.query(ExtractedCriterion).filter(
        ExtractedCriterion.trial_id == trial_id
    ).all()
    return fhir_mapper.to_research_study(trial, criteria)


# --- Review ---

@router.get("/review")
def get_review_queue(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(ExtractedCriterion).filter(
        ExtractedCriterion.review_required == True,  # noqa: E712
        ExtractedCriterion.review_status == "pending",
    )
    total = query.count()
    criteria = query.offset((page - 1) * per_page).limit(per_page).all()
    return {
        "items": [_criterion_detail(c) for c in criteria],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.patch("/criteria/{criterion_id}/review")
def review_criterion(
    criterion_id: UUID,
    request: ReviewRequest,
    db: Session = Depends(get_db),
):
    criterion = db.query(ExtractedCriterion).filter(
        ExtractedCriterion.id == criterion_id
    ).first()
    if not criterion:
        raise HTTPException(status_code=404, detail="Criterion not found")

    if request.action == "accept":
        criterion.review_status = "accepted"
        criterion.review_required = False
    elif request.action == "correct":
        # Snapshot original before correction
        criterion.original_extracted = {
            "coded_concepts": criterion.coded_concepts,
            "confidence": criterion.confidence,
            "category": criterion.category,
            "operator": criterion.operator,
            "value_low": criterion.value_low,
            "value_high": criterion.value_high,
            "unit": criterion.unit,
        }
        # Apply corrections
        if request.corrected_data:
            for key, value in request.corrected_data.items():
                if hasattr(criterion, key):
                    setattr(criterion, key, value)
        criterion.review_status = "corrected"
        criterion.review_required = False
    elif request.action == "reject":
        criterion.review_status = "rejected"
        criterion.review_required = False
    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: {request.action}")

    criterion.reviewed_by = request.reviewed_by
    criterion.reviewed_at = datetime.utcnow()
    criterion.review_notes = request.review_notes

    db.commit()
    db.refresh(criterion)

    return _criterion_detail(criterion)


# --- Pipeline management ---

@router.get("/pipeline/status")
def pipeline_status(db: Session = Depends(get_db)):
    total_runs = db.query(PipelineRun).count()
    completed = db.query(PipelineRun).filter(PipelineRun.status == "completed").count()
    failed = db.query(PipelineRun).filter(PipelineRun.status == "failed").count()
    return {
        "version": settings.pipeline_version,
        "total_runs": total_runs,
        "completed": completed,
        "failed": failed,
    }


@router.get("/pipeline/runs")
def list_pipeline_runs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(PipelineRun).order_by(PipelineRun.started_at.desc())
    total = query.count()
    runs = query.offset((page - 1) * per_page).limit(per_page).all()
    return {
        "items": [_run_summary(r) for r in runs],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/pipeline/runs/{run_id}")
def get_pipeline_run(run_id: UUID, db: Session = Depends(get_db)):
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return _run_summary(run)


@router.post("/trials/{trial_id}/re-extract")
def re_extract_trial(trial_id: UUID, db: Session = Depends(get_db)):
    trial = db.query(Trial).filter(Trial.id == trial_id).first()
    if not trial:
        raise HTTPException(status_code=404, detail="Trial not found")
    service = IngestionService(db)
    result = service.re_extract(trial)
    return {
        "trial_id": str(trial.id),
        "criteria_count": result.criteria_count,
        "review_count": result.review_count,
    }


# --- Serialization helpers ---

def _trial_summary(trial: Trial) -> dict:
    return {
        "id": str(trial.id),
        "nct_id": trial.nct_id,
        "brief_title": trial.brief_title,
        "status": trial.status,
        "phase": trial.phase,
        "extraction_status": trial.extraction_status,
        "ingested_at": trial.ingested_at.isoformat() if trial.ingested_at else None,
    }


def _trial_detail(trial: Trial) -> dict:
    return {
        **_trial_summary(trial),
        "official_title": trial.official_title,
        "conditions": trial.conditions,
        "interventions": trial.interventions,
        "eligibility_text": trial.eligibility_text,
        "eligible_min_age": trial.eligible_min_age,
        "eligible_max_age": trial.eligible_max_age,
        "eligible_sex": trial.eligible_sex,
        "accepts_healthy": trial.accepts_healthy,
        "sponsor": trial.sponsor,
    }


def _criterion_detail(criterion: ExtractedCriterion) -> dict:
    return {
        "id": str(criterion.id),
        "trial_id": str(criterion.trial_id),
        "type": criterion.type,
        "category": criterion.category,
        "parse_status": criterion.parse_status,
        "original_text": criterion.original_text,
        "operator": criterion.operator,
        "value_low": criterion.value_low,
        "value_high": criterion.value_high,
        "value_text": criterion.value_text,
        "unit": criterion.unit,
        "negated": criterion.negated,
        "timeframe_operator": criterion.timeframe_operator,
        "timeframe_value": criterion.timeframe_value,
        "timeframe_unit": criterion.timeframe_unit,
        "coded_concepts": criterion.coded_concepts,
        "confidence": criterion.confidence,
        "review_required": criterion.review_required,
        "review_reason": criterion.review_reason,
        "review_status": criterion.review_status,
        "reviewed_by": criterion.reviewed_by,
        "reviewed_at": criterion.reviewed_at.isoformat() if criterion.reviewed_at else None,
        "review_notes": criterion.review_notes,
        "original_extracted": criterion.original_extracted,
        "pipeline_version": criterion.pipeline_version,
    }


def _run_summary(run: PipelineRun) -> dict:
    return {
        "id": str(run.id),
        "trial_id": str(run.trial_id),
        "pipeline_version": run.pipeline_version,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "criteria_extracted_count": run.criteria_extracted_count,
        "review_required_count": run.review_required_count,
        "error_message": run.error_message,
    }
