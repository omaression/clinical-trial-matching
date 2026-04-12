import copy
import json
import uuid
from pathlib import Path
from unittest.mock import patch

import docker
import pytest

from app.extraction.coding.entity_coder import CodingResult
from app.extraction.types import ClassifiedCriterion, CodedConcept, Entity, PipelineResult
from app.ingestion.ctgov_client import SearchStudiesResult
from app.ingestion.hasher import content_hash
from app.ingestion.service import IngestionResult, IngestionService, SearchIngestTrialResult
from app.models.database import CodingLookup, ExtractedCriterion, FHIRResearchStudy, PipelineRun, Trial
from app.scripts.seed import _merge_synonyms

MOCK_DIR = Path(__file__).parent.parent / "fixtures" / "mock_ctgov_responses"

NSCLC_DIAGNOSIS_TEXT = (
    "* Has histologically or cytologically confirmed diagnosis of advanced or metastatic "
    "non-squamous non-small cell lung cancer (NSCLC)"
)
KRAS_G12C_TEXT = (
    "* Has tumor tissue or circulating tumor deoxyribonucleic acid (ctDNA) that demonstrates "
    "the presence of Kirsten rat sarcoma viral oncogene (KRAS) mutation of glycine to cysteine "
    "at codon 12 (G12C) mutations"
)
PD1_THERAPY_TEXT = (
    "* Has documented disease progression after receiving 1-2 prior lines of programmed cell "
    "death protein 1 (PD-1)/programmed death-ligand 1 (PD-L1) therapy and platinum-based "
    "chemotherapy"
)
KRAS_TARGETING_THERAPY_TEXT = "* Has received previous treatment with an agent targeting KRAS"
HIV_TEXT = (
    "* Participants with human immunodeficiency virus (HIV) infection must have well-controlled "
    "HIV on antiretroviral therapy (ART) per protocol"
)
OPHTHALMOLOGY_TEXT = (
    "* Has one or more of the following ophthalmological conditions: a) Clinically significant "
    "corneal disease b) history of documented severe dry eye syndrome, severe Meibomian gland "
    "disease and/or blepharitis"
)
VACCINE_TEXT = (
    "* Has received a live or live-attenuated vaccine within 30 days before the first dose of "
    "study intervention"
)
IMMUNODEFICIENCY_TEXT = (
    "* Has a diagnosis of immunodeficiency or is receiving chronic systemic steroid therapy or "
    "any other form of immunosuppressive therapy within 7 days prior to the first dose of study "
    "intervention"
)
ILD_TEXT = (
    "* Has history of (noninfectious) pneumonitis/ interstitial lung disease (ILD) that required "
    "steroids or has current pneumonitis/ILD"
)
ACTIVE_INFECTION_TEXT = "* Has an active infection requiring systemic therapy"
IBD_ACTIVE_TEXT = "* Has active inflammatory bowel disease requiring immunosuppressive medication"
IBD_HISTORY_TEXT = "* Has previous history of inflammatory bowel disease"
CARDIOVASCULAR_TEXT = "* Has uncontrolled or significant cardiovascular disorder prior to allocation/randomization"
CEREBROVASCULAR_TEXT = "* Has uncontrolled or significant cerebrovascular disease prior to allocation/randomization"
ARCHIVAL_TISSUE_TEXT = "* Provides archival tumor tissue sample of a tumor lesion not previously irradiated"
BIOPSY_TEXT = (
    "* Has provided tissue prior to treatment allocation/randomization from a newly obtained biopsy "
    "of a tumor lesion not previously irradiated"
)
SURGERY_TEXT = "* Have not adequately recovered from major surgery or have ongoing surgical complications"
CNS_METASTASES_TEXT = "* Has known active central nervous system (CNS) metastases"
CARCINOMATOUS_MENINGITIS_TEXT = "* Has known carcinomatous meningitis"
INCLUSION_INTRO_TEXT = "The main inclusion criteria include but are not limited to the following:"
EXCLUSION_INTRO_TEXT = "The main exclusion criteria include but are not limited to the following:"


def _docker_available():
    try:
        docker.from_env().ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _docker_available(), reason="Docker not available")


def _unique_mock_response():
    """Load mock response and assign a unique NCT ID to avoid cross-test collisions."""
    data = json.loads((MOCK_DIR / "NCT04567890.json").read_text())
    nct_id = f"NCT{uuid.uuid4().hex[:8].upper()}"
    data["protocolSection"]["identificationModule"]["nctId"] = nct_id
    return nct_id, data


def _mock_response_from_file(filename: str):
    data = json.loads((MOCK_DIR / filename).read_text())
    nct_id = data["protocolSection"]["identificationModule"]["nctId"]
    return nct_id, data


def _unique_mock_response_from_file(filename: str):
    data = json.loads((MOCK_DIR / filename).read_text())
    nct_id = f"NCT{uuid.uuid4().hex[:8].upper()}"
    data["protocolSection"]["identificationModule"]["nctId"] = nct_id
    return nct_id, data


@pytest.fixture
def service(db_session):
    return IngestionService(db_session)


class TestIngestSingleTrial:
    def test_ingests_and_extracts(self, service, db_session):
        nct_id, mock_resp = _unique_mock_response()
        with patch.object(service._client, "fetch_study", return_value=mock_resp):
            result = service.ingest(nct_id)

        assert result.trial.nct_id == nct_id
        assert result.trial.extraction_status == "completed"
        assert result.criteria_count > 0

        trial = db_session.query(Trial).filter_by(nct_id=nct_id).first()
        assert trial is not None
        run = db_session.query(PipelineRun).filter_by(trial_id=trial.id).first()
        assert run is not None
        assert run.status == "completed"
        assert run.input_snapshot is not None

    def test_ingest_aggregates_mixed_coding_review_reasons_and_counts(self, service, db_session):
        nct_id, mock_resp = _unique_mock_response()
        pipeline_result = PipelineResult(
            criteria=[
                ClassifiedCriterion(
                    original_text="Confirmed breast cancr with recurrent breast carcinoma",
                    type="inclusion",
                    category="diagnosis",
                    parse_status="parsed",
                    confidence=0.85,
                    entities=[
                        Entity(text="breast cancr", label="DISEASE", start=10, end=22),
                        Entity(text="breast carcinoma", label="DISEASE", start=38, end=54),
                    ],
                )
            ],
            pipeline_version="0.1.0",
        )
        coding_results = [
            CodingResult(
                concepts=[
                    CodedConcept(
                        system="mesh",
                        code="D001943",
                        display="Breast Neoplasms",
                        match_type="fuzzy",
                    )
                ],
                confidence=0.60,
                review_required=True,
                review_reason="fuzzy_match",
            ),
            CodingResult(
                concepts=[],
                confidence=0.40,
                review_required=True,
                review_reason="uncoded_entity",
            ),
        ]

        with (
            patch.object(service._client, "fetch_study", return_value=mock_resp),
            patch.object(service._pipeline, "extract", return_value=pipeline_result),
            patch.object(service._coder, "code_entity", side_effect=coding_results),
        ):
            result = service.ingest(nct_id)

        trial = db_session.query(Trial).filter_by(nct_id=nct_id).first()
        run = (
            db_session.query(PipelineRun)
            .filter_by(trial_id=trial.id)
            .order_by(PipelineRun.started_at.desc())
            .first()
        )
        criterion = db_session.query(ExtractedCriterion).filter_by(trial_id=trial.id).one()

        assert result.criteria_count == 1
        assert result.review_count == 1
        assert run.criteria_extracted_count == 1
        assert run.review_required_count == 1
        assert criterion.review_required is True
        assert criterion.review_reason == "mixed_coding_review"
        assert criterion.confidence == 0.40
        assert criterion.review_status == "pending"
        assert criterion.coded_concepts == [
            {
                "system": "mesh",
                "code": "D001943",
                "display": "Breast Neoplasms",
                "match_type": "fuzzy",
            }
        ]

    def test_ingest_preserves_non_coding_review_reason_while_counting_coding_flags(self, service, db_session):
        nct_id, mock_resp = _unique_mock_response()
        pipeline_result = PipelineResult(
            criteria=[
                ClassifiedCriterion(
                    original_text="No prior treatment with trastuzumab, unless administered more than 6 months ago",
                    type="exclusion",
                    category="prior_therapy",
                    parse_status="partial",
                    confidence=0.30,
                    review_required=True,
                    review_reason="complex_criteria",
                    entities=[Entity(text="trastuzumab", label="DRUG", start=24, end=35)],
                )
            ],
            pipeline_version="0.1.0",
        )
        coding_result = CodingResult(
            concepts=[],
            confidence=0.40,
            review_required=True,
            review_reason="uncoded_entity",
        )

        with (
            patch.object(service._client, "fetch_study", return_value=mock_resp),
            patch.object(service._pipeline, "extract", return_value=pipeline_result),
            patch.object(service._coder, "code_entity", return_value=coding_result),
        ):
            result = service.ingest(nct_id)

        trial = db_session.query(Trial).filter_by(nct_id=nct_id).first()
        run = db_session.query(PipelineRun).filter_by(trial_id=trial.id).one()
        criterion = db_session.query(ExtractedCriterion).filter_by(trial_id=trial.id).one()

        assert result.review_count == 1
        assert run.review_required_count == 1
        assert criterion.review_required is True
        assert criterion.review_reason == "complex_criteria"
        assert criterion.confidence == 0.30

    def test_nct07286149_regression_blocks_known_absurd_codes(self, service, db_session):
        nct_id, mock_resp = _unique_mock_response_from_file("NCT07286149.json")
        with patch.object(service._client, "fetch_study", return_value=mock_resp):
            service.ingest(nct_id)

        trial = db_session.query(Trial).filter_by(nct_id=nct_id).one()
        criteria = db_session.query(ExtractedCriterion).filter_by(trial_id=trial.id).all()
        criteria_by_text = {criterion.original_text: criterion for criterion in criteria}

        def coded_keys(text: str) -> set[tuple[str, str]]:
            criterion = criteria_by_text[text]
            return {
                (concept["system"], concept["code"])
                for concept in (criterion.coded_concepts or [])
                if isinstance(concept, dict)
            }

        assert ("loinc", "718-7") not in coded_keys(KRAS_G12C_TEXT)
        assert ("loinc", "718-7") not in coded_keys(PD1_THERAPY_TEXT)
        assert ("loinc", "1742-6") not in coded_keys(HIV_TEXT)
        assert ("loinc", "6301-6") not in coded_keys(OPHTHALMOLOGY_TEXT)
        assert ("mesh", "D015266") not in coded_keys(VACCINE_TEXT)
        assert ("mesh", "D015266") not in coded_keys(IMMUNODEFICIENCY_TEXT)
        assert ("mesh", "D015451") not in coded_keys(ILD_TEXT)
        assert criteria_by_text[NSCLC_DIAGNOSIS_TEXT].category == "diagnosis"
        assert criteria_by_text[KRAS_G12C_TEXT].category == "molecular_alteration"
        assert criteria_by_text[ACTIVE_INFECTION_TEXT].category == "diagnosis"
        assert criteria_by_text[ACTIVE_INFECTION_TEXT].review_required is False
        assert criteria_by_text[VACCINE_TEXT].category == "concomitant_medication"
        assert criteria_by_text[KRAS_TARGETING_THERAPY_TEXT].category == "prior_therapy"
        assert criteria_by_text[VACCINE_TEXT].review_required is True
        assert INCLUSION_INTRO_TEXT not in criteria_by_text
        assert EXCLUSION_INTRO_TEXT not in criteria_by_text

    def test_prior_therapy_coding_skips_biomarker_entities_even_when_catalog_matches(self, service, db_session):
        nct_id, mock_resp = _unique_mock_response()
        pipeline_result = PipelineResult(
            criteria=[
                ClassifiedCriterion(
                    original_text="Prior PD-L1 therapy and trastuzumab treatment",
                    type="inclusion",
                    category="prior_therapy",
                    parse_status="parsed",
                    confidence=0.85,
                    entities=[
                        Entity(text="PD-L1", label="BIOMARKER", start=6, end=11),
                        Entity(text="trastuzumab", label="DRUG", start=23, end=34),
                    ],
                )
            ],
            pipeline_version="0.1.0",
        )
        db_session.add_all(
            [
                CodingLookup(
                    system="nci_thesaurus",
                    code="C128839",
                    display="PD-L1 Positive",
                    synonyms=["pd-l1", "pd-l1 positive"],
                ),
                CodingLookup(
                    system="nci_thesaurus",
                    code="C1647",
                    display="Trastuzumab",
                    synonyms=["trastuzumab", "herceptin"],
                ),
            ]
        )
        db_session.flush()

        with (
            patch.object(service._client, "fetch_study", return_value=mock_resp),
            patch.object(service._pipeline, "extract", return_value=pipeline_result),
        ):
            service.ingest(nct_id)

        trial = db_session.query(Trial).filter_by(nct_id=nct_id).one()
        criterion = db_session.query(ExtractedCriterion).filter_by(trial_id=trial.id).one()
        coded_keys = {
            (concept["system"], concept["code"])
            for concept in (criterion.coded_concepts or [])
            if isinstance(concept, dict)
        }

        assert ("nci_thesaurus", "C1647") in coded_keys
        assert ("nci_thesaurus", "C128839") not in coded_keys

    def test_generic_therapy_class_mentions_do_not_force_review(self, service, db_session):
        nct_id, mock_resp = _unique_mock_response()
        pipeline_result = PipelineResult(
            criteria=[
                ClassifiedCriterion(
                    original_text="Prior platinum-based chemotherapy for metastatic disease",
                    type="inclusion",
                    category="prior_therapy",
                    parse_status="parsed",
                    confidence=0.85,
                    entities=[Entity(text="chemotherapy", label="DRUG", start=21, end=33)],
                )
            ],
            pipeline_version="0.1.0",
        )

        with (
            patch.object(service._client, "fetch_study", return_value=mock_resp),
            patch.object(service._pipeline, "extract", return_value=pipeline_result),
        ):
            result = service.ingest(nct_id)

        trial = db_session.query(Trial).filter_by(nct_id=nct_id).one()
        criterion = db_session.query(ExtractedCriterion).filter_by(trial_id=trial.id).one()

        assert result.review_count == 0
        assert criterion.review_required is False
        assert criterion.coded_concepts == []

    def test_alias_paired_disease_mentions_use_peer_context_for_coding(self, service, db_session):
        nct_id, mock_resp = _unique_mock_response()
        pipeline_result = PipelineResult(
            criteria=[
                ClassifiedCriterion(
                    original_text=(
                        "Has history of noninfectious pneumonitis / interstitial lung disease (ILD)"
                    ),
                    type="exclusion",
                    category="diagnosis",
                    parse_status="parsed",
                    confidence=0.85,
                    entities=[
                        Entity(text="pneumonitis", label="DISEASE", start=26, end=37),
                        Entity(text="interstitial lung disease", label="DISEASE", start=40, end=65),
                        Entity(text="ILD", label="ORG", start=67, end=70),
                    ],
                )
            ],
            pipeline_version="0.1.0",
        )
        db_session.add(
            CodingLookup(
                system="mesh",
                code="D017563",
                display="Lung Diseases, Interstitial",
                synonyms=["interstitial lung disease", "ild"],
            )
        )
        db_session.flush()

        with (
            patch.object(service._client, "fetch_study", return_value=mock_resp),
            patch.object(service._pipeline, "extract", return_value=pipeline_result),
        ):
            result = service.ingest(nct_id)

        trial = db_session.query(Trial).filter_by(nct_id=nct_id).one()
        criterion = db_session.query(ExtractedCriterion).filter_by(trial_id=trial.id).one()
        coded_keys = {
            (concept["system"], concept["code"])
            for concept in (criterion.coded_concepts or [])
            if isinstance(concept, dict)
        }

        assert result.review_count == 0
        assert criterion.review_required is False
        assert coded_keys == {("mesh", "D017563")}

    def test_generic_diagnosis_mentions_do_not_force_review(self, service, db_session):
        nct_id, mock_resp = _unique_mock_response()
        pipeline_result = PipelineResult(
            criteria=[
                ClassifiedCriterion(
                    original_text="Has an active infection requiring systemic therapy",
                    type="exclusion",
                    category="diagnosis",
                    parse_status="parsed",
                    confidence=0.85,
                    entities=[Entity(text="active infection", label="DISEASE", start=7, end=23)],
                )
            ],
            pipeline_version="0.1.0",
        )

        with (
            patch.object(service._client, "fetch_study", return_value=mock_resp),
            patch.object(service._pipeline, "extract", return_value=pipeline_result),
        ):
            result = service.ingest(nct_id)

        trial = db_session.query(Trial).filter_by(nct_id=nct_id).one()
        criterion = db_session.query(ExtractedCriterion).filter_by(trial_id=trial.id).one()

        assert result.review_count == 0
        assert criterion.review_required is False
        assert criterion.coded_concepts == []

    def test_nct07286149_regression_codes_domain_concepts_when_catalog_is_available(self, service, db_session):
        for system, code, display, synonyms in [
            (
                "mesh",
                "D002289",
                "Carcinoma, Non-Small-Cell Lung",
                ["nsclc", "non-small cell lung cancer", "non-small-cell lung cancer"],
            ),
            (
                "mesh",
                "D001859",
                "Brain Neoplasms",
                [
                    "brain metastases",
                    "cns metastases",
                    "central nervous system metastases",
                    "active cns metastases",
                    "active central nervous system metastases",
                ],
            ),
            (
                "mesh",
                "D015658",
                "HIV Infections",
                ["hiv infection", "human immunodeficiency virus infection", "well-controlled hiv"],
            ),
            ("mesh", "D007239", "Infections", ["infection", "active infection"]),
            (
                "mesh",
                "D015212",
                "Inflammatory Bowel Diseases",
                ["inflammatory bowel disease", "active inflammatory bowel disease"],
            ),
            (
                "mesh",
                "D002318",
                "Cardiovascular Diseases",
                ["cardiovascular disorder", "cardiovascular disease"],
            ),
            (
                "mesh",
                "D002561",
                "Cerebrovascular Disorders",
                ["cerebrovascular disease", "cerebrovascular disorder"],
            ),
            (
                "mesh",
                "D012131",
                "Respiratory Insufficiency",
                ["pulmonary compromise", "clinically severe pulmonary compromise"],
            ),
            ("mesh", "D007153", "Immunologic Deficiency Syndromes", ["immunodeficiency", "immune deficiency"]),
            ("mesh", "D017563", "Lung Diseases, Interstitial", ["interstitial lung disease", "ild"]),
            ("mesh", "D003316", "Corneal Diseases", ["corneal disease", "corneal diseases"]),
            ("mesh", "D015352", "Dry Eye Syndromes", ["dry eye syndrome", "dry eye"]),
            (
                "mesh",
                "D001762",
                "Blepharitis",
                ["blepharitis", "meibomian gland disease", "meibomian gland dysfunction"],
            ),
            ("mesh", "D012514", "Sarcoma, Kaposi", ["kaposi sarcoma", "kaposi's sarcoma"]),
            (
                "mesh",
                "D005871",
                "Castleman Disease",
                [
                    "castleman disease",
                    "castleman's disease",
                    "multicentric castleman disease",
                    "multicentric castleman's disease",
                ],
            ),
            ("nci_thesaurus", "C126815", "KRAS Mutation Positive", ["kras", "kras g12c", "kras g12c mutation"]),
            (
                "nci_thesaurus",
                "C128057",
                "anti-PD-L1 monoclonal antibody",
                ["pd-l1 therapy", "programmed death-ligand 1 therapy"],
            ),
            (
                "snomed_ct",
                "17636008",
                "Specimen collection",
                ["archival tumor tissue", "archival tumor tissue sample", "provided tissue"],
            ),
            ("snomed_ct", "86273004", "Biopsy", ["newly obtained biopsy", "tumor biopsy"]),
            ("snomed_ct", "387713003", "Surgical procedure", ["major surgery", "surgical complications"]),
        ]:
            existing = db_session.query(CodingLookup).filter_by(system=system, code=code).first()
            if existing:
                existing.display = display
                existing.synonyms = _merge_synonyms(existing.synonyms, synonyms)
            else:
                db_session.add(
                    CodingLookup(system=system, code=code, display=display, synonyms=synonyms)
                )
        db_session.flush()

        nct_id, mock_resp = _unique_mock_response_from_file("NCT07286149.json")
        with patch.object(service._client, "fetch_study", return_value=mock_resp):
            service.ingest(nct_id)

        trial = db_session.query(Trial).filter_by(nct_id=nct_id).one()
        criteria = db_session.query(ExtractedCriterion).filter_by(trial_id=trial.id).all()
        criteria_by_text = {criterion.original_text: criterion for criterion in criteria}

        def coded_keys(text: str) -> set[tuple[str, str]]:
            criterion = criteria_by_text[text]
            return {
                (concept["system"], concept["code"])
                for concept in (criterion.coded_concepts or [])
                if isinstance(concept, dict)
            }

        assert ("mesh", "D002289") in coded_keys(NSCLC_DIAGNOSIS_TEXT)
        assert ("mesh", "D001859") in coded_keys(CNS_METASTASES_TEXT)
        assert ("nci_thesaurus", "C126815") in coded_keys(KRAS_G12C_TEXT)
        assert ("nci_thesaurus", "C128057") in coded_keys(PD1_THERAPY_TEXT)
        assert ("mesh", "D015658") in coded_keys(HIV_TEXT)
        assert ("mesh", "D007239") in coded_keys(ACTIVE_INFECTION_TEXT)
        assert ("mesh", "D015212") in coded_keys(IBD_ACTIVE_TEXT)
        assert ("mesh", "D015212") in coded_keys(IBD_HISTORY_TEXT)
        assert ("mesh", "D002318") in coded_keys(CARDIOVASCULAR_TEXT)
        assert ("mesh", "D002561") in coded_keys(CEREBROVASCULAR_TEXT)
        assert ("mesh", "D007153") in coded_keys(IMMUNODEFICIENCY_TEXT)
        assert ("mesh", "D017563") in coded_keys(ILD_TEXT)
        assert criteria_by_text[ILD_TEXT].review_required is False
        assert coded_keys(KRAS_TARGETING_THERAPY_TEXT) == set()
        assert ("snomed_ct", "17636008") in coded_keys(ARCHIVAL_TISSUE_TEXT)
        assert ("snomed_ct", "86273004") in coded_keys(BIOPSY_TEXT)
        assert ("snomed_ct", "387713003") in coded_keys(SURGERY_TEXT)
        assert criteria_by_text[ARCHIVAL_TISSUE_TEXT].category == "procedural_requirement"
        assert criteria_by_text[ARCHIVAL_TISSUE_TEXT].review_required is False
        assert criteria_by_text[BIOPSY_TEXT].category == "procedural_requirement"
        assert criteria_by_text[BIOPSY_TEXT].review_required is False
        assert criteria_by_text[SURGERY_TEXT].category == "procedural_requirement"
        assert criteria_by_text[SURGERY_TEXT].review_required is False
        assert criteria_by_text[ACTIVE_INFECTION_TEXT].review_required is False
        assert criteria_by_text[IBD_ACTIVE_TEXT].logic_operator == "OR"
        assert criteria_by_text[IBD_HISTORY_TEXT].logic_operator == "OR"
        assert criteria_by_text[IBD_ACTIVE_TEXT].logic_group_id == criteria_by_text[IBD_HISTORY_TEXT].logic_group_id
        assert criteria_by_text[IBD_ACTIVE_TEXT].original_extracted == {
            "source_sentence": (
                "* Has active inflammatory bowel disease requiring immunosuppressive medication "
                "or previous history of inflammatory bowel disease"
            )
        }
        assert criteria_by_text[CARDIOVASCULAR_TEXT].logic_operator == "OR"
        assert criteria_by_text[CEREBROVASCULAR_TEXT].logic_operator == "OR"
        assert (
            criteria_by_text[CARDIOVASCULAR_TEXT].logic_group_id
            == criteria_by_text[CEREBROVASCULAR_TEXT].logic_group_id
        )
        assert criteria_by_text[CARDIOVASCULAR_TEXT].original_extracted == {
            "source_sentence": (
                "* Has uncontrolled or significant cardiovascular disorder or cerebrovascular disease "
                "prior to allocation/randomization"
            )
        }
        kaposi_castleman_codes = coded_keys(
            "* HIV-infected participants with a history of Kaposi's sarcoma and/or Multicentric Castleman's Disease"
        )
        assert ("mesh", "D012514") in kaposi_castleman_codes
        assert ("mesh", "D005871") in kaposi_castleman_codes
        ophthalmology_codes = coded_keys(OPHTHALMOLOGY_TEXT)
        assert ("mesh", "D003316") in ophthalmology_codes
        assert ("mesh", "D015352") in ophthalmology_codes
        assert ("mesh", "D001762") in ophthalmology_codes
        assert len(criteria_by_text[NSCLC_DIAGNOSIS_TEXT].coded_concepts) == 1
        assert len(criteria_by_text[HIV_TEXT].coded_concepts) == 1
        assert len(criteria_by_text[OPHTHALMOLOGY_TEXT].coded_concepts) == 3


class TestIdempotency:
    def test_reingest_unchanged_skips(self, service, db_session):
        nct_id, mock_resp = _unique_mock_response()
        with patch.object(service._client, "fetch_study", return_value=mock_resp):
            result1 = service.ingest(nct_id)
            result2 = service.ingest(nct_id)

        assert result2.skipped is True
        runs = db_session.query(PipelineRun).filter_by(trial_id=result1.trial.id).count()
        assert runs == 1

    def test_reingest_changed_reextracts(self, service, db_session):
        nct_id, mock_resp = _unique_mock_response()
        with patch.object(service._client, "fetch_study", return_value=mock_resp):
            result1 = service.ingest(nct_id)

        changed = copy.deepcopy(mock_resp)
        changed["protocolSection"]["eligibilityModule"]["eligibilityCriteria"] = "Age >= 21 years"
        with patch.object(service._client, "fetch_study", return_value=changed):
            result2 = service.ingest(nct_id)

        assert result2.skipped is False
        runs = db_session.query(PipelineRun).filter_by(trial_id=result1.trial.id).count()
        assert runs == 2

    def test_reingest_changed_source_fields_reextracts_and_preserves_run_history(self, service, db_session):
        nct_id, mock_resp = _unique_mock_response()
        with patch.object(service._client, "fetch_study", return_value=mock_resp):
            result1 = service.ingest(nct_id)

        changed = copy.deepcopy(mock_resp)
        changed["protocolSection"]["identificationModule"]["briefTitle"] = "Updated Study Title"
        changed["protocolSection"]["statusModule"]["overallStatus"] = "COMPLETED"
        changed["protocolSection"]["eligibilityModule"]["minimumAge"] = "21 Years"

        with patch.object(service._client, "fetch_study", return_value=changed):
            result2 = service.ingest(nct_id)

        trial = db_session.query(Trial).filter_by(nct_id=nct_id).first()
        runs = db_session.query(PipelineRun).filter_by(trial_id=trial.id).count()
        latest_run = (
            db_session.query(PipelineRun)
            .filter_by(trial_id=trial.id)
            .order_by(PipelineRun.started_at.desc())
            .first()
        )
        total_criteria = db_session.query(ExtractedCriterion).filter_by(trial_id=trial.id).count()
        latest_criteria_count = db_session.query(ExtractedCriterion).filter_by(
            trial_id=trial.id,
            pipeline_run_id=latest_run.id,
        ).count()
        fhir_versions = [
            row.version
            for row in db_session.query(FHIRResearchStudy)
            .filter_by(trial_id=trial.id)
            .order_by(FHIRResearchStudy.version.asc())
            .all()
        ]

        assert result2.skipped is False
        assert runs == 2
        assert trial.brief_title == "Updated Study Title"
        assert trial.status == "COMPLETED"
        assert trial.eligible_min_age == "21 Years"
        assert total_criteria == result1.criteria_count + result2.criteria_count
        assert latest_criteria_count == result2.criteria_count
        assert fhir_versions == [1, 2]

    def test_reextract_appends_history_and_diffs_against_previous_completed_run(self, service, db_session):
        nct_id, mock_resp = _unique_mock_response()
        with patch.object(service._client, "fetch_study", return_value=mock_resp):
            first_result = service.ingest(nct_id)

        trial = db_session.query(Trial).filter_by(nct_id=nct_id).first()
        second_result = service.re_extract(trial)

        runs = (
            db_session.query(PipelineRun)
            .filter_by(trial_id=trial.id, status="completed")
            .order_by(PipelineRun.started_at.asc())
            .all()
        )
        criteria_by_run = {
            run.id: db_session.query(ExtractedCriterion).filter_by(pipeline_run_id=run.id).count()
            for run in runs
        }
        fhir_versions = [
            row.version
            for row in db_session.query(FHIRResearchStudy)
            .filter_by(trial_id=trial.id)
            .order_by(FHIRResearchStudy.version.asc())
            .all()
        ]

        assert len(runs) == 2
        assert second_result.criteria_count == first_result.criteria_count
        assert criteria_by_run[runs[0].id] == first_result.criteria_count
        assert criteria_by_run[runs[1].id] == second_result.criteria_count
        assert second_result.diff_summary == {
            "added": 0,
            "removed": 0,
            "unchanged": first_result.criteria_count,
            "previous_count": first_result.criteria_count,
            "new_count": second_result.criteria_count,
        }
        assert fhir_versions == [1, 2]

    def test_reextract_failure_preserves_existing_criteria(self, service, db_session):
        nct_id, mock_resp = _unique_mock_response()
        with patch.object(service._client, "fetch_study", return_value=mock_resp):
            result = service.ingest(nct_id)

        trial = db_session.query(Trial).filter_by(nct_id=nct_id).first()
        original_count = db_session.query(ExtractedCriterion).filter_by(trial_id=trial.id).count()

        with patch.object(service._pipeline, "extract", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                service.re_extract(trial)

        criteria_count = db_session.query(ExtractedCriterion).filter_by(trial_id=trial.id).count()
        fhir_count = db_session.query(FHIRResearchStudy).filter_by(trial_id=trial.id).count()
        latest_run = (
            db_session.query(PipelineRun)
            .filter_by(trial_id=trial.id)
            .order_by(PipelineRun.started_at.desc())
            .first()
        )

        assert criteria_count == original_count
        assert original_count == result.criteria_count
        assert fhir_count == 1
        assert latest_run.status == "failed"


class TestContentHash:
    def test_hash_deterministic(self):
        h1 = content_hash("some eligibility text")
        h2 = content_hash("some eligibility text")
        assert h1 == h2

    def test_hash_differs_on_change(self):
        h1 = content_hash("Age >= 18")
        h2 = content_hash("Age >= 21")
        assert h1 != h2


class TestSearchAndIngest:
    def test_search_and_ingest_keeps_partial_batch_outcomes(self, service):
        search_result = SearchStudiesResult(
            studies=[
                {"protocolSection": {"identificationModule": {"nctId": "NCTGOOD001"}}},
                {"protocolSection": {"identificationModule": {"nctId": "NCTSKIP001"}}},
                {"protocolSection": {"identificationModule": {"nctId": "NCTFAIL001"}}},
                {"protocolSection": {"identificationModule": {}}},
            ],
            total_count=42,
            next_page_token="cursor-2",
        )
        ingest_results = {
            "NCTGOOD001": IngestionResult(trial=Trial(id=uuid.uuid4(), nct_id="NCTGOOD001"), criteria_count=4),
            "NCTSKIP001": IngestionResult(
                trial=Trial(id=uuid.uuid4(), nct_id="NCTSKIP001"),
                criteria_count=0,
                skipped=True,
            ),
        }

        def _ingest(nct_id):
            if nct_id == "NCTFAIL001":
                raise RuntimeError("boom")
            result = ingest_results[nct_id]
            return SearchIngestTrialResult(
                nct_id=nct_id,
                trial=result.trial,
                criteria_count=result.criteria_count,
                skipped=result.skipped,
            )

        with (
            patch.object(service._client, "search_studies", return_value=search_result) as search_studies,
            patch.object(service, "_ingest_search_result", side_effect=_ingest),
        ):
            batch = service.search_and_ingest(condition="breast cancer", limit=4, page_token="cursor-1")

        assert batch.returned_count == 4
        assert batch.total_count == 42
        assert batch.next_page_token == "cursor-2"
        assert len(batch.results) == 4
        assert [result.nct_id for result in batch.results] == ["NCTGOOD001", "NCTSKIP001", "NCTFAIL001", None]
        assert batch.results[0].trial is not None
        assert batch.results[0].criteria_count == 4
        assert batch.results[0].skipped is False
        assert batch.results[0].error_message is None
        assert batch.results[1].trial is not None
        assert batch.results[1].skipped is True
        assert batch.results[2].trial is None
        assert batch.results[2].error_message == "Trial ingestion failed"
        assert batch.results[3].trial is None
        assert batch.results[3].error_message == "Search result missing NCT ID"
        search_studies.assert_called_once_with(
            condition="breast cancer",
            status=None,
            phase=None,
            limit=4,
            page_token="cursor-1",
        )
