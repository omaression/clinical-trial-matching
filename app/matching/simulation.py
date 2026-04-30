from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from app.api.schemas import (
    MatchSimulationAppliedChanges,
    MatchSimulationRequest,
    MatchSimulationResultDelta,
    MatchSimulationSummary,
)
from app.models.database import Patient, PatientBiomarker, PatientLab, PatientMedication, PatientTherapy

_STATUS_RANK = {"ineligible": 0, "possible": 1, "eligible": 2}
_GAP_BUCKETS = {
    "hard_blockers": "blockers",
    "missing_data": "missing_data",
    "clarifiable_blockers": "clarifiable_blockers",
    "unsupported": "unsupported",
    "review_required": "review_required",
}


def build_simulated_patient(patient: Patient, patch: MatchSimulationRequest) -> Patient:
    simulated = Patient(
        id=patient.id,
        external_id=patient.external_id,
        sex=patient.sex,
        birth_date=patient.birth_date,
        ecog_status=patient.ecog_status if patch.ecog_status is None else patch.ecog_status,
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
    simulated.conditions = [
        type(condition)(description=condition.description, coded_concepts=condition.coded_concepts or [])
        for condition in patient.conditions
    ]
    simulated.biomarkers = (
        [_biomarker_from_input(item) for item in patch.biomarkers]
        if patch.biomarkers is not None
        else [_copy_biomarker(item) for item in patient.biomarkers]
    )
    simulated.labs = (
        [_lab_from_input(item) for item in patch.labs]
        if patch.labs is not None
        else [_copy_lab(item) for item in patient.labs]
    )
    simulated.therapies = (
        [_therapy_from_input(item) for item in patch.therapies]
        if patch.therapies is not None
        else [_copy_therapy(item) for item in patient.therapies]
    )
    simulated.medications = (
        [_medication_from_input(item) for item in patch.medications]
        if patch.medications is not None
        else [_copy_medication(item) for item in patient.medications]
    )
    return simulated


def applied_changes_from_request(patch: MatchSimulationRequest) -> MatchSimulationAppliedChanges:
    data = {field: getattr(patch, field) for field in patch.model_fields_set}
    return MatchSimulationAppliedChanges.model_validate(data)


def summarize_source_results(results: Iterable[Any], source: str) -> MatchSimulationSummary:
    items = list(results)
    counts = Counter(item.overall_status for item in items)
    return MatchSimulationSummary(
        total_trials=len(items),
        eligible=counts["eligible"],
        possible=counts["possible"],
        ineligible=counts["ineligible"],
        review_required=sum(1 for item in items if getattr(item, "requires_review_count", 0)),
        source=source,
    )


def summarize_simulation_results(
    baseline_results: Iterable[Any], scenario_results: Iterable[Any]
) -> MatchSimulationSummary:
    baseline_by_trial = {_trial_key(result): result for result in baseline_results}
    scenario_by_trial = {_trial_key(result): result for result in scenario_results}
    all_keys = sorted(set(baseline_by_trial) | set(scenario_by_trial), key=str)
    status_changed = 0
    newly_eligible = 0
    newly_blocked = 0
    unchanged = 0
    review_required = 0
    scenario_status_counts: Counter[str] = Counter()
    for key in all_keys:
        baseline = baseline_by_trial.get(key)
        scenario = scenario_by_trial.get(key)
        baseline_status = getattr(baseline, "overall_status", None)
        scenario_status = getattr(scenario, "overall_status", None)
        if scenario_status:
            scenario_status_counts[scenario_status] += 1
        if scenario and getattr(scenario, "requires_review_count", 0):
            review_required += 1
        if baseline_status == scenario_status:
            unchanged += 1
        else:
            status_changed += 1
            if _became_more_eligible(baseline_status, scenario_status):
                newly_eligible += 1
            if _became_more_blocked(baseline_status, scenario_status):
                newly_blocked += 1
    return MatchSimulationSummary(
        total_trials=len(all_keys),
        eligible=scenario_status_counts["eligible"],
        possible=scenario_status_counts["possible"],
        ineligible=scenario_status_counts["ineligible"],
        newly_eligible=newly_eligible,
        newly_blocked=newly_blocked,
        status_changed=status_changed,
        unchanged=unchanged,
        review_required=review_required,
        source="simulated",
    )


def build_result_delta(baseline: Any | None, scenario: Any | None) -> MatchSimulationResultDelta:
    representative = scenario or baseline
    baseline_status = getattr(baseline, "overall_status", None)
    scenario_status = getattr(scenario, "overall_status", None)
    removed_added: dict[str, tuple[list[str], list[str]]] = {}
    for bucket, label in _GAP_BUCKETS.items():
        before = set(_gap_texts(getattr(baseline, "gap_report_payload", None), bucket)) if baseline else set()
        after = set(_gap_texts(getattr(scenario, "gap_report_payload", None), bucket)) if scenario else set()
        removed_added[label] = (sorted(before - after), sorted(after - before))
    return MatchSimulationResultDelta(
        trial_id=getattr(representative.trial, "id", representative.trial_id),
        trial_nct_id=representative.trial.nct_id,
        trial_brief_title=representative.trial.brief_title,
        baseline_status=baseline_status,
        scenario_status=scenario_status,
        status_changed=baseline_status != scenario_status,
        blockers_removed=removed_added["blockers"][0],
        blockers_added=removed_added["blockers"][1],
        missing_data_removed=removed_added["missing_data"][0],
        missing_data_added=removed_added["missing_data"][1],
        clarifiable_blockers_removed=removed_added["clarifiable_blockers"][0],
        clarifiable_blockers_added=removed_added["clarifiable_blockers"][1],
        unsupported_removed=removed_added["unsupported"][0],
        unsupported_added=removed_added["unsupported"][1],
        review_required_removed=removed_added["review_required"][0],
        review_required_added=removed_added["review_required"][1],
        baseline_summary_explanation=getattr(baseline, "summary_explanation", None),
        scenario_summary_explanation=getattr(scenario, "summary_explanation", None),
    )


def build_result_deltas(
    baseline_results: Iterable[Any], scenario_results: Iterable[Any]
) -> list[MatchSimulationResultDelta]:
    baseline_by_trial = {_trial_key(result): result for result in baseline_results}
    scenario_by_trial = {_trial_key(result): result for result in scenario_results}
    deltas = [
        build_result_delta(baseline_by_trial.get(key), scenario_by_trial.get(key))
        for key in set(baseline_by_trial) | set(scenario_by_trial)
    ]
    return sorted(
        deltas,
        key=lambda item: (
            not item.status_changed,
            -int(item.scenario_status == "eligible"),
            item.trial_nct_id,
        ),
    )


def _trial_key(result: Any) -> Any:
    return getattr(result, "trial_id", None) or result.trial.id


def _gap_texts(payload: Any, bucket: str) -> list[str]:
    if not isinstance(payload, dict):
        return []
    entries = payload.get(bucket) or []
    texts = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        text = entry.get("criterion_text") or entry.get("summary") or entry.get("category")
        if isinstance(text, str) and text.strip():
            texts.append(text.strip())
    return texts


def _became_more_eligible(baseline_status: str | None, scenario_status: str | None) -> bool:
    if baseline_status is None or scenario_status is None:
        return False
    return _STATUS_RANK[scenario_status] > _STATUS_RANK[baseline_status]


def _became_more_blocked(baseline_status: str | None, scenario_status: str | None) -> bool:
    if baseline_status is None or scenario_status is None:
        return False
    return _STATUS_RANK[scenario_status] < _STATUS_RANK[baseline_status]


def _copy_biomarker(item: PatientBiomarker) -> PatientBiomarker:
    return PatientBiomarker(
        description=item.description, coded_concepts=item.coded_concepts or [], value_text=item.value_text
    )


def _copy_lab(item: PatientLab) -> PatientLab:
    return PatientLab(
        description=item.description,
        coded_concepts=item.coded_concepts or [],
        value_numeric=item.value_numeric,
        value_text=item.value_text,
        unit=item.unit,
    )


def _copy_therapy(item: PatientTherapy) -> PatientTherapy:
    return PatientTherapy(
        description=item.description,
        coded_concepts=item.coded_concepts or [],
        line_of_therapy=item.line_of_therapy,
        completed=item.completed,
    )


def _copy_medication(item: PatientMedication) -> PatientMedication:
    return PatientMedication(description=item.description, coded_concepts=item.coded_concepts or [], active=item.active)


def _biomarker_from_input(item) -> PatientBiomarker:
    return PatientBiomarker(
        description=item.description, coded_concepts=item.model_dump()["coded_concepts"], value_text=item.value_text
    )


def _lab_from_input(item) -> PatientLab:
    return PatientLab(
        description=item.description,
        coded_concepts=item.model_dump()["coded_concepts"],
        value_numeric=item.value_numeric,
        value_text=item.value_text,
        unit=item.unit,
    )


def _therapy_from_input(item) -> PatientTherapy:
    return PatientTherapy(
        description=item.description,
        coded_concepts=item.model_dump()["coded_concepts"],
        line_of_therapy=item.line_of_therapy,
        completed=item.completed,
    )


def _medication_from_input(item) -> PatientMedication:
    return PatientMedication(
        description=item.description, coded_concepts=item.model_dump()["coded_concepts"], active=item.active
    )
