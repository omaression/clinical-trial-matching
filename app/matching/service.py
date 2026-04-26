import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

from sqlalchemy.orm import Session, selectinload

from app.api.state import criterion_state_from_extracted, match_state_from_evaluations
from app.matching.gap_report import build_gap_report_payload
from app.models.database import (
    ExtractedCriterion,
    MatchResult,
    MatchResultCriterion,
    MatchRun,
    Patient,
    PatientBiomarker,
    PatientCondition,
    PatientLab,
    PatientMedication,
    PatientTherapy,
    PipelineRun,
    Trial,
)
from app.time_utils import utc_now

_STATUS_ORDER = {
    "eligible": 0,
    "possible": 1,
    "ineligible": 2,
}


def _ranking_metrics(result: MatchResult) -> tuple[float, float]:
    deterministic_count = result.favorable_count + result.unfavorable_count
    unresolved_count = result.unknown_count + result.requires_review_count
    evaluated_count = deterministic_count + unresolved_count
    coverage_ratio = deterministic_count / evaluated_count if evaluated_count else 0.0
    return coverage_ratio, result.score
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


@dataclass
class CriterionEvaluation:
    criterion_id: object | None
    pipeline_run_id: object | None
    logic_group_id: object | None
    logic_operator: str | None
    source_type: str
    source_label: str
    criterion_type: str
    category: str
    criterion_text: str
    outcome: str
    state: str
    state_reason: str | None
    explanation_text: str
    explanation_type: str
    evidence_payload: dict[str, Any] | None = None


class PatientMatchService:
    def __init__(self, db: Session):
        self._db = db

    def get_patient(self, patient_id) -> Patient | None:
        return self._db.query(Patient).options(
            selectinload(Patient.conditions),
            selectinload(Patient.biomarkers),
            selectinload(Patient.labs),
            selectinload(Patient.therapies),
            selectinload(Patient.medications),
        ).filter(Patient.id == patient_id).first()

    def run_match(self, patient: Patient) -> MatchRun:
        trials = (
            self._db.query(Trial)
            .options(selectinload(Trial.criteria), selectinload(Trial.pipeline_runs))
            .order_by(Trial.nct_id.asc())
            .all()
        )

        match_run = MatchRun(patient_id=patient.id, status="running", created_at=utc_now())
        self._db.add(match_run)
        self._db.flush()

        summaries: list[MatchResult] = []
        for trial in trials:
            latest_run = _latest_completed_run(trial)
            evaluations = self._evaluate_trial(patient, trial, latest_run)
            if not evaluations:
                continue
            effective_evaluations = _collapse_logic_group_evaluations(evaluations)

            favorable_count = sum(
                1 for evaluation in effective_evaluations if evaluation.outcome in {"matched", "not_triggered"}
            )
            unfavorable_count = sum(
                1 for evaluation in effective_evaluations if evaluation.outcome in {"not_matched", "triggered"}
            )
            unknown_count = sum(1 for evaluation in effective_evaluations if evaluation.outcome == "unknown")
            requires_review_count = sum(
                1 for evaluation in effective_evaluations if evaluation.outcome == "requires_review"
            )

            if unfavorable_count > 0:
                overall_status = "ineligible"
            elif unknown_count > 0 or requires_review_count > 0:
                overall_status = "possible"
            else:
                overall_status = "eligible"

            deterministic_count = favorable_count + unfavorable_count
            score = favorable_count / deterministic_count if deterministic_count else 0.0
            summary_explanation = _build_summary_explanation(
                trial=trial,
                overall_status=overall_status,
                evaluations=effective_evaluations,
            )
            state, state_reason = match_state_from_evaluations(effective_evaluations)

            result = MatchResult(
                match_run_id=match_run.id,
                patient_id=patient.id,
                trial_id=trial.id,
                overall_status=overall_status,
                state=state,
                state_reason=state_reason,
                score=score,
                favorable_count=favorable_count,
                unfavorable_count=unfavorable_count,
                unknown_count=unknown_count,
                requires_review_count=requires_review_count,
                summary_explanation=summary_explanation,
                gap_report_payload=build_gap_report_payload(effective_evaluations),
                created_at=utc_now(),
            )
            self._db.add(result)
            self._db.flush()

            for evaluation in evaluations:
                evidence_payload = evaluation.evidence_payload
                if isinstance(evidence_payload, dict):
                    evidence_payload = {
                        **evidence_payload,
                        "snapshot_match_metadata": {
                            "logic_group_id": (
                                str(evaluation.logic_group_id) if evaluation.logic_group_id is not None else None
                            ),
                            "logic_operator": evaluation.logic_operator,
                        },
                    }
                self._db.add(
                    MatchResultCriterion(
                        match_result_id=result.id,
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
                        evidence_payload=evidence_payload,
                    )
                )

            summaries.append(result)

        summaries.sort(
            key=lambda result: (
                _STATUS_ORDER[result.overall_status],
                -_ranking_metrics(result)[0],
                -_ranking_metrics(result)[1],
                str(result.trial_id),
            )
        )
        match_run.total_trials_evaluated = len(summaries)
        match_run.eligible_trials = sum(1 for result in summaries if result.overall_status == "eligible")
        match_run.possible_trials = sum(1 for result in summaries if result.overall_status == "possible")
        match_run.ineligible_trials = sum(1 for result in summaries if result.overall_status == "ineligible")
        match_run.status = "completed"
        match_run.completed_at = utc_now()

        self._db.commit()
        self._db.refresh(match_run)
        return match_run

    def list_patient_matches(self, patient_id, *, page: int = 1, per_page: int = 20) -> tuple[list[MatchResult], int]:
        query = (
            self._db.query(MatchResult)
            .options(
                selectinload(MatchResult.trial),
                selectinload(MatchResult.match_run),
            )
            .filter(MatchResult.patient_id == patient_id)
            .order_by(MatchResult.created_at.desc(), MatchResult.id.desc())
        )
        total = query.count()
        items = query.offset((page - 1) * per_page).limit(per_page).all()
        return items, total

    def get_match_result(self, match_result_id) -> MatchResult | None:
        return (
            self._db.query(MatchResult)
            .options(
                selectinload(MatchResult.trial),
                selectinload(MatchResult.match_run),
                selectinload(MatchResult.criteria),
            )
            .filter(MatchResult.id == match_result_id)
            .first()
        )

    def _evaluate_trial(
        self,
        patient: Patient,
        trial: Trial,
        latest_run: PipelineRun | None,
    ) -> list[CriterionEvaluation]:
        evaluations: list[CriterionEvaluation] = []
        uses_structured_age = bool(trial.eligible_min_age or trial.eligible_max_age)
        uses_structured_sex = bool(trial.eligible_sex and trial.eligible_sex != "ALL")

        if uses_structured_age:
            outcome, explanation_text, evidence_payload = self._evaluate_structured_age(patient, trial)
            evaluations.append(
                CriterionEvaluation(
                    criterion_id=None,
                    pipeline_run_id=latest_run.id if latest_run else None,
                    logic_group_id=None,
                    logic_operator=None,
                    source_type="structured",
                    source_label="ClinicalTrials.gov",
                    criterion_type="inclusion",
                    category="age",
                    criterion_text="ClinicalTrials.gov structured age eligibility",
                    outcome=outcome,
                    state="structured_safe",
                    state_reason=None,
                    explanation_text=explanation_text,
                    explanation_type="structured_rule",
                    evidence_payload=evidence_payload,
                )
            )
        if uses_structured_sex:
            outcome, explanation_text, evidence_payload = self._evaluate_structured_sex(patient, trial)
            evaluations.append(
                CriterionEvaluation(
                    criterion_id=None,
                    pipeline_run_id=latest_run.id if latest_run else None,
                    logic_group_id=None,
                    logic_operator=None,
                    source_type="structured",
                    source_label="ClinicalTrials.gov",
                    criterion_type="inclusion",
                    category="sex",
                    criterion_text=f"ClinicalTrials.gov structured sex eligibility: {trial.eligible_sex}",
                    outcome=outcome,
                    state="structured_safe",
                    state_reason=None,
                    explanation_text=explanation_text,
                    explanation_type="structured_rule",
                    evidence_payload=evidence_payload,
                )
            )
        if trial.accepts_healthy is False:
            outcome, explanation_text, evidence_payload = self._evaluate_healthy_volunteer(patient)
            evaluations.append(
                CriterionEvaluation(
                    criterion_id=None,
                    pipeline_run_id=latest_run.id if latest_run else None,
                    logic_group_id=None,
                    logic_operator=None,
                    source_type="structured",
                    source_label="ClinicalTrials.gov",
                    criterion_type="inclusion",
                    category="healthy_volunteers",
                    criterion_text="ClinicalTrials.gov structured healthy volunteer restriction",
                    outcome=outcome,
                    state="structured_safe",
                    state_reason=None,
                    explanation_text=explanation_text,
                    explanation_type="structured_rule",
                    evidence_payload=evidence_payload,
                )
            )

        criteria = [
            criterion for criterion in trial.criteria
            if latest_run is None or criterion.pipeline_run_id == latest_run.id
        ]
        for criterion in criteria:
            if uses_structured_age and criterion.category == "age":
                continue
            if uses_structured_sex and criterion.category == "sex":
                continue
            if criterion.category in {"procedural_requirement", "disease_status"}:
                continue
            evaluations.append(self._evaluate_extracted_criterion(patient, criterion))

        return evaluations

    def _evaluate_structured_age(self, patient: Patient, trial: Trial) -> tuple[str, str, dict[str, Any]]:
        patient_age = _patient_age_years(patient.birth_date)
        evidence = {
            "minimum_age_years": _parse_age_years(trial.eligible_min_age),
            "maximum_age_years": _parse_age_years(trial.eligible_max_age),
            "patient_age_years": patient_age,
        }
        if patient_age is None:
            return (
                "unknown",
                "Patient birth date is unavailable, so age eligibility could not be evaluated.",
                evidence,
            )
        minimum_age = evidence["minimum_age_years"]
        maximum_age = evidence["maximum_age_years"]
        if minimum_age is not None and patient_age < minimum_age:
            return (
                "not_matched",
                f"Patient age {int(patient_age)} is below the minimum age {int(minimum_age)}.",
                evidence,
            )
        if maximum_age is not None and patient_age > maximum_age:
            return (
                "not_matched",
                f"Patient age {int(patient_age)} exceeds the maximum age {int(maximum_age)}.",
                evidence,
            )
        return "matched", f"Patient age {int(patient_age)} satisfies the structured age range.", evidence

    def _evaluate_structured_sex(self, patient: Patient, trial: Trial) -> tuple[str, str, dict[str, Any]]:
        evidence = {
            "required_sex": trial.eligible_sex,
            "patient_sex": patient.sex,
        }
        if not patient.sex:
            return (
                "unknown",
                "Patient sex is unavailable, so structured sex eligibility could not be evaluated.",
                evidence,
            )
        if not trial.eligible_sex or trial.eligible_sex == "ALL":
            return "matched", "Trial accepts all sexes in the structured eligibility fields.", evidence
        if patient.sex.casefold() == trial.eligible_sex.casefold():
            return (
                "matched",
                f"Patient sex {patient.sex} matches the structured requirement {trial.eligible_sex}.",
                evidence,
            )
        return (
            "not_matched",
            f"Patient sex {patient.sex} does not match the structured requirement {trial.eligible_sex}.",
            evidence,
        )

    def _evaluate_healthy_volunteer(self, patient: Patient) -> tuple[str, str, dict[str, Any]]:
        evidence = {"patient_is_healthy_volunteer": patient.is_healthy_volunteer}
        if patient.is_healthy_volunteer is None:
            return (
                "unknown",
                "Healthy volunteer status is unavailable, so the structured restriction could not be evaluated.",
                evidence,
            )
        if patient.is_healthy_volunteer:
            return (
                "not_matched",
                "Trial does not accept healthy volunteers and the patient is marked as a healthy volunteer.",
                evidence,
            )
        return (
            "matched",
            "Trial does not accept healthy volunteers and the patient is not marked as a healthy volunteer.",
            evidence,
        )

    def _evaluate_extracted_criterion(self, patient: Patient, criterion: ExtractedCriterion) -> CriterionEvaluation:
        state, state_reason = criterion_state_from_extracted(criterion)
        if criterion.review_required and criterion.review_status == "pending":
            outcome = "requires_review"
            explanation_text = "This criterion still requires manual review, so the patient match remains provisional."
            explanation_type = "review_required"
            evidence_payload = {
                "review_reason": criterion.review_reason,
                "review_status": criterion.review_status,
            }
        elif state == "blocked_unsupported":
            outcome = "unknown"
            explanation_text = "This criterion was rejected during review, so it is excluded from automated matching."
            explanation_type = "blocked_unsupported"
            evidence_payload = {
                "review_reason": criterion.review_reason,
                "review_status": criterion.review_status,
            }
        else:
            outcome = self._resolve_criterion_outcome(patient, criterion)
            explanation_text, explanation_type, evidence_payload = _build_extracted_explanation(
                criterion=criterion,
                outcome=outcome,
                patient=patient,
            )

        return CriterionEvaluation(
            criterion_id=criterion.id,
            pipeline_run_id=criterion.pipeline_run_id,
            logic_group_id=criterion.logic_group_id,
            logic_operator=criterion.logic_operator,
            source_type="extracted",
            source_label="criterion",
            criterion_type=criterion.type,
            category=criterion.category,
            criterion_text=criterion.original_text,
            outcome=outcome,
            state=state,
            state_reason=state_reason,
            explanation_text=explanation_text,
            explanation_type=explanation_type,
            evidence_payload=evidence_payload,
        )

    def _resolve_criterion_outcome(self, patient: Patient, criterion: ExtractedCriterion) -> str:
        outcome = None
        if criterion.category == "age":
            patient_age = _patient_age_years(patient.birth_date)
            if patient_age is not None:
                outcome = _criterion_boolean_outcome(
                    criterion.type,
                    _numeric_criterion_satisfied(criterion, patient_age),
                )
        elif criterion.category == "sex":
            if patient.sex:
                outcome = _criterion_boolean_outcome(
                    criterion.type,
                    _sex_matches(criterion, patient.sex),
                )
        elif criterion.category in {"diagnosis", "disease_stage", "histology", "cns_metastases", "other"}:
            outcome = _evaluate_fact_match(criterion, patient.conditions)
        elif criterion.category in {"biomarker", "molecular_alteration"}:
            outcome = _evaluate_fact_match(criterion, patient.biomarkers)
        elif criterion.category == "lab_value":
            outcome = _evaluate_lab_match(criterion, patient.labs)
        elif criterion.category in {"prior_therapy", "line_of_therapy"}:
            outcome = _evaluate_therapy_match(criterion, patient.therapies)
        elif criterion.category == "concomitant_medication":
            active_medications = [medication for medication in patient.medications if medication.active]
            outcome = _evaluate_medication_match(criterion, active_medications)
        elif criterion.category == "performance_status":
            if patient.ecog_status is not None:
                outcome = _criterion_boolean_outcome(
                    criterion.type,
                    _numeric_criterion_satisfied(criterion, float(patient.ecog_status)),
                )
        elif criterion.category == "administrative_requirement":
            outcome = _evaluate_patient_flag_match(criterion, patient)
        elif criterion.category == "behavioral_constraint":
            outcome = _evaluate_patient_flag_match(criterion, patient)
        elif criterion.category == "reproductive_status":
            outcome = _evaluate_patient_flag_match(criterion, patient)
        elif criterion.category == "device_constraint":
            outcome = _evaluate_patient_flag_match(criterion, patient)

        return outcome or "unknown"


def _latest_completed_run(trial: Trial) -> PipelineRun | None:
    completed_runs = [run for run in trial.pipeline_runs if run.status == "completed"]
    if not completed_runs:
        return None
    return sorted(
        completed_runs,
        key=lambda run: (
            run.finished_at or run.started_at,
            run.started_at,
            str(run.id),
        ),
        reverse=True,
    )[0]


def _evaluation_has_explicit_missing_patient_data(evaluation: CriterionEvaluation) -> bool:
    evidence = evaluation.evidence_payload
    if not isinstance(evidence, dict):
        return False

    scalar_patient_keys = (
        "patient_age_years",
        "patient_sex",
        "patient_is_healthy_volunteer",
        "patient_ecog_status",
    )
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

    if evaluation.category == "lab_value":
        labs = evidence.get("patient_labs")
        if (
            isinstance(labs, list)
            and labs
            and all(lab.get("value_numeric") is None for lab in labs if isinstance(lab, dict))
        ):
            return True

    if evaluation.category in {"prior_therapy", "line_of_therapy"}:
        therapies = evidence.get("patient_therapies")
        if isinstance(therapies, list) and therapies and all(
            therapy.get("line_of_therapy") is None for therapy in therapies if isinstance(therapy, dict)
        ):
            return True

    patient_flags = evidence.get("patient_flags")
    patient_flag_field = evidence.get("patient_flag_field")
    if isinstance(patient_flags, dict) and isinstance(patient_flag_field, str):
        if patient_flags.get(patient_flag_field) is None:
            return True

    if evaluation.category == "concomitant_medication":
        medications = evidence.get("patient_medications")
        if not isinstance(medications, list) or not medications:
            return True

    return False


def _collapse_logic_group_evaluations(evaluations: list[CriterionEvaluation]) -> list[CriterionEvaluation]:
    collapsed: list[CriterionEvaluation] = []
    grouped: dict[tuple[object, str], list[CriterionEvaluation]] = {}

    for evaluation in evaluations:
        if not evaluation.logic_group_id or evaluation.logic_operator != "OR":
            collapsed.append(evaluation)
            continue
        grouped.setdefault((evaluation.logic_group_id, evaluation.logic_operator), []).append(evaluation)

    for (_, _), members in grouped.items():
        collapsed.append(_collapse_or_group(members))

    return collapsed


def _collapse_or_group(evaluations: list[CriterionEvaluation]) -> CriterionEvaluation:
    exemplar = evaluations[0]
    outcomes = {evaluation.outcome for evaluation in evaluations}

    if exemplar.criterion_type == "inclusion":
        if "matched" in outcomes:
            outcome = "matched"
            explanation_text = "At least one OR-linked inclusion branch is satisfied."
            explanation_type = "logic_group_match"
        elif "requires_review" in outcomes:
            outcome = "requires_review"
            explanation_text = "An OR-linked inclusion branch still requires manual review."
            explanation_type = "logic_group_review_required"
        elif "unknown" in outcomes:
            outcome = "unknown"
            explanation_text = "Available patient data is insufficient to resolve an OR-linked inclusion branch."
            explanation_type = "logic_group_unknown"
        else:
            outcome = "not_matched"
            explanation_text = "None of the OR-linked inclusion branches are satisfied."
            explanation_type = "logic_group_mismatch"
    else:
        if "triggered" in outcomes:
            outcome = "triggered"
            explanation_text = "At least one OR-linked exclusion branch is triggered."
            explanation_type = "logic_group_blocker"
        elif "requires_review" in outcomes:
            outcome = "requires_review"
            explanation_text = "An OR-linked exclusion branch still requires manual review."
            explanation_type = "logic_group_review_required"
        elif "unknown" in outcomes:
            outcome = "unknown"
            explanation_text = "Available patient data is insufficient to resolve an OR-linked exclusion branch."
            explanation_type = "logic_group_unknown"
        else:
            outcome = "not_triggered"
            explanation_text = "None of the OR-linked exclusion branches are triggered."
            explanation_type = "logic_group_clear"

    matching_members = [evaluation for evaluation in evaluations if evaluation.outcome == outcome] or evaluations
    state_members = (
        evaluations
        if outcome in {"not_matched", "not_triggered", "unknown"}
        else matching_members
    )
    member_states = {evaluation.state for evaluation in state_members}
    member_texts = [evaluation.criterion_text for evaluation in evaluations]
    if outcome in {"not_matched", "not_triggered", "unknown"}:
        if "review_required" in member_states:
            state = "review_required"
            state_reason = "review_required"
        elif "blocked_unsupported" in member_states:
            state = "blocked_unsupported"
            state_reason = "blocked_unsupported"
        elif "structured_low_confidence" in member_states:
            state = "structured_low_confidence"
            state_reason = "low_confidence"
        elif "structured_safe" in member_states:
            state = "structured_safe"
            state_reason = None
        else:
            state = exemplar.state
            state_reason = exemplar.state_reason
    else:
        if "structured_safe" in member_states:
            state = "structured_safe"
            state_reason = None
        elif "structured_low_confidence" in member_states:
            state = "structured_low_confidence"
            state_reason = "low_confidence"
        elif "review_required" in member_states:
            state = "review_required"
            state_reason = "review_required"
        elif "blocked_unsupported" in member_states:
            state = "blocked_unsupported"
            state_reason = "blocked_unsupported"
        else:
            state = exemplar.state
            state_reason = exemplar.state_reason

    member_texts = [evaluation.criterion_text for evaluation in evaluations]
    return CriterionEvaluation(
        criterion_id=None,
        pipeline_run_id=exemplar.pipeline_run_id,
        logic_group_id=exemplar.logic_group_id,
        logic_operator=exemplar.logic_operator,
        source_type=exemplar.source_type,
        source_label=exemplar.source_label,
        criterion_type=exemplar.criterion_type,
        category=exemplar.category,
        criterion_text=" OR ".join(dict.fromkeys(member_texts)),
        outcome=outcome,
        state=state,
        state_reason=state_reason,
        explanation_text=explanation_text,
        explanation_type=explanation_type,
        evidence_payload={
            "logic_group_id": str(exemplar.logic_group_id),
            "logic_operator": exemplar.logic_operator,
            "member_outcomes": [evaluation.outcome for evaluation in evaluations],
            "member_states": [evaluation.state for evaluation in evaluations],
            "member_criterion_texts": member_texts,
            "member_categories": [evaluation.category for evaluation in evaluations],
            "snapshot_missing_data": any(
                _evaluation_has_explicit_missing_patient_data(evaluation) for evaluation in evaluations
            ),
        },
    )


def _patient_age_years(birth_date: date | None) -> float | None:
    if birth_date is None:
        return None
    today = utc_now().date()
    years = today.year - birth_date.year
    before_birthday = (today.month, today.day) < (birth_date.month, birth_date.day)
    return float(years - int(before_birthday))


def _parse_age_years(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", value)
    if not match:
        return None
    return float(match.group(1))


def _evaluate_patient_flag_match(criterion: ExtractedCriterion, patient: Patient) -> str | None:
    flag_match = _parse_patient_flag_expression(criterion.value_text)
    if not flag_match:
        return None

    field_name, expected_value = flag_match
    actual_value = getattr(patient, field_name, None)
    if actual_value is None:
        return None
    return _criterion_boolean_outcome(criterion.type, actual_value is expected_value)


def _parse_patient_flag_expression(value_text: str | None) -> tuple[str, bool] | None:
    if not value_text or ":" not in value_text:
        return None
    field_name, raw_value = value_text.split(":", 1)
    normalized_field = field_name.strip()
    normalized_value = raw_value.strip().casefold()
    if normalized_value not in {"true", "false"}:
        return None
    return normalized_field, normalized_value == "true"


def _sex_matches(criterion: ExtractedCriterion, patient_sex: str) -> bool | None:
    expected = (criterion.value_text or criterion.raw_expression or criterion.original_text).casefold()
    if "female" in expected:
        return patient_sex.casefold() == "female"
    if "male" in expected:
        return patient_sex.casefold() == "male"
    return None


def _numeric_criterion_satisfied(criterion: ExtractedCriterion, actual_value: float) -> bool | None:
    operator = criterion.operator
    low = criterion.value_low
    high = criterion.value_high
    if operator == "gte" and low is not None:
        return actual_value >= low
    if operator == "gt" and low is not None:
        return actual_value > low
    if operator == "lte" and low is not None:
        return actual_value <= low
    if operator == "lt" and low is not None:
        return actual_value < low
    if operator == "eq" and low is not None:
        return actual_value == low
    if operator == "neq" and low is not None:
        return actual_value != low
    if operator == "between":
        if low is not None and actual_value < low:
            return False
        if high is not None and actual_value > high:
            return False
        return True
    if low is not None and high is not None:
        return low <= actual_value <= high
    return None


def _criterion_boolean_outcome(criterion_type: str, satisfied: bool | None) -> str | None:
    if satisfied is None:
        return None
    if criterion_type == "inclusion":
        return "matched" if satisfied else "not_matched"
    return "triggered" if satisfied else "not_triggered"


def _evaluate_fact_match(
    criterion: ExtractedCriterion,
    facts: Iterable[PatientCondition | PatientBiomarker | PatientMedication],
) -> str | None:
    facts = list(facts)
    if not facts:
        return None
    matched = any(_fact_matches_criterion(fact, criterion) for fact in facts)
    return _criterion_boolean_outcome(criterion.type, matched)


def _evaluate_medication_match(
    criterion: ExtractedCriterion,
    medications: Iterable[PatientMedication],
) -> str | None:
    medications = list(medications)
    if not medications:
        return None

    matching_medications = [
        medication for medication in medications if _fact_matches_criterion(medication, criterion)
    ]
    if not matching_medications:
        return _criterion_boolean_outcome(criterion.type, False)

    exception_entities = getattr(criterion, "exception_entities", None) or []
    allowance_text = getattr(criterion, "allowance_text", None)
    has_timeframe = (
        getattr(criterion, "timeframe_operator", None)
        or getattr(criterion, "timeframe_value", None) is not None
        or getattr(criterion, "timeframe_unit", None)
    )

    disallowed_matches: list[PatientMedication] = []
    requires_additional_context = False
    for medication in matching_medications:
        if _medication_matches_any_exception(medication, exception_entities):
            continue
        if allowance_text:
            if _medication_matches_allowance(medication, allowance_text):
                continue
            requires_additional_context = True
            continue
        if has_timeframe:
            requires_additional_context = True
            continue
        disallowed_matches.append(medication)

    if disallowed_matches:
        return _criterion_boolean_outcome(criterion.type, True)
    if requires_additional_context:
        return None
    return _criterion_boolean_outcome(criterion.type, False)


def _evaluate_lab_match(criterion: ExtractedCriterion, labs: Iterable[PatientLab]) -> str | None:
    labs = list(labs)
    if not labs:
        return None
    matching_labs = [lab for lab in labs if _fact_matches_criterion(lab, criterion)]
    if not matching_labs:
        return _criterion_boolean_outcome(criterion.type, False)
    if all(lab.value_numeric is None for lab in matching_labs):
        return None

    satisfied = any(
        _numeric_criterion_satisfied(criterion, float(lab.value_numeric)) is True
        for lab in matching_labs
        if lab.value_numeric is not None
    )
    if not satisfied and any(lab.value_numeric is not None for lab in matching_labs):
        return _criterion_boolean_outcome(criterion.type, False)
    return _criterion_boolean_outcome(criterion.type, satisfied)


def _evaluate_therapy_match(criterion: ExtractedCriterion, therapies: Iterable[PatientTherapy]) -> str | None:
    therapies = list(therapies)
    if not therapies:
        return None
    if criterion.category == "line_of_therapy":
        line_values = [therapy.line_of_therapy for therapy in therapies if therapy.line_of_therapy is not None]
        if not line_values:
            return None
        max_line = float(max(line_values))
        satisfied = _numeric_criterion_satisfied(criterion, max_line)
        if satisfied is None:
            satisfied = max_line > 0
        return _criterion_boolean_outcome(criterion.type, satisfied)

    matched = any(_fact_matches_criterion(therapy, criterion) for therapy in therapies)
    return _criterion_boolean_outcome(criterion.type, matched)


def _fact_matches_criterion(
    fact: PatientCondition | PatientBiomarker | PatientLab | PatientMedication | PatientTherapy,
    criterion: ExtractedCriterion,
) -> bool:
    criterion_codes = _coded_concept_keys(criterion.coded_concepts)
    fact_codes = _coded_concept_keys(getattr(fact, "coded_concepts", None))
    if criterion_codes and fact_codes and criterion_codes.intersection(fact_codes):
        return True

    criterion_text = criterion.value_text or criterion.raw_expression or criterion.original_text
    return _text_overlaps(criterion_text, fact.description)


def _coded_concept_keys(concepts) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    if not isinstance(concepts, list):
        return keys
    for concept in concepts:
        if not isinstance(concept, dict):
            continue
        system = concept.get("system")
        code = concept.get("code")
        if system and code:
            keys.add((str(system).casefold(), str(code).casefold()))
    return keys


def _text_overlaps(left: str | None, right: str | None) -> bool:
    left_tokens = _normalized_tokens(left)
    right_tokens = _normalized_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    if left_tokens <= right_tokens or right_tokens <= left_tokens:
        return True
    return len(left_tokens.intersection(right_tokens)) >= 2


def _medication_matches_any_exception(medication: PatientMedication, exception_entities: list[str]) -> bool:
    return any(_text_overlaps(exception_entity, medication.description) for exception_entity in exception_entities)


def _medication_matches_allowance(medication: PatientMedication, allowance_text: str | None) -> bool:
    if not allowance_text:
        return False
    allowance = allowance_text.casefold()
    description = (medication.description or "").casefold()
    if "physiologic" in allowance or "physiological" in allowance:
        return any(token in description for token in ("physiologic", "physiological", "replacement", "maintenance"))
    return _text_overlaps(allowance_text, medication.description)


def _normalized_tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    return {token for token in _TOKEN_PATTERN.findall(text.casefold()) if token}


def _build_extracted_explanation(
    *,
    criterion: ExtractedCriterion,
    outcome: str,
    patient: Patient,
) -> tuple[str, str, dict[str, Any]]:
    evidence = {
        "criterion_operator": criterion.operator,
        "criterion_value_low": criterion.value_low,
        "criterion_value_high": criterion.value_high,
        "criterion_value_text": criterion.value_text,
        "criterion_coded_concepts": criterion.coded_concepts,
        "specimen_type": getattr(criterion, "specimen_type", None),
        "testing_modality": getattr(criterion, "testing_modality", None),
        "assay_context": getattr(criterion, "assay_context", None),
        "disease_subtype": getattr(criterion, "disease_subtype", None),
        "histology_text": getattr(criterion, "histology_text", None),
        "secondary_semantic_tags": getattr(criterion, "secondary_semantic_tags", None),
    }

    if criterion.category == "lab_value":
        patient_labs = [
            {
                "description": lab.description,
                "value_numeric": lab.value_numeric,
                "value_text": lab.value_text,
                "unit": lab.unit,
                "coded_concepts": lab.coded_concepts,
            }
            for lab in patient.labs
        ]
        evidence["patient_labs"] = patient_labs
    elif criterion.category == "biomarker":
        evidence["patient_biomarkers"] = [
            {
                "description": biomarker.description,
                "value_text": biomarker.value_text,
                "coded_concepts": biomarker.coded_concepts,
            }
            for biomarker in patient.biomarkers
        ]
    elif criterion.category in {"prior_therapy", "line_of_therapy"}:
        evidence["patient_therapies"] = [
            {
                "description": therapy.description,
                "line_of_therapy": therapy.line_of_therapy,
                "completed": therapy.completed,
                "coded_concepts": therapy.coded_concepts,
            }
            for therapy in patient.therapies
        ]
    elif criterion.category == "concomitant_medication":
        evidence["patient_medications"] = [
            {
                "description": medication.description,
                "active": medication.active,
                "coded_concepts": medication.coded_concepts,
            }
            for medication in patient.medications
        ]
        evidence["exception_logic"] = getattr(criterion, "exception_logic", None)
        evidence["exception_entities"] = getattr(criterion, "exception_entities", None)
        evidence["allowance_text"] = getattr(criterion, "allowance_text", None)
    elif criterion.category in {
        "administrative_requirement",
        "behavioral_constraint",
        "reproductive_status",
        "device_constraint",
    }:
        evidence["patient_flags"] = {
            "can_consent": patient.can_consent,
            "protocol_compliant": patient.protocol_compliant,
            "claustrophobic": patient.claustrophobic,
            "motion_intolerant": patient.motion_intolerant,
            "pregnant": patient.pregnant,
            "mr_device_present": patient.mr_device_present,
        }
        parsed_flag = _parse_patient_flag_expression(criterion.value_text)
        evidence["patient_flag_field"] = parsed_flag[0] if parsed_flag is not None else None
    elif criterion.category in {"performance_status"}:
        evidence["patient_ecog_status"] = patient.ecog_status
    else:
        evidence["patient_conditions"] = [
            {
                "description": condition.description,
                "coded_concepts": condition.coded_concepts,
            }
            for condition in patient.conditions
        ]

    if outcome == "matched":
        return (
            "Patient data satisfies this inclusion criterion.",
            "criterion_match",
            evidence,
        )
    if outcome == "not_matched":
        return (
            "Patient data does not satisfy this inclusion criterion.",
            "criterion_mismatch",
            evidence,
        )
    if outcome == "triggered":
        return (
            "Patient data triggers this exclusion criterion.",
            "criterion_blocker",
            evidence,
        )
    if outcome == "not_triggered":
        return (
            "Patient data does not trigger this exclusion criterion.",
            "criterion_clear",
            evidence,
        )
    return (
        "Available patient data is insufficient to evaluate this criterion safely.",
        "criterion_unknown",
        evidence,
    )


def _build_summary_explanation(
    *,
    trial: Trial,
    overall_status: str,
    evaluations: list[CriterionEvaluation],
) -> str:
    blockers = [
        evaluation.category for evaluation in evaluations if evaluation.outcome in {"not_matched", "triggered"}
    ]
    unresolved = [
        evaluation.category for evaluation in evaluations if evaluation.outcome in {"unknown", "requires_review"}
    ]
    review_required = [evaluation.category for evaluation in evaluations if evaluation.state == "review_required"]
    blocked = [evaluation.category for evaluation in evaluations if evaluation.state == "blocked_unsupported"]
    favorable = [
        evaluation.category for evaluation in evaluations if evaluation.outcome in {"matched", "not_triggered"}
    ]

    if overall_status == "ineligible":
        blocker_text = ", ".join(blockers[:2]) if blockers else "blocking criteria"
        return f"{trial.brief_title} is ineligible because of {blocker_text}."
    if review_required:
        unresolved_text = ", ".join(review_required[:2]) if review_required else "review-pending criteria"
        return f"{trial.brief_title} remains a possible match pending manual review of {unresolved_text}."
    if blocked:
        blocked_text = ", ".join(blocked[:2]) if blocked else "unsupported criteria"
        return (
            f"{trial.brief_title} remains a possible match because {blocked_text} were rejected or unsupported "
            "and excluded from automated matching."
        )
    if overall_status == "possible":
        unresolved_text = ", ".join(unresolved[:2]) if unresolved else "unresolved criteria"
        return f"{trial.brief_title} remains a possible match pending {unresolved_text}."
    return f"{trial.brief_title} is eligible based on {len(favorable)} favorable criteria and no blockers."
