from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.db.session import SessionLocal
from app.ingestion.service import IngestionService
from app.matching.service import PatientMatchService
from app.models.database import (
    Patient,
    PatientBiomarker,
    PatientCondition,
    PatientLab,
    PatientMedication,
    PatientTherapy,
    Trial,
)
from app.scripts.seed import seed as seed_coding_lookups

DEMO_TRIAL_IDS = ("NCT04567890", "NCT90000001")
DEMO_PATIENT_IDS = ("DEMO-HER2-001", "DEMO-HER2-002")


def _fixture_path(*parts: str) -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures" / Path(*parts)


def _load_json_fixture(name: str) -> dict:
    return json.loads(_fixture_path("mock_ctgov_responses", name).read_text())


def _load_text_fixture(name: str) -> str:
    return _fixture_path("sample_eligibility_texts", name).read_text().strip()


def _synthetic_review_trial() -> dict:
    return {
        "protocolSection": {
            "identificationModule": {
                "nctId": "NCT90000001",
                "briefTitle": "Synthetic CNS Review Demonstration Trial",
                "officialTitle": "Synthetic local review fixture for CNS metastases eligibility demonstration",
            },
            "statusModule": {
                "overallStatus": "RECRUITING",
                "startDateStruct": {"date": "2025-02-01"},
                "primaryCompletionDateStruct": {"date": "2027-10-31"},
            },
            "sponsorCollaboratorsModule": {
                "leadSponsor": {
                    "name": "Portfolio Demonstration Sponsor",
                    "class": "OTHER",
                }
            },
            "designModule": {
                "phases": ["PHASE2"],
                "studyType": "INTERVENTIONAL",
            },
            "conditionsModule": {
                "conditions": ["Metastatic Breast Cancer", "CNS Metastases"],
            },
            "armsInterventionsModule": {
                "interventions": [
                    {
                        "type": "DRUG",
                        "name": "Synthetic Investigational Agent",
                        "description": "Synthetic local fixture intervention",
                    }
                ]
            },
            "eligibilityModule": {
                "eligibilityCriteria": _load_text_fixture("nct05346328_cns_exception.txt"),
                "healthyVolunteers": "No",
                "sex": "ALL",
                "minimumAge": "18 Years",
                "maximumAge": "75 Years",
                "stdAges": ["ADULT", "OLDER_ADULT"],
            },
            "contactsLocationsModule": {
                "locations": [
                    {
                        "facility": "Portfolio Demo Cancer Center",
                        "city": "Boston",
                        "state": "Massachusetts",
                        "country": "United States",
                        "zip": "02115",
                        "status": "RECRUITING",
                    }
                ]
            },
        }
    }


def _mock_fetch_factory(expected_nct_id: str, payload: dict):
    def fetch_study(requested_nct_id: str) -> dict:
        if requested_nct_id != expected_nct_id:
            raise ValueError(f"Unexpected demo trial request: {requested_nct_id}")
        return payload

    return fetch_study


def _replace_demo_trials() -> None:
    fixtures = {
        "NCT04567890": _load_json_fixture("NCT04567890.json"),
        "NCT90000001": _synthetic_review_trial(),
    }

    db = SessionLocal()
    try:
        for trial in db.query(Trial).filter(Trial.nct_id.in_(DEMO_TRIAL_IDS)).all():
            db.delete(trial)
        db.commit()

        service = IngestionService(db)
        for nct_id, payload in fixtures.items():
            service._client.fetch_study = _mock_fetch_factory(nct_id, payload)
            service.ingest(nct_id)
    finally:
        db.close()


def _replace_demo_patients() -> None:
    db = SessionLocal()
    try:
        for patient in db.query(Patient).filter(Patient.external_id.in_(DEMO_PATIENT_IDS)).all():
            db.delete(patient)
        db.commit()

        patient_1 = Patient(
            external_id="DEMO-HER2-001",
            sex="female",
            birth_date=date(1988, 6, 14),
            ecog_status=1,
            is_healthy_volunteer=False,
            city="Boston",
            state="Massachusetts",
            country="United States",
        )
        patient_1.conditions = [
            PatientCondition(description="HER2-positive breast cancer"),
        ]
        patient_1.biomarkers = [
            PatientBiomarker(
                description="HER2 positive",
                coded_concepts=[{"system": "nci_thesaurus", "code": "C68748", "display": "HER2 Positive"}],
            )
        ]
        patient_1.labs = [
            PatientLab(
                description="ANC",
                value_numeric=1900,
                unit="cells/uL",
                coded_concepts=[{"system": "loinc", "code": "751-8", "display": "Neutrophils [#/volume] in Blood"}],
            )
        ]

        patient_2 = Patient(
            external_id="DEMO-HER2-002",
            sex="female",
            birth_date=date(1940, 3, 22),
            ecog_status=2,
            is_healthy_volunteer=False,
            city="Cambridge",
            state="Massachusetts",
            country="United States",
        )
        patient_2.conditions = [
            PatientCondition(description="Metastatic breast cancer"),
        ]
        patient_2.biomarkers = [
            PatientBiomarker(
                description="HER2 positive",
                coded_concepts=[{"system": "nci_thesaurus", "code": "C68748", "display": "HER2 Positive"}],
            )
        ]
        patient_2.labs = [
            PatientLab(
                description="ANC",
                value_numeric=1200,
                unit="cells/uL",
                coded_concepts=[{"system": "loinc", "code": "751-8", "display": "Neutrophils [#/volume] in Blood"}],
            )
        ]
        patient_2.therapies = [
            PatientTherapy(
                description="trastuzumab",
                completed=True,
                line_of_therapy=1,
                coded_concepts=[{"system": "nci_thesaurus", "code": "C1647", "display": "Trastuzumab"}],
            )
        ]
        patient_2.medications = [
            PatientMedication(description="dexamethasone", active=True),
        ]

        db.add_all([patient_1, patient_2])
        db.commit()

        matcher = PatientMatchService(db)
        for external_id in DEMO_PATIENT_IDS:
            patient = db.query(Patient).filter(Patient.external_id == external_id).first()
            if patient:
                matcher.run_match(patient)
    finally:
        db.close()


def main() -> None:
    seed_coding_lookups()
    _replace_demo_trials()
    _replace_demo_patients()
    print("Seeded local demo trials, patients, and match results.")


if __name__ == "__main__":
    main()
