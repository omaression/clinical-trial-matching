from types import SimpleNamespace
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import require_api_key
from app.api.openapi import PROTECTED_MUTATION_RESPONSES, PROTECTED_RESOURCE_RESPONSES
from app.api.schemas import (
    MatchCriterionResultResponse,
    MatchExplanationItemResponse,
    MatchExplanationResponse,
    MatchGapEntryResponse,
    MatchGapReportResponse,
    MatchResultDetail,
    MatchResultListResponse,
    MatchResultSummary,
    MatchRunResponse,
    PatientBiomarkerInput,
    PatientBiomarkerResponse,
    PatientConditionInput,
    PatientConditionResponse,
    PatientCreateRequest,
    PatientDetail,
    PatientLabInput,
    PatientLabResponse,
    PatientListResponse,
    PatientMedicationInput,
    PatientMedicationResponse,
    PatientSummary,
    PatientTherapyInput,
    PatientTherapyResponse,
    PatientUpdateRequest,
)
from app.api.state import criterion_state_from_match_result_criterion, match_state_from_match_result
from app.db.session import get_db
from app.matching.gap_report import build_gap_report_payload
from app.matching.service import CriterionEvaluation, PatientMatchService, _collapse_or_group
from app.models.database import (
    MatchResult,
    MatchRun,
    Patient,
    PatientBiomarker,
    PatientCondition,
    PatientLab,
    PatientMedication,
    PatientTherapy,
)
from app.time_utils import utc_now

router = APIRouter()


def _get_match_service(db: Session = Depends(get_db)) -> PatientMatchService:
    return PatientMatchService(db)


@router.post("/patients", response_model=PatientDetail, status_code=201, responses=PROTECTED_MUTATION_RESPONSES)
def create_patient(
    payload: PatientCreateRequest,
    _: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    patient = Patient(
        external_id=payload.external_id,
        sex=payload.sex,
        birth_date=payload.birth_date,
        ecog_status=payload.ecog_status,
        is_healthy_volunteer=payload.is_healthy_volunteer,
        can_consent=payload.can_consent,
        protocol_compliant=payload.protocol_compliant,
        claustrophobic=payload.claustrophobic,
        motion_intolerant=payload.motion_intolerant,
        pregnant=payload.pregnant,
        mr_device_present=payload.mr_device_present,
        country=payload.country,
        state=payload.state,
        city=payload.city,
        latitude=payload.latitude,
        longitude=payload.longitude,
        created_at=utc_now(),
    )
    db.add(patient)
    db.flush()
    _replace_patient_facts(patient, payload)
    db.commit()
    return _patient_detail(_load_patient_or_404(patient.id, db))


@router.get("/patients", response_model=PatientListResponse, responses=PROTECTED_MUTATION_RESPONSES)
def list_patients(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    _: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    query = db.query(Patient).order_by(Patient.created_at.desc(), Patient.id.desc())
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return PatientListResponse(
        items=[_patient_summary(patient) for patient in items],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/patients/{patient_id}", response_model=PatientDetail, responses=PROTECTED_RESOURCE_RESPONSES)
def get_patient(
    patient_id: UUID,
    _: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    return _patient_detail(_load_patient_or_404(patient_id, db))


@router.patch("/patients/{patient_id}", response_model=PatientDetail, responses=PROTECTED_RESOURCE_RESPONSES)
def update_patient(
    patient_id: UUID,
    payload: PatientUpdateRequest,
    _: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    patient = _load_patient_or_404(patient_id, db)
    for field in (
        "external_id",
        "sex",
        "birth_date",
        "ecog_status",
        "is_healthy_volunteer",
        "can_consent",
        "protocol_compliant",
        "claustrophobic",
        "motion_intolerant",
        "pregnant",
        "mr_device_present",
        "country",
        "state",
        "city",
        "latitude",
        "longitude",
    ):
        if field in payload.model_fields_set:
            setattr(patient, field, getattr(payload, field))
    patient.updated_at = utc_now()
    _replace_patient_facts(patient, payload)
    db.commit()
    return _patient_detail(_load_patient_or_404(patient_id, db))


@router.post(
    "/patients/{patient_id}/match",
    response_model=MatchRunResponse,
    responses=PROTECTED_RESOURCE_RESPONSES,
)
def match_patient(
    patient_id: UUID,
    _: str = Depends(require_api_key),
    service: PatientMatchService = Depends(_get_match_service),
    db: Session = Depends(get_db),
):
    patient = service.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    match_run = service.run_match(patient)
    match_run = _load_match_run_or_404(match_run.id, db)
    return _match_run_detail(match_run)


@router.get(
    "/patients/{patient_id}/matches",
    response_model=MatchResultListResponse,
    responses=PROTECTED_RESOURCE_RESPONSES,
)
def list_patient_matches(
    patient_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    _: str = Depends(require_api_key),
    service: PatientMatchService = Depends(_get_match_service),
    db: Session = Depends(get_db),
):
    if not db.query(Patient.id).filter(Patient.id == patient_id).first():
        raise HTTPException(status_code=404, detail="Patient not found")
    items, total = service.list_patient_matches(patient_id, page=page, per_page=per_page)
    return MatchResultListResponse(
        items=[_match_summary(item) for item in items],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/matches/{match_id}", response_model=MatchResultDetail, responses=PROTECTED_RESOURCE_RESPONSES)
def get_match_result(
    match_id: UUID,
    _: str = Depends(require_api_key),
    service: PatientMatchService = Depends(_get_match_service),
):
    match_result = service.get_match_result(match_id)
    if not match_result:
        raise HTTPException(status_code=404, detail="Match result not found")
    return _match_detail(match_result)


def _load_patient_or_404(patient_id: UUID, db: Session) -> Patient:
    patient = (
        db.query(Patient)
        .options(
            selectinload(Patient.conditions),
            selectinload(Patient.biomarkers),
            selectinload(Patient.labs),
            selectinload(Patient.therapies),
            selectinload(Patient.medications),
        )
        .filter(Patient.id == patient_id)
        .first()
    )
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


def _load_match_run_or_404(match_run_id: UUID, db: Session) -> MatchRun:
    match_run = (
        db.query(MatchRun)
        .options(
            selectinload(MatchRun.results).selectinload(MatchResult.trial),
        )
        .filter(MatchRun.id == match_run_id)
        .first()
    )
    if not match_run:
        raise HTTPException(status_code=404, detail="Match run not found")
    return match_run


def _replace_patient_facts(patient: Patient, payload: PatientCreateRequest | PatientUpdateRequest) -> None:
    if isinstance(payload, PatientCreateRequest) or payload.conditions is not None:
        patient.conditions = [_build_condition(item) for item in payload.conditions or []]
    if isinstance(payload, PatientCreateRequest) or payload.biomarkers is not None:
        patient.biomarkers = [_build_biomarker(item) for item in payload.biomarkers or []]
    if isinstance(payload, PatientCreateRequest) or payload.labs is not None:
        patient.labs = [_build_lab(item) for item in payload.labs or []]
    if isinstance(payload, PatientCreateRequest) or payload.therapies is not None:
        patient.therapies = [_build_therapy(item) for item in payload.therapies or []]
    if isinstance(payload, PatientCreateRequest) or payload.medications is not None:
        patient.medications = [_build_medication(item) for item in payload.medications or []]


def _build_condition(item: PatientConditionInput) -> PatientCondition:
    return PatientCondition(description=item.description, coded_concepts=item.model_dump()["coded_concepts"])


def _build_biomarker(item: PatientBiomarkerInput) -> PatientBiomarker:
    return PatientBiomarker(
        description=item.description,
        coded_concepts=item.model_dump()["coded_concepts"],
        value_text=item.value_text,
    )


def _build_lab(item: PatientLabInput) -> PatientLab:
    return PatientLab(
        description=item.description,
        coded_concepts=item.model_dump()["coded_concepts"],
        value_numeric=item.value_numeric,
        value_text=item.value_text,
        unit=item.unit,
    )


def _build_therapy(item: PatientTherapyInput) -> PatientTherapy:
    return PatientTherapy(
        description=item.description,
        coded_concepts=item.model_dump()["coded_concepts"],
        line_of_therapy=item.line_of_therapy,
        completed=item.completed,
    )


def _build_medication(item: PatientMedicationInput) -> PatientMedication:
    return PatientMedication(
        description=item.description,
        coded_concepts=item.model_dump()["coded_concepts"],
        active=item.active,
    )


def _patient_summary(patient: Patient) -> PatientSummary:
    return PatientSummary(
        id=patient.id,
        external_id=patient.external_id,
        sex=patient.sex,
        birth_date=patient.birth_date,
        ecog_status=patient.ecog_status,
        is_healthy_volunteer=patient.is_healthy_volunteer,
        can_consent=patient.can_consent,
        protocol_compliant=patient.protocol_compliant,
        claustrophobic=patient.claustrophobic,
        motion_intolerant=patient.motion_intolerant,
        pregnant=patient.pregnant,
        mr_device_present=patient.mr_device_present,
        country=patient.country,
        state=patient.state,
        city=patient.city,
        latitude=patient.latitude,
        longitude=patient.longitude,
        created_at=patient.created_at,
        updated_at=patient.updated_at,
    )


def _patient_detail(patient: Patient) -> PatientDetail:
    return PatientDetail(
        **_patient_summary(patient).model_dump(),
        conditions=[
            PatientConditionResponse(
                id=condition.id,
                description=condition.description,
                coded_concepts=condition.coded_concepts or [],
            )
            for condition in patient.conditions
        ],
        biomarkers=[
            PatientBiomarkerResponse(
                id=biomarker.id,
                description=biomarker.description,
                coded_concepts=biomarker.coded_concepts or [],
                value_text=biomarker.value_text,
            )
            for biomarker in patient.biomarkers
        ],
        labs=[
            PatientLabResponse(
                id=lab.id,
                description=lab.description,
                coded_concepts=lab.coded_concepts or [],
                value_numeric=lab.value_numeric,
                value_text=lab.value_text,
                unit=lab.unit,
            )
            for lab in patient.labs
        ],
        therapies=[
            PatientTherapyResponse(
                id=therapy.id,
                description=therapy.description,
                coded_concepts=therapy.coded_concepts or [],
                line_of_therapy=therapy.line_of_therapy,
                completed=therapy.completed,
            )
            for therapy in patient.therapies
        ],
        medications=[
            PatientMedicationResponse(
                id=medication.id,
                description=medication.description,
                coded_concepts=medication.coded_concepts or [],
                active=medication.active,
            )
            for medication in patient.medications
        ],
    )


def _match_metrics(match_result: MatchResult) -> dict[str, float | int]:
    deterministic_count = match_result.favorable_count + match_result.unfavorable_count
    unresolved_count = match_result.unknown_count + match_result.requires_review_count
    evaluated_count = deterministic_count + unresolved_count
    coverage_ratio = deterministic_count / evaluated_count if evaluated_count else 0.0
    return {
        "determinate_score": match_result.score,
        "coverage_ratio": coverage_ratio,
        "evaluated_count": evaluated_count,
        "deterministic_count": deterministic_count,
        "unresolved_count": unresolved_count,
    }


def _match_summary(match_result: MatchResult) -> MatchResultSummary:
    state, state_reason = match_state_from_match_result(match_result)
    return MatchResultSummary(
        id=match_result.id,
        match_run_id=match_result.match_run_id,
        patient_id=match_result.patient_id,
        trial_id=match_result.trial_id,
        trial_nct_id=match_result.trial.nct_id,
        trial_brief_title=match_result.trial.brief_title,
        overall_status=match_result.overall_status,
        state=state,
        state_reason=state_reason,
        score=match_result.score,
        favorable_count=match_result.favorable_count,
        unfavorable_count=match_result.unfavorable_count,
        unknown_count=match_result.unknown_count,
        requires_review_count=match_result.requires_review_count,
        summary_explanation=match_result.summary_explanation,
        created_at=match_result.created_at,
        **_match_metrics(match_result),
    )


def _build_match_criterion_response(criterion) -> MatchCriterionResultResponse:
    state, state_reason = criterion_state_from_match_result_criterion(criterion)
    return MatchCriterionResultResponse(
        id=criterion.id,
        criterion_id=criterion.criterion_id,
        pipeline_run_id=criterion.pipeline_run_id,
        source_type=criterion.source_type,
        source_label=criterion.source_label,
        criterion_type=criterion.criterion_type,
        category=criterion.category,
        criterion_text=criterion.criterion_text,
        outcome=criterion.outcome,
        state=state,
        state_reason=state_reason,
        explanation_text=criterion.explanation_text,
        explanation_type=criterion.explanation_type,
        evidence_payload=criterion.evidence_payload,
        created_at=criterion.created_at,
    )


def _explanation_label_for_category(category: str) -> str:
    return category.replace("_", " ").title()


def _first_scalar_evidence_value(value):
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        preferred_keys = (
            "source_snippet",
            "description",
            "display",
            "value_text",
            "criterion_value_text",
            "review_reason",
            "required_sex",
            "patient_sex",
        )
        for key in preferred_keys:
            if key in value:
                found = _first_scalar_evidence_value(value[key])
                if found:
                    return found
        for nested_value in value.values():
            found = _first_scalar_evidence_value(nested_value)
            if found:
                return found
        return None
    if isinstance(value, list):
        for item in value:
            found = _first_scalar_evidence_value(item)
            if found:
                return found
    return None


def _source_snippet_for_criterion(criterion) -> str | None:
    if not isinstance(criterion.evidence_payload, dict):
        return None
    explicit_snippet = criterion.evidence_payload.get("source_snippet") or criterion.evidence_payload.get("source_text")
    if isinstance(explicit_snippet, str) and explicit_snippet.strip():
        return explicit_snippet.strip()
    return None


def _build_match_explanation_item(criterion) -> MatchExplanationItemResponse:
    state, _ = criterion_state_from_match_result_criterion(criterion)
    return MatchExplanationItemResponse(
        label=_explanation_label_for_category(criterion.category),
        category=criterion.category,
        criterion_text=criterion.criterion_text,
        outcome=criterion.outcome,
        state=state,
        explanation_text=criterion.explanation_text,
        source_snippet=_source_snippet_for_criterion(criterion),
        evidence_payload=criterion.evidence_payload,
    )


def _build_match_explanation(criteria) -> MatchExplanationResponse:
    explanation = MatchExplanationResponse()
    for criterion in criteria:
        item = _build_match_explanation_item(criterion)
        state, _ = criterion_state_from_match_result_criterion(criterion)

        if criterion.outcome in {"matched", "not_triggered"}:
            explanation.matched.append(item)
        elif criterion.outcome in {"not_matched", "triggered"}:
            explanation.blockers.append(item)

        if criterion.outcome in {"unknown", "requires_review"} or state != "structured_safe":
            explanation.review_required.append(item)
    return explanation


def _patient_flag_field_name(criterion) -> str | None:
    evidence = criterion.evidence_payload
    if not isinstance(evidence, dict):
        return None
    patient_flag_field = evidence.get("patient_flag_field")
    if isinstance(patient_flag_field, str) and patient_flag_field:
        return patient_flag_field
    return None


def _has_missing_patient_data(criterion) -> bool:
    state_reason = getattr(criterion, "state_reason", None)
    if state_reason == "legacy_state_unverifiable":
        return False

    evidence = criterion.evidence_payload
    if not isinstance(evidence, dict):
        return False

    scalar_patient_keys = (
        "patient_age_years",
        "patient_sex",
        "patient_is_healthy_volunteer",
        "patient_ecog_status",
    )
    snapshot_missing_data = evidence.get("snapshot_missing_data")
    if snapshot_missing_data is True:
        return True
    if any(key in evidence and evidence[key] is None for key in scalar_patient_keys):
        return True

    list_patient_keys = (
        "patient_conditions",
        "patient_biomarkers",
        "patient_labs",
        "patient_therapies",
    )
    if any(key in evidence and isinstance(evidence[key], list) and not evidence[key] for key in list_patient_keys):
        return True

    if criterion.category == "lab_value":
        labs = evidence.get("patient_labs")
        if (
            isinstance(labs, list)
            and labs
            and all(lab.get("value_numeric") is None for lab in labs if isinstance(lab, dict))
        ):
            return True

    if criterion.category in {"prior_therapy", "line_of_therapy"}:
        therapies = evidence.get("patient_therapies")
        if isinstance(therapies, list) and therapies and all(
            therapy.get("line_of_therapy") is None for therapy in therapies if isinstance(therapy, dict)
        ):
            return True

    patient_flags = evidence.get("patient_flags")
    if isinstance(patient_flags, dict):
        field_name = _patient_flag_field_name(criterion)
        if field_name and patient_flags.get(field_name) is None:
            return True

    if criterion.category == "concomitant_medication":
        medications = evidence.get("patient_medications")
        if not isinstance(medications, list) or not medications:
            return True
        if evidence.get("exception_logic") or evidence.get("allowance_text"):
            return False
        if any(
            evidence.get(key) is not None
            for key in ("timeframe_operator", "timeframe_value", "timeframe_unit")
        ):
            return False
        return False

    return False


def _is_hard_blocker(criterion, *, state: str | None = None) -> bool:
    criterion_state = state
    if criterion_state is None:
        criterion_state, _ = criterion_state_from_match_result_criterion(criterion)
    return criterion_state == "structured_safe"


def _criterion_logic_group_key(criterion) -> tuple[object, str] | None:
    evidence = criterion.evidence_payload
    if not isinstance(evidence, dict):
        return None
    snapshot_metadata = evidence.get("snapshot_match_metadata")
    if not isinstance(snapshot_metadata, dict):
        return None
    logic_group_id = snapshot_metadata.get("logic_group_id")
    logic_operator = snapshot_metadata.get("logic_operator")
    if logic_group_id and logic_operator == "OR":
        return logic_group_id, logic_operator
    return None


def _criterion_to_evaluation(criterion) -> CriterionEvaluation:
    logic_group_id = None
    logic_operator = None
    evidence = criterion.evidence_payload
    if isinstance(evidence, dict):
        snapshot_metadata = evidence.get("snapshot_match_metadata")
        if isinstance(snapshot_metadata, dict):
            logic_group_id = snapshot_metadata.get("logic_group_id")
            logic_operator = snapshot_metadata.get("logic_operator")
    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        pipeline_run_id=criterion.pipeline_run_id,
        logic_group_id=logic_group_id,
        logic_operator=logic_operator,
        source_type=criterion.source_type,
        source_label=criterion.source_label,
        criterion_type=criterion.criterion_type,
        category=criterion.category,
        criterion_text=criterion.criterion_text,
        outcome=criterion.outcome,
        state=criterion.state,
        state_reason=criterion.state_reason,
        explanation_text=criterion.explanation_text,
        explanation_type=criterion.explanation_type,
        evidence_payload=criterion.evidence_payload,
    )


def _evaluation_to_gap_criterion(evaluation: CriterionEvaluation):
    return SimpleNamespace(
        criterion_id=evaluation.criterion_id,
        pipeline_run_id=evaluation.pipeline_run_id,
        source_type=evaluation.source_type,
        source_label=evaluation.source_label,
        criterion_type=evaluation.criterion_type,
        category=evaluation.category,
        criterion_text=evaluation.criterion_text,
        outcome=evaluation.outcome,
        state=evaluation.state,
        state_reason=evaluation.state_reason,
        explanation_text=evaluation.explanation_text,
        explanation_type=evaluation.explanation_type,
        evidence_payload=evaluation.evidence_payload,
        criterion=None,
    )


def _grouped_gap_criterion(members: list[object]):
    collapsed = _collapse_or_group([_criterion_to_evaluation(member) for member in members])
    member_texts = []
    for member in members:
        text = member.criterion_text.strip()
        if text and text not in member_texts:
            member_texts.append(text)
    evidence_payload = collapsed.evidence_payload if isinstance(collapsed.evidence_payload, dict) else {}
    return SimpleNamespace(
        criterion_id=collapsed.criterion_id,
        pipeline_run_id=collapsed.pipeline_run_id,
        source_type=collapsed.source_type,
        source_label=collapsed.source_label,
        criterion_type=collapsed.criterion_type,
        category=collapsed.category,
        criterion_text=" OR ".join(member_texts) if member_texts else collapsed.criterion_text,
        outcome=collapsed.outcome,
        state=collapsed.state,
        state_reason=collapsed.state_reason,
        explanation_text=collapsed.explanation_text,
        explanation_type=collapsed.explanation_type,
        evidence_payload={
            **evidence_payload,
            "snapshot_match_metadata": {
                "logic_group_id": str(collapsed.logic_group_id) if collapsed.logic_group_id is not None else None,
                "logic_operator": collapsed.logic_operator,
            },
            "member_criterion_texts": member_texts,
            "snapshot_missing_data": any(_has_missing_patient_data(member) for member in members),
        },
        criterion=None,
    )


def _effective_gap_report_criteria(criteria):
    effective = []
    grouped_members: dict[tuple[object, str], list[object]] = {}
    grouped_order: list[tuple[object, str]] = []

    for criterion in criteria:
        key = _criterion_logic_group_key(criterion)
        if key is not None:
            if key not in grouped_members:
                grouped_order.append(key)
                grouped_members[key] = []
            grouped_members[key].append(criterion)
            continue

        effective.append(criterion)

    for key in grouped_order:
        effective.append(_grouped_gap_criterion(grouped_members[key]))

    return effective


def _build_match_gap_entry(criterion, kind: str) -> MatchGapEntryResponse:
    state, state_reason = criterion_state_from_match_result_criterion(criterion)
    return MatchGapEntryResponse(
        kind=kind,
        label=_explanation_label_for_category(criterion.category),
        category=criterion.category,
        criterion_text=criterion.criterion_text,
        outcome=criterion.outcome,
        state=state,
        state_reason=state_reason,
        summary=criterion.explanation_text,
        source_snippet=_source_snippet_for_criterion(criterion),
        evidence_payload=criterion.evidence_payload,
    )


def _build_match_gap_report(criteria) -> MatchGapReportResponse:
    return MatchGapReportResponse.model_validate(build_gap_report_payload(criteria))


def _legacy_gap_report_payload(match_result: MatchResult) -> dict[str, list[dict[str, object | None]]]:
    base_entry = {
        "label": "Historical Snapshot",
        "category": "historical_snapshot",
        "criterion_text": "Gap report was not snapshotted for this historical match result.",
        "state": match_result.state,
        "state_reason": match_result.state_reason or "legacy_state_unverifiable",
        "summary": match_result.summary_explanation,
        "source_snippet": None,
        "evidence_payload": None,
    }
    report = {
        "hard_blockers": [],
        "clarifiable_blockers": [],
        "missing_data": [],
        "review_required": [],
        "unsupported": [],
    }
    if match_result.state == "blocked_unsupported":
        report["unsupported"].append({**base_entry, "kind": "unsupported", "outcome": "unknown"})
    if (
        match_result.overall_status == "ineligible"
        and match_result.unfavorable_count > 0
        and match_result.state == "structured_safe"
    ):
        report["hard_blockers"].append({**base_entry, "kind": "hard_blocker", "outcome": "not_matched"})
    if (
        match_result.unknown_count > 0
        or match_result.requires_review_count > 0
        or (match_result.state not in {"structured_safe", "blocked_unsupported"})
    ):
        report["review_required"].append({**base_entry, "kind": "review_required", "outcome": "unknown"})
    return report


def _match_detail(match_result: MatchResult) -> MatchResultDetail:
    criteria = sorted(match_result.criteria, key=lambda criterion: (criterion.created_at, str(criterion.id)))
    gap_report_payload = match_result.gap_report_payload or _legacy_gap_report_payload(match_result)
    return MatchResultDetail(
        **_match_summary(match_result).model_dump(),
        criteria=[_build_match_criterion_response(criterion) for criterion in criteria],
        explanation=_build_match_explanation(criteria),
        gap_report=MatchGapReportResponse.model_validate(gap_report_payload),
    )


def _match_run_detail(match_run: MatchRun) -> MatchRunResponse:
    results = sorted(
        match_run.results,
        key=lambda result: (
            result.overall_status != "eligible",
            result.overall_status == "ineligible",
            -_match_metrics(result)["coverage_ratio"],
            -_match_metrics(result)["determinate_score"],
            result.trial.nct_id,
        ),
    )
    return MatchRunResponse(
        id=match_run.id,
        patient_id=match_run.patient_id,
        status=match_run.status,
        total_trials_evaluated=match_run.total_trials_evaluated,
        eligible_trials=match_run.eligible_trials,
        possible_trials=match_run.possible_trials,
        ineligible_trials=match_run.ineligible_trials,
        created_at=match_run.created_at,
        completed_at=match_run.completed_at,
        results=[_match_summary(result) for result in results],
    )
