from types import SimpleNamespace
from uuid import NAMESPACE_DNS, uuid5

import pytest

from app.api.schemas import MatchSimulationRequest, PatientBiomarkerInput, PatientMedicationInput, PatientTherapyInput
from app.matching.simulation import build_result_delta, build_simulated_patient, summarize_simulation_results
from app.models.database import Patient, PatientBiomarker, PatientMedication, PatientTherapy


def test_match_simulation_request_accepts_bounded_patient_fact_patch():
    payload = MatchSimulationRequest.model_validate(
        {
            "ecog_status": 1,
            "biomarkers": [{"description": "EGFR exon 19 deletion", "value_text": "positive"}],
            "medications": [{"description": "prednisone", "active": False}],
            "therapies": [{"description": "platinum chemotherapy", "line_of_therapy": 1, "completed": True}],
        }
    )

    assert payload.ecog_status == 1
    assert payload.biomarkers[0].description == "EGFR exon 19 deletion"
    assert payload.medications[0].active is False
    assert payload.therapies[0].line_of_therapy == 1


def test_match_simulation_request_rejects_out_of_range_ecog_status():
    with pytest.raises(Exception, match="ecog_status"):
        MatchSimulationRequest.model_validate({"ecog_status": 9})


def test_match_simulation_request_rejects_explicit_null_fields():
    with pytest.raises(Exception, match="Omit fields to preserve baseline"):
        MatchSimulationRequest.model_validate({"ecog_status": None})

    with pytest.raises(Exception, match="Omit fields to preserve baseline"):
        MatchSimulationRequest.model_validate({"biomarkers": None})


def test_build_simulated_patient_overlays_patch_without_mutating_baseline():
    patient = Patient(id="00000000-0000-0000-0000-000000000001", ecog_status=2)
    patient.biomarkers = [PatientBiomarker(description="EGFR wild type", value_text="negative")]
    patient.medications = [PatientMedication(description="prednisone", active=True)]
    patient.therapies = [PatientTherapy(description="radiation", completed=True)]

    simulated = build_simulated_patient(
        patient,
        MatchSimulationRequest(
            ecog_status=1,
            biomarkers=[PatientBiomarkerInput(description="EGFR exon 19 deletion", value_text="positive")],
            medications=[PatientMedicationInput(description="prednisone", active=False)],
            therapies=[PatientTherapyInput(description="platinum chemotherapy", line_of_therapy=1, completed=True)],
        ),
    )

    assert simulated is not patient
    assert simulated.id == patient.id
    assert simulated.ecog_status == 1
    assert [item.description for item in simulated.biomarkers] == ["EGFR exon 19 deletion"]
    assert simulated.medications[0].active is False
    assert [item.description for item in simulated.therapies] == ["platinum chemotherapy"]
    assert patient.ecog_status == 2
    assert [item.description for item in patient.biomarkers] == ["EGFR wild type"]
    assert patient.medications[0].active is True


def _result(trial_id, status, blockers=None, review_required_count=0, clarifiable=None, unsupported=None):
    trial_uuid = uuid5(NAMESPACE_DNS, f"simulation-trial-{trial_id}")
    return SimpleNamespace(
        trial=SimpleNamespace(id=trial_uuid, nct_id=f"NCT{trial_id}", brief_title=f"Trial {trial_id}"),
        trial_id=trial_uuid,
        overall_status=status,
        state="structured_safe",
        state_reason=None,
        score=1.0 if status == "eligible" else 0.0,
        favorable_count=1 if status == "eligible" else 0,
        unfavorable_count=1 if status == "ineligible" else 0,
        unknown_count=1 if status == "possible" else 0,
        requires_review_count=review_required_count,
        summary_explanation=f"{status} summary",
        gap_report_payload={
            "hard_blockers": [
                {"criterion_text": blocker, "category": "performance_status", "summary": blocker}
                for blocker in (blockers or [])
            ],
            "missing_data": [],
            "review_required": [],
            "clarifiable_blockers": [
                {"criterion_text": item, "category": "other", "summary": item} for item in (clarifiable or [])
            ],
            "unsupported": [
                {"criterion_text": item, "category": "other", "summary": item} for item in (unsupported or [])
            ],
        },
    )


def test_build_result_delta_classifies_status_and_blocker_changes():
    baseline = _result("1", "possible", blockers=["ECOG must be 0 to 1"])
    scenario = _result("1", "eligible")

    delta = build_result_delta(baseline, scenario)

    assert delta.status_changed is True
    assert delta.baseline_status == "possible"
    assert delta.scenario_status == "eligible"
    assert delta.blockers_removed == ["ECOG must be 0 to 1"]
    assert delta.blockers_added == []


def test_summarize_simulation_results_counts_newly_eligible_blocked_and_unchanged():
    summary = summarize_simulation_results(
        [
            _result("1", "possible"),
            _result("2", "eligible"),
            _result("3", "possible"),
        ],
        [
            _result("1", "eligible"),
            _result("2", "ineligible", blockers=["New blocker"]),
            _result("3", "possible"),
        ],
    )

    assert summary.newly_eligible == 1
    assert summary.newly_blocked == 1
    assert summary.status_changed == 2
    assert summary.unchanged == 1


def test_build_result_delta_includes_uncertainty_bucket_changes():
    baseline = _result("4", "possible", clarifiable=["Clarify steroid dose"], unsupported=["Unsupported washout rule"])
    scenario = _result("4", "possible", clarifiable=["Clarify lab timing"], unsupported=[])

    delta = build_result_delta(baseline, scenario)

    assert delta.status_changed is False
    assert delta.clarifiable_blockers_removed == ["Clarify steroid dose"]
    assert delta.clarifiable_blockers_added == ["Clarify lab timing"]
    assert delta.unsupported_removed == ["Unsupported washout rule"]
    assert delta.unsupported_added == []
