import uuid
from datetime import date

import docker
import pytest

from app.models.database import ExtractedCriterion, MatchResult, PipelineRun, Trial


def _docker_available():
    try:
        docker.from_env().ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _docker_available(), reason="Docker not available")


def _seed_trial_with_run(db_session, *, nct_id: str, sex: str, criteria_payloads: list[dict]):
    trial = Trial(
        nct_id=nct_id,
        raw_json={"protocolSection": {"eligibilityModule": {"eligibilityCriteria": "Test criteria"}}},
        content_hash=f"hash-{nct_id}",
        brief_title=f"Trial {nct_id}",
        official_title=f"Official {nct_id}",
        status="RECRUITING",
        phase="PHASE2",
        conditions=["Breast Cancer"],
        eligibility_text="Test criteria",
        eligible_min_age="18 Years",
        eligible_max_age="75 Years",
        eligible_sex=sex,
        sponsor="Test Sponsor",
    )
    db_session.add(trial)
    db_session.flush()

    run = PipelineRun(
        trial_id=trial.id,
        pipeline_version="0.1.1",
        input_hash=f"input-{nct_id}",
        input_snapshot=trial.raw_json,
        status="completed",
        criteria_extracted_count=len(criteria_payloads),
        review_required_count=sum(1 for payload in criteria_payloads if payload.get("review_required")),
    )
    db_session.add(run)
    db_session.flush()

    for payload in criteria_payloads:
        criterion_payload = {
            "trial_id": trial.id,
            "parse_status": "parsed",
            "negated": False,
            "confidence": 0.95,
            "review_required": False,
            "review_status": None,
            "coded_concepts": [],
            "pipeline_version": "0.1.1",
            "pipeline_run_id": run.id,
            **payload,
        }
        if criterion_payload["review_required"] and criterion_payload["review_status"] is None:
            criterion_payload["review_status"] = "pending"
        db_session.add(
            ExtractedCriterion(
                **criterion_payload,
            )
        )

    db_session.commit()
    return trial


class TestPatientEndpoints:
    def test_create_and_fetch_patient(self, client):
        response = client.post(
            "/api/v1/patients",
            json={
                "external_id": "pt-001",
                "sex": "female",
                "birth_date": "1985-01-01",
                "ecog_status": 1,
                "can_consent": True,
                "protocol_compliant": True,
                "claustrophobic": False,
                "motion_intolerant": False,
                "pregnant": False,
                "mr_device_present": False,
                "conditions": [
                    {
                        "description": "Metastatic breast cancer",
                        "coded_concepts": [{"system": "mesh", "code": "D001943", "display": "Breast Neoplasms"}],
                    }
                ],
                "biomarkers": [
                    {
                        "description": "HER2 Positive",
                        "coded_concepts": [{"system": "nci_thesaurus", "code": "C68748", "display": "HER2 Positive"}],
                    }
                ],
                "labs": [
                    {
                        "description": "ANC",
                        "coded_concepts": [
                            {
                                "system": "loinc",
                                "code": "751-8",
                                "display": "Neutrophils [#/volume] in Blood",
                            }
                        ],
                        "value_numeric": 1800,
                        "unit": "cells/uL",
                    }
                ],
            },
        )
        assert response.status_code == 201
        patient_id = response.json()["id"]
        assert response.json()["conditions"][0]["description"] == "Metastatic breast cancer"
        assert response.json()["can_consent"] is True
        assert response.json()["mr_device_present"] is False

        fetched = client.get(f"/api/v1/patients/{patient_id}")
        assert fetched.status_code == 200
        assert fetched.json()["biomarkers"][0]["coded_concepts"][0]["code"] == "C68748"
        assert fetched.json()["protocol_compliant"] is True

    def test_patch_patient_replaces_nested_fact_lists(self, client):
        created = client.post(
            "/api/v1/patients",
            json={
                "external_id": "pt-002",
                "sex": "female",
                "conditions": [{"description": "Breast cancer"}],
                "medications": [{"description": "Trastuzumab", "active": True}],
            },
        )
        patient_id = created.json()["id"]

        response = client.patch(
            f"/api/v1/patients/{patient_id}",
            json={
                "medications": [{"description": "Capecitabine", "active": True}],
            },
        )
        assert response.status_code == 200
        assert [item["description"] for item in response.json()["medications"]] == ["Capecitabine"]


class TestPatientMatching:
    def test_match_patient_uses_structured_precedence_and_persists_results(self, client, db_session):
        eligible_trial = _seed_trial_with_run(
            db_session,
            nct_id="NCT10000001",
            sex="FEMALE",
            criteria_payloads=[
                {
                    "type": "inclusion",
                    "category": "sex",
                    "original_text": "Male patients only",
                    "value_text": "Male patients only",
                },
                {
                    "type": "inclusion",
                    "category": "diagnosis",
                    "original_text": "Metastatic breast cancer",
                    "coded_concepts": [
                        {"system": "mesh", "code": "D001943", "display": "Breast Neoplasms"}
                    ],
                },
                {
                    "type": "inclusion",
                    "category": "molecular_alteration",
                    "original_text": "HER2-positive disease",
                    "coded_concepts": [
                        {"system": "nci_thesaurus", "code": "C68748", "display": "HER2 Positive"}
                    ],
                },
                {
                    "type": "inclusion",
                    "category": "biomarker",
                    "original_text": "HER2-positive disease",
                    "coded_concepts": [
                        {"system": "nci_thesaurus", "code": "C68748", "display": "HER2 Positive"}
                    ],
                },
                {
                    "type": "inclusion",
                    "category": "lab_value",
                    "original_text": "ANC >= 1500",
                    "operator": "gte",
                    "value_low": 1500,
                    "coded_concepts": [
                        {"system": "loinc", "code": "751-8", "display": "Neutrophils [#/volume] in Blood"}
                    ],
                },
            ],
        )
        _seed_trial_with_run(
            db_session,
            nct_id="NCT10000002",
            sex="MALE",
            criteria_payloads=[],
        )
        _seed_trial_with_run(
            db_session,
            nct_id="NCT10000003",
            sex="ALL",
            criteria_payloads=[
                {
                    "type": "exclusion",
                    "category": "concomitant_medication",
                    "original_text": "Concurrent CYP3A4 inhibitor use",
                    "review_required": True,
                },
            ],
        )
        _seed_trial_with_run(
            db_session,
            nct_id="NCT10000009",
            sex="ALL",
            criteria_payloads=[
                {
                    "type": "inclusion",
                    "category": "diagnosis",
                    "original_text": "Metastatic breast cancer",
                    "coded_concepts": [
                        {"system": "mesh", "code": "D001943", "display": "Breast Neoplasms"}
                    ],
                },
                {
                    "type": "exclusion",
                    "category": "concomitant_medication",
                    "original_text": "Concurrent CYP3A4 inhibitor use",
                    "review_required": True,
                },
            ],
        )

        patient = client.post(
            "/api/v1/patients",
            json={
                "external_id": "pt-match-001",
                "sex": "female",
                "birth_date": str(date(1985, 1, 1)),
                "conditions": [
                    {
                        "description": "Metastatic breast cancer",
                        "coded_concepts": [{"system": "mesh", "code": "D001943", "display": "Breast Neoplasms"}],
                    }
                ],
                "biomarkers": [
                    {
                        "description": "HER2 Positive",
                        "coded_concepts": [{"system": "nci_thesaurus", "code": "C68748", "display": "HER2 Positive"}],
                    }
                ],
                "labs": [
                    {
                        "description": "ANC",
                        "coded_concepts": [
                            {
                                "system": "loinc",
                                "code": "751-8",
                                "display": "Neutrophils [#/volume] in Blood",
                            }
                        ],
                        "value_numeric": 1800,
                        "unit": "cells/uL",
                    }
                ],
            },
        )
        patient_id = patient.json()["id"]
        total_trials = db_session.query(Trial).count()

        response = client.post(f"/api/v1/patients/{patient_id}/match")
        assert response.status_code == 200
        data = response.json()
        assert data["total_trials_evaluated"] == total_trials
        assert data["eligible_trials"] >= 1
        assert data["possible_trials"] >= 1
        assert data["ineligible_trials"] >= 1

        ranked = {item["trial_nct_id"]: item for item in data["results"]}
        assert ranked["NCT10000001"]["overall_status"] == "eligible"
        assert ranked["NCT10000001"]["score"] == 1.0
        assert ranked["NCT10000001"]["determinate_score"] == 1.0
        assert ranked["NCT10000001"]["coverage_ratio"] == 1.0
        assert ranked["NCT10000001"]["deterministic_count"] == (
            ranked["NCT10000001"]["favorable_count"] + ranked["NCT10000001"]["unfavorable_count"]
        )
        assert ranked["NCT10000001"]["unresolved_count"] == 0
        assert "eligible" in ranked["NCT10000001"]["summary_explanation"].casefold()
        assert ranked["NCT10000002"]["overall_status"] == "ineligible"
        assert ranked["NCT10000003"]["overall_status"] == "possible"
        assert ranked["NCT10000003"]["requires_review_count"] == 1
        assert ranked["NCT10000003"]["determinate_score"] == 1.0
        assert ranked["NCT10000003"]["coverage_ratio"] < 1.0
        assert ranked["NCT10000003"]["unresolved_count"] == 1

        possible_order = [item["trial_nct_id"] for item in data["results"] if item["overall_status"] == "possible"]
        assert possible_order.index("NCT10000009") < possible_order.index("NCT10000003")

        stored = db_session.query(MatchResult).filter(MatchResult.trial_id == eligible_trial.id).first()
        assert stored is not None

        detail = client.get(f"/api/v1/matches/{ranked['NCT10000001']['id']}")
        assert detail.status_code == 200
        outcomes = {(item["source_type"], item["category"]): item["outcome"] for item in detail.json()["criteria"]}
        assert outcomes[("structured", "sex")] == "matched"
        assert outcomes[("structured", "age")] == "matched"
        assert outcomes[("extracted", "diagnosis")] == "matched"
        assert outcomes[("extracted", "molecular_alteration")] == "matched"
        assert outcomes[("extracted", "biomarker")] == "matched"
        assert outcomes[("extracted", "lab_value")] == "matched"
        assert ("extracted", "sex") not in outcomes
        structured_sex = next(
            item
            for item in detail.json()["criteria"]
            if item["source_type"] == "structured" and item["category"] == "sex"
        )
        assert structured_sex["explanation_type"] == "structured_rule"
        assert structured_sex["evidence_payload"]["required_sex"] == "FEMALE"

        listing = client.get(f"/api/v1/patients/{patient_id}/matches?per_page={total_trials}")
        assert listing.status_code == 200
        assert listing.json()["total"] == total_trials
        assert {
            "NCT10000001",
            "NCT10000002",
            "NCT10000003",
        }.issubset({item["trial_nct_id"] for item in listing.json()["items"]})

    def test_procedural_requirements_are_skipped_in_matching(self, client, db_session):
        _seed_trial_with_run(
            db_session,
            nct_id="NCT10000004",
            sex="ALL",
            criteria_payloads=[
                {
                    "type": "inclusion",
                    "category": "diagnosis",
                    "original_text": "Metastatic breast cancer",
                    "coded_concepts": [
                        {"system": "mesh", "code": "D001943", "display": "Breast Neoplasms"}
                    ],
                },
                {
                    "type": "inclusion",
                    "category": "procedural_requirement",
                    "original_text": "Provides archival tumor tissue sample",
                },
            ],
        )

        patient = client.post(
            "/api/v1/patients",
            json={
                "external_id": "pt-match-procedural",
                "sex": "female",
                "birth_date": str(date(1985, 1, 1)),
                "conditions": [
                    {
                        "description": "Metastatic breast cancer",
                        "coded_concepts": [{"system": "mesh", "code": "D001943", "display": "Breast Neoplasms"}],
                    }
                ],
            },
        )
        patient_id = patient.json()["id"]

        response = client.post(f"/api/v1/patients/{patient_id}/match")
        assert response.status_code == 200
        result = next(item for item in response.json()["results"] if item["trial_nct_id"] == "NCT10000004")
        assert result["overall_status"] == "eligible"

        detail = client.get(f"/api/v1/matches/{result['id']}")
        assert detail.status_code == 200
        categories = {item["category"] for item in detail.json()["criteria"]}
        assert "procedural_requirement" not in categories

    def test_or_grouped_criteria_do_not_force_all_branches(self, client, db_session):
        group_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        _seed_trial_with_run(
            db_session,
            nct_id="NCT10000005",
            sex="ALL",
            criteria_payloads=[
                {
                    "type": "inclusion",
                    "category": "diagnosis",
                    "original_text": "Metastatic breast cancer",
                    "coded_concepts": [
                        {"system": "mesh", "code": "D001943", "display": "Breast Neoplasms"}
                    ],
                    "logic_group_id": group_id,
                    "logic_operator": "OR",
                },
                {
                    "type": "inclusion",
                    "category": "diagnosis",
                    "original_text": "Metastatic melanoma",
                    "coded_concepts": [
                        {"system": "mesh", "code": "D008545", "display": "Melanoma"}
                    ],
                    "logic_group_id": group_id,
                    "logic_operator": "OR",
                },
            ],
        )

        patient = client.post(
            "/api/v1/patients",
            json={
                "external_id": "pt-match-or-group",
                "sex": "female",
                "birth_date": str(date(1985, 1, 1)),
                "conditions": [
                    {
                        "description": "Metastatic breast cancer",
                        "coded_concepts": [{"system": "mesh", "code": "D001943", "display": "Breast Neoplasms"}],
                    }
                ],
            },
        )
        patient_id = patient.json()["id"]

        response = client.post(f"/api/v1/patients/{patient_id}/match")
        assert response.status_code == 200
        result = next(item for item in response.json()["results"] if item["trial_nct_id"] == "NCT10000005")
        assert result["overall_status"] == "eligible"
        assert result["score"] == 1.0

        detail = client.get(f"/api/v1/matches/{result['id']}")
        assert detail.status_code == 200
        outcomes = {
            item["criterion_text"]: item["outcome"]
            for item in detail.json()["criteria"]
            if item["source_type"] == "extracted"
        }
        assert outcomes["Metastatic breast cancer"] == "matched"
        assert outcomes["Metastatic melanoma"] == "not_matched"

    def test_boolean_backed_categories_drive_matching_and_unknowns(self, client, db_session):
        _seed_trial_with_run(
            db_session,
            nct_id="NCT10000006",
            sex="ALL",
            criteria_payloads=[
                {
                    "type": "inclusion",
                    "category": "administrative_requirement",
                    "original_text": "Able to provide informed consent",
                    "value_text": "can_consent:true",
                },
                {
                    "type": "exclusion",
                    "category": "behavioral_constraint",
                    "original_text": "Claustrophobia preventing MRI",
                    "value_text": "claustrophobic:true",
                },
                {
                    "type": "exclusion",
                    "category": "device_constraint",
                    "original_text": "Presence of an MR-incompatible pacemaker",
                    "value_text": "mr_device_present:true",
                },
                {
                    "type": "exclusion",
                    "category": "reproductive_status",
                    "original_text": "Pregnant women are excluded",
                    "value_text": "pregnant:true",
                },
            ],
        )

        patient = client.post(
            "/api/v1/patients",
            json={
                "external_id": "pt-match-flags",
                "sex": "female",
                "birth_date": str(date(1985, 1, 1)),
                "can_consent": True,
                "claustrophobic": False,
                "pregnant": False,
            },
        )
        patient_id = patient.json()["id"]

        response = client.post(f"/api/v1/patients/{patient_id}/match")
        assert response.status_code == 200
        result = next(item for item in response.json()["results"] if item["trial_nct_id"] == "NCT10000006")
        assert result["overall_status"] == "possible"
        assert result["unknown_count"] == 1

        detail = client.get(f"/api/v1/matches/{result['id']}")
        assert detail.status_code == 200
        outcomes = {
            item["criterion_text"]: item["outcome"]
            for item in detail.json()["criteria"]
            if item["source_type"] == "extracted"
        }
        assert outcomes["Able to provide informed consent"] == "matched"
        assert outcomes["Claustrophobia preventing MRI"] == "not_triggered"
        assert outcomes["Pregnant women are excluded"] == "not_triggered"
        assert outcomes["Presence of an MR-incompatible pacemaker"] == "unknown"

    def test_medication_exception_logic_uses_unknowns_and_explicit_allowances(self, client, db_session):
        _seed_trial_with_run(
            db_session,
            nct_id="NCT10000007",
            sex="ALL",
            criteria_payloads=[
                {
                    "type": "exclusion",
                    "category": "concomitant_medication",
                    "original_text": "Live-attenuated vaccine within 30 days before enrollment",
                    "value_text": "live-attenuated vaccine",
                    "timeframe_operator": "within",
                    "timeframe_value": 30.0,
                    "timeframe_unit": "days",
                    "exception_logic": {
                        "mode": "washout_window",
                        "base_entities": ["live-attenuated vaccine"],
                        "has_timeframe": True,
                        "exception_text": None,
                    },
                },
                {
                    "type": "exclusion",
                    "category": "concomitant_medication",
                    "original_text": "Systemic corticosteroids except physiologic replacement doses",
                    "value_text": "systemic corticosteroids",
                    "allowance_text": "physiologic replacement doses",
                    "exception_logic": {
                        "mode": "prohibited_with_allowance",
                        "base_entities": ["systemic corticosteroids"],
                        "has_timeframe": False,
                        "exception_text": "physiologic replacement doses",
                    },
                },
            ],
        )

        patient = client.post(
            "/api/v1/patients",
            json={
                "external_id": "pt-match-medication-exceptions",
                "sex": "female",
                "birth_date": str(date(1985, 1, 1)),
                "medications": [
                    {"description": "live-attenuated vaccine", "active": True},
                    {"description": "physiologic replacement prednisone", "active": True},
                ],
            },
        )
        patient_id = patient.json()["id"]

        response = client.post(f"/api/v1/patients/{patient_id}/match")
        assert response.status_code == 200
        result = next(item for item in response.json()["results"] if item["trial_nct_id"] == "NCT10000007")
        assert result["overall_status"] == "possible"

        detail = client.get(f"/api/v1/matches/{result['id']}")
        assert detail.status_code == 200
        outcomes = {
            item["criterion_text"]: item["outcome"]
            for item in detail.json()["criteria"]
            if item["source_type"] == "extracted"
        }
        assert outcomes["Live-attenuated vaccine within 30 days before enrollment"] == "unknown"
        assert outcomes["Systemic corticosteroids except physiologic replacement doses"] == "not_triggered"
