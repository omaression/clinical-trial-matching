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
        pipeline_version="0.1.0",
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
            "pipeline_version": "0.1.0",
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

        fetched = client.get(f"/api/v1/patients/{patient_id}")
        assert fetched.status_code == 200
        assert fetched.json()["biomarkers"][0]["coded_concepts"][0]["code"] == "C68748"

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
        assert "eligible" in ranked["NCT10000001"]["summary_explanation"].casefold()
        assert ranked["NCT10000002"]["overall_status"] == "ineligible"
        assert ranked["NCT10000003"]["overall_status"] == "possible"
        assert ranked["NCT10000003"]["requires_review_count"] == 1

        stored = db_session.query(MatchResult).filter(MatchResult.trial_id == eligible_trial.id).first()
        assert stored is not None

        detail = client.get(f"/api/v1/matches/{ranked['NCT10000001']['id']}")
        assert detail.status_code == 200
        outcomes = {(item["source_type"], item["category"]): item["outcome"] for item in detail.json()["criteria"]}
        assert outcomes[("structured", "sex")] == "matched"
        assert outcomes[("structured", "age")] == "matched"
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
