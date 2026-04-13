from pathlib import Path

import pytest

from app.extraction.pipeline import ExtractionPipeline
from app.extraction.types import PipelineResult

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="module")
def pipeline():
    return ExtractionPipeline()


class TestSimpleBreastCancer:
    def test_extracts_all_criteria(self, pipeline):
        text = (FIXTURES / "sample_eligibility_texts" / "simple_breast_cancer.txt").read_text()
        result = pipeline.extract(text)
        assert isinstance(result, PipelineResult)
        assert result.criteria_count >= 5
        inclusion = [c for c in result.criteria if c.type == "inclusion"]
        exclusion = [c for c in result.criteria if c.type == "exclusion"]
        assert len(inclusion) >= 3
        assert len(exclusion) >= 2

    def test_age_criterion_parsed(self, pipeline):
        text = (FIXTURES / "sample_eligibility_texts" / "simple_breast_cancer.txt").read_text()
        result = pipeline.extract(text)
        age = [c for c in result.criteria if c.category == "age"]
        assert len(age) == 1
        assert age[0].operator == "gte"
        assert age[0].value_low == 18
        assert age[0].unit == "years"

    def test_exclusion_negated(self, pipeline):
        text = (FIXTURES / "sample_eligibility_texts" / "simple_breast_cancer.txt").read_text()
        result = pipeline.extract(text)
        exclusion = [c for c in result.criteria if c.type == "exclusion"]
        brain = [c for c in exclusion if "brain" in c.original_text.lower()]
        assert len(brain) == 1


class TestMissingHeaders:
    def test_polarity_fallback_classifies_correctly(self, pipeline):
        text = (FIXTURES / "sample_eligibility_texts" / "missing_headers.txt").read_text()
        result = pipeline.extract(text)
        types = {c.type for c in result.criteria}
        assert "inclusion" in types
        assert "exclusion" in types


class TestPipelineVersion:
    def test_version_stamped(self, pipeline):
        result = pipeline.extract("Age >= 18 years")
        assert result.pipeline_version == "0.1.0"


class TestNoCriteriaDropped:
    def test_unparseable_preserved(self, pipeline):
        text = "Adequate renal function as determined by the investigator"
        result = pipeline.extract(text)
        assert result.criteria_count >= 1
        assert any(c.original_text == text for c in result.criteria)


class TestNct07286149Signals:
    def test_kras_mutation_line_stays_molecular_not_diagnosis(self, pipeline):
        text = (
            "Has tumor tissue or circulating tumor deoxyribonucleic acid (ctDNA) that demonstrates "
            "the presence of Kirsten rat sarcoma viral oncogene (KRAS) mutation of glycine to "
            "cysteine at codon 12 (G12C) mutations"
        )
        result = pipeline.extract(text)
        assert result.criteria_count == 1
        assert result.criteria[0].category == "molecular_alteration"
        assert result.criteria[0].specimen_type == "ctDNA"
        assert result.criteria[0].assay_context == {
            "specimen_types": ["ctDNA", "tumor tissue"],
            "testing_modalities": ["liquid_biopsy"],
        }
        assert result.criteria[0].confidence >= 0.75

    def test_nsclc_line_stays_diagnosis_primary(self, pipeline):
        text = "Has histologically confirmed diagnosis of advanced or metastatic non-small cell lung cancer (NSCLC)"
        result = pipeline.extract(text)
        assert result.criteria_count == 1
        assert result.criteria[0].category == "diagnosis"

    def test_active_infection_line_routes_to_diagnosis_not_prior_therapy(self, pipeline):
        text = "Has an active infection requiring systemic therapy"
        result = pipeline.extract(text)
        assert result.criteria_count == 1
        assert result.criteria[0].category == "diagnosis"
        assert result.criteria[0].review_required is False

    def test_biomarker_targeting_therapy_line_routes_to_prior_therapy(self, pipeline):
        text = "Has received previous treatment with an agent targeting KRAS"
        result = pipeline.extract(text)
        assert result.criteria_count == 1
        assert result.criteria[0].category == "prior_therapy"

    def test_live_vaccine_line_becomes_reviewable_concomitant_medication(self, pipeline):
        text = "Has received a live-attenuated vaccine within 30 days before the first dose"
        result = pipeline.extract(text)
        assert result.criteria_count == 1
        assert result.criteria[0].category == "concomitant_medication"
        assert result.criteria[0].parse_status == "partial"
        assert result.criteria[0].review_required is True
        assert result.criteria[0].confidence > 0.3

    def test_non_small_cell_line_keeps_specific_disease_entity(self, pipeline):
        text = "Has histologically confirmed metastatic non-small cell lung cancer"
        result = pipeline.extract(text)
        assert result.criteria_count == 1
        disease_entities = [entity for entity in result.criteria[0].entities if entity.label == "DISEASE"]
        assert any("non-small cell lung cancer" in entity.text.lower() for entity in disease_entities)

    def test_kaposi_and_castleman_line_keeps_specific_disease_entities(self, pipeline):
        text = "HIV-infected participants with a history of Kaposi's sarcoma and/or Multicentric Castleman's Disease"
        result = pipeline.extract(text)
        assert result.criteria_count == 1
        disease_entities = [entity.text.lower() for entity in result.criteria[0].entities if entity.label == "DISEASE"]
        assert any("kaposi" in entity and "sarcoma" in entity for entity in disease_entities)
        assert any("castleman" in entity and "disease" in entity for entity in disease_entities)

    def test_cns_metastases_line_keeps_specific_disease_entities(self, pipeline):
        text = "Has known active central nervous system (CNS) metastases and/or carcinomatous meningitis"
        result = pipeline.extract(text)
        disease_entities = [entity.text.lower() for entity in result.criteria[0].entities if entity.label == "DISEASE"]
        assert any("central nervous system" in entity or "cns metastases" in entity for entity in disease_entities)

    def test_ibd_compound_exclusion_splits_into_linked_criteria(self, pipeline):
        text = (
            "Has active inflammatory bowel disease requiring immunosuppressive medication "
            "or previous history of inflammatory bowel disease"
        )
        result = pipeline.extract(text)
        assert result.criteria_count == 2
        assert all(criterion.category == "diagnosis" for criterion in result.criteria)
        assert all(criterion.review_required is False for criterion in result.criteria)
        logic_group_ids = {criterion.logic_group_id for criterion in result.criteria}
        assert len(logic_group_ids) == 1
        assert {criterion.logic_operator for criterion in result.criteria} == {"OR"}

    def test_cardiovascular_compound_exclusion_splits_into_linked_criteria(self, pipeline):
        text = (
            "Has uncontrolled or significant cardiovascular disorder or cerebrovascular disease "
            "prior to allocation/randomization"
        )
        result = pipeline.extract(text)
        assert result.criteria_count == 2
        assert all(criterion.category == "diagnosis" for criterion in result.criteria)
        assert all(criterion.review_required is False for criterion in result.criteria)
        logic_group_ids = {criterion.logic_group_id for criterion in result.criteria}
        assert len(logic_group_ids) == 1
        assert {criterion.logic_operator for criterion in result.criteria} == {"OR"}

    def test_procedural_requirements_are_classified_structurally(self, pipeline):
        text = (
            "Inclusion Criteria:\n"
            "The main inclusion criteria include but are not limited to the following:\n"
            "1. Provides archival tumor tissue sample of a tumor lesion not previously irradiated\n"
            "2. Has provided tissue prior to treatment allocation/randomization from a newly obtained biopsy "
            "of a tumor lesion not previously irradiated\n"
        )
        result = pipeline.extract(text)
        assert result.criteria_count == 2
        assert all(criterion.category == "procedural_requirement" for criterion in result.criteria)
        assert all(criterion.review_required is False for criterion in result.criteria)
        assert any(entity.label == "PROCEDURE" for criterion in result.criteria for entity in criterion.entities)

    def test_administrative_behavioral_and_device_constraints_are_not_unparsed(self, pipeline):
        text = (
            "Exclusion Criteria:\n"
            "- Adults unable to consent\n"
            "- Unable to comply with protocol procedures\n"
            "- Claustrophobia that prevents MRI completion\n"
            "- Unable to remain still during MRI acquisition\n"
            "- Presence of an MR-incompatible pacemaker\n"
            "- Pregnant women\n"
            "- Receiving systemic corticosteroids\n"
        )
        result = pipeline.extract(text)
        categories = [criterion.category for criterion in result.criteria]
        assert "administrative_requirement" in categories
        assert "behavioral_constraint" in categories
        assert "device_constraint" in categories
        assert "reproductive_status" in categories
        assert "concomitant_medication" in categories
        assert all(
            not (criterion.category == "other" and criterion.parse_status == "unparsed")
            for criterion in result.criteria
        )

    def test_primary_brain_tumor_is_retained_alongside_cns_disease_mentions(self, pipeline):
        text = "Patients with primary brain tumors or active CNS metastases are excluded."
        result = pipeline.extract(text)
        disease_entities = [
            entity.text.lower()
            for criterion in result.criteria
            for entity in criterion.entities
            if entity.label == "DISEASE"
        ]
        assert any("primary brain tumor" in entity for entity in disease_entities)
        assert any("cns metastases" in entity or "central nervous system" in entity for entity in disease_entities)

    def test_diagnosis_enumeration_with_palliative_radiation_splits_into_or_linked_diagnoses(self, pipeline):
        text = (
            "Histologically confirmed breast cancer, non-small cell lung cancer, colorectal cancer, "
            "or pancreatic cancer requiring palliative radiation are eligible."
        )
        result = pipeline.extract(text)
        assert result.criteria_count == 4
        assert all(criterion.category == "diagnosis" for criterion in result.criteria)
        assert all("therapy_context" in criterion.secondary_semantic_tags for criterion in result.criteria)
        logic_group_ids = {criterion.logic_group_id for criterion in result.criteria}
        assert len(logic_group_ids) == 1
        assert {criterion.logic_operator for criterion in result.criteria} == {"OR"}

    def test_pd_l1_therapy_phrase_emits_drug_entity(self, pipeline):
        text = "Has progressed after prior programmed death-ligand 1 (PD-L1) therapy"
        result = pipeline.extract(text)
        assert result.criteria_count == 1
        drug_entities = [entity.text.lower() for entity in result.criteria[0].entities if entity.label == "DRUG"]
        assert any("therapy" in entity for entity in drug_entities)

    def test_progression_after_receiving_splits_into_atomic_prior_therapy_clauses(self, pipeline):
        text = (
            "Has documented disease progression after receiving 1-2 prior lines of programmed cell "
            "death protein 1 (PD-1)/programmed death-ligand 1 (PD-L1) therapy and platinum-based chemotherapy"
        )
        result = pipeline.extract(text)
        assert result.criteria_count == 2
        assert all(criterion.category == "prior_therapy" for criterion in result.criteria)
        assert all("progression_requirement" in criterion.secondary_semantic_tags for criterion in result.criteria)
        assert all(criterion.source_sentence == text for criterion in result.criteria)

    def test_pd_1_therapy_phrase_emits_drug_entity(self, pipeline):
        text = "Has progressed after prior PD-1 therapy"
        result = pipeline.extract(text)
        assert result.criteria_count == 1
        drug_entities = [entity.text.lower() for entity in result.criteria[0].entities if entity.label == "DRUG"]
        assert "pd-1 therapy" in drug_entities

    def test_pd_1_pd_l1_inhibitor_phrase_emits_drug_entity(self, pipeline):
        text = "Has progressed after prior PD-1/PD-L1 inhibitor therapy"
        result = pipeline.extract(text)
        assert result.criteria_count == 1
        drug_entities = [entity.text.lower() for entity in result.criteria[0].entities if entity.label == "DRUG"]
        assert "pd-1/pd-l1 inhibitor therapy" in drug_entities

    def test_agent_targeting_kras_phrase_emits_drug_entity(self, pipeline):
        text = "Has received previous treatment with an agent targeting KRAS"
        result = pipeline.extract(text)
        assert result.criteria_count == 1
        drug_entities = [entity.text.lower() for entity in result.criteria[0].entities if entity.label == "DRUG"]
        assert "agent targeting kras" in drug_entities

    def test_kras_targeted_therapy_phrase_emits_drug_entity(self, pipeline):
        text = "Has received previous KRAS-targeted therapy"
        result = pipeline.extract(text)
        assert result.criteria_count == 1
        drug_entities = [entity.text.lower() for entity in result.criteria[0].entities if entity.label == "DRUG"]
        assert "kras-targeted therapy" in drug_entities
