import docker
import pytest

from app.extraction.coding.entity_coder import EntityCoder
from app.extraction.types import Entity
from app.models.database import CodingLookup


def _docker_available():
    try:
        docker.from_env().ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _docker_available(), reason="Docker not available")


@pytest.fixture
def seed_lookups(db_session):
    lookups = [
        CodingLookup(system="mesh", code="D001943", display="Breast Neoplasms",
                      synonyms=["breast cancer", "breast carcinoma"]),
        CodingLookup(system="mesh", code="D000073182", display="Triple Negative Breast Neoplasms",
                      synonyms=["tnbc", "triple negative breast cancer"]),
        CodingLookup(system="nci_thesaurus", code="C68748", display="HER2 Positive",
                      synonyms=["her2+", "erbb2 positive"]),
        CodingLookup(system="nci_thesaurus", code="C126815", display="KRAS Mutation Positive",
                      synonyms=["kras", "kras mutant", "kras g12c", "kras g12c mutation"]),
        CodingLookup(system="mesh", code="D008545", display="Melanoma",
                      synonyms=["malignant melanoma"]),
        CodingLookup(system="nci_thesaurus", code="C3224", display="Melanoma",
                      synonyms=["melanoma lesion"]),
        CodingLookup(system="mesh", code="D002289", display="Carcinoma, Non-Small-Cell Lung",
                      synonyms=["nsclc", "non-small cell lung cancer"]),
        CodingLookup(system="mesh", code="D055752", display="Small Cell Lung Carcinoma",
                      synonyms=["sclc", "small cell lung cancer"]),
        CodingLookup(system="mesh", code="D015658", display="HIV Infections",
                      synonyms=["hiv infection", "human immunodeficiency virus infection"]),
        CodingLookup(system="mesh", code="D007239", display="Infections",
                      synonyms=["infection", "active infection"]),
        CodingLookup(system="mesh", code="D007153", display="Immunologic Deficiency Syndromes",
                      synonyms=["immunodeficiency", "immune deficiency"]),
        CodingLookup(system="mesh", code="D015212", display="Inflammatory Bowel Diseases",
                      synonyms=["inflammatory bowel disease", "active inflammatory bowel disease"]),
        CodingLookup(system="mesh", code="D002318", display="Cardiovascular Diseases",
                      synonyms=["cardiovascular disorder", "cardiovascular disease"]),
        CodingLookup(system="mesh", code="D002561", display="Cerebrovascular Disorders",
                      synonyms=["cerebrovascular disease", "cerebrovascular disorder"]),
        CodingLookup(system="mesh", code="D012131", display="Respiratory Insufficiency",
                      synonyms=["pulmonary compromise", "clinically severe pulmonary compromise"]),
        CodingLookup(system="mesh", code="D017563", display="Lung Diseases, Interstitial",
                      synonyms=["interstitial lung disease", "ild", "pneumonitis interstitial"]),
        CodingLookup(system="mesh", code="D001859", display="Brain Neoplasms",
                      synonyms=["brain metastases", "cns metastases", "central nervous system metastases"]),
        CodingLookup(system="mesh", code="D003316", display="Corneal Diseases",
                      synonyms=["corneal disease", "corneal diseases"]),
        CodingLookup(system="mesh", code="D015352", display="Dry Eye Syndromes",
                      synonyms=["dry eye syndrome", "dry eye"]),
        CodingLookup(system="mesh", code="D001762", display="Blepharitis",
                      synonyms=["blepharitis", "meibomian gland disease"]),
        CodingLookup(system="nci_thesaurus", code="C1647", display="Trastuzumab",
                      synonyms=["herceptin"]),
        CodingLookup(system="nci_thesaurus", code="C178320", display="anti-PD-1 monoclonal antibody",
                      synonyms=["pd-1 therapy", "programmed cell death protein 1 therapy"]),
        CodingLookup(system="nci_thesaurus", code="C128057", display="anti-PD-L1 monoclonal antibody",
                      synonyms=["pd-l1 therapy", "programmed death-ligand 1 therapy"]),
        CodingLookup(system="snomed_ct", code="17636008", display="Specimen collection",
                      synonyms=["archival tumor tissue sample", "archival tumor tissue"]),
        CodingLookup(system="snomed_ct", code="86273004", display="Biopsy",
                      synonyms=["newly obtained biopsy", "tumor biopsy"]),
        CodingLookup(system="snomed_ct", code="387713003", display="Surgical procedure",
                      synonyms=["major surgery", "surgical complications"]),
        CodingLookup(system="loinc", code="751-8", display="Neutrophils [#/volume] in Blood",
                      synonyms=["anc", "absolute neutrophil count"]),
    ]
    for lookup in lookups:
        existing = db_session.query(CodingLookup).filter_by(system=lookup.system, code=lookup.code).first()
        if existing:
            existing.display = lookup.display
            existing.synonyms = lookup.synonyms
        else:
            db_session.add(lookup)
    db_session.flush()
    return lookups


@pytest.fixture
def coder(db_session, seed_lookups):
    return EntityCoder(db_session)


class TestExactMatch:
    def test_exact_match(self, coder):
        entity = Entity(text="Breast Neoplasms", label="DISEASE", start=0, end=16)
        result = coder.code_entity(entity)
        assert len(result.concepts) == 1
        assert result.concepts[0].code == "D001943"
        assert result.concepts[0].match_type == "exact"
        assert result.confidence == 0.95
        assert result.review_required is False


class TestSynonymMatch:
    def test_synonym_match(self, coder):
        entity = Entity(text="breast cancer", label="DISEASE", start=0, end=13)
        result = coder.code_entity(entity)
        assert len(result.concepts) == 1
        assert result.concepts[0].code == "D001943"
        assert result.concepts[0].match_type == "synonym"
        assert result.confidence == 0.85
        assert result.review_required is False


class TestFuzzyMatch:
    def test_fuzzy_flagged_for_review(self, coder):
        entity = Entity(text="breast cancr", label="DISEASE", start=0, end=12)
        result = coder.code_entity(entity)
        if result.concepts:
            assert result.concepts[0].match_type == "fuzzy"
            assert result.review_required is True
            assert result.confidence == 0.60

    def test_fuzzy_match_uses_synonym_similarity(self, coder):
        entity = Entity(text="absolute neutrophil coun", label="LAB_TEST", start=0, end=24)
        result = coder.code_entity(entity)
        assert result.concepts[0].system == "loinc"
        assert result.concepts[0].code == "751-8"
        assert result.concepts[0].match_type == "fuzzy"
        assert result.review_required is True


class TestNoMatch:
    def test_uncoded_flagged(self, coder):
        entity = Entity(text="XYZ_UNKNOWN_ENTITY", label="DISEASE", start=0, end=18)
        result = coder.code_entity(entity)
        assert result.concepts == []
        assert result.review_required is True
        assert result.confidence == 0.40

    def test_non_codeable_labels_are_skipped_without_review(self, coder):
        entity = Entity(text="30 days", label="DATE", start=0, end=7)
        result = coder.code_entity(entity)
        assert result.concepts == []
        assert result.review_required is False
        assert result.review_reason is None


class TestExpandedText:
    def test_uses_expanded_text(self, coder):
        entity = Entity(text="TNBC", label="DISEASE", start=0, end=4,
                         expanded_text="Triple Negative Breast Cancer")
        result = coder.code_entity(entity)
        assert result is not None
        assert result.concepts[0].code == "D000073182"
        assert result.concepts[0].match_type == "synonym"

    def test_uses_original_abbreviation_when_expansion_is_less_codable(self, coder):
        entity = Entity(
            text="KRAS",
            label="BIOMARKER",
            start=0,
            end=4,
            expanded_text="Kirsten Rat Sarcoma Viral Oncogene",
        )
        result = coder.code_entity(entity)
        assert result.concepts[0].system == "nci_thesaurus"
        assert result.concepts[0].code == "C126815"
        assert result.concepts[0].match_type == "synonym"


class TestDeterministicResolution:
    def test_scopes_disease_entities_to_mesh(self, coder):
        entity = Entity(text="Melanoma", label="DISEASE", start=0, end=8)
        result = coder.code_entity(entity)
        assert result.concepts[0].system == "mesh"
        assert result.concepts[0].code == "D008545"
        assert result.concepts[0].match_type == "exact"

    def test_normalizes_punctuation_for_biomarker_resolution(self, coder):
        entity = Entity(text="HER2-positive", label="BIOMARKER", start=0, end=13)
        result = coder.code_entity(entity)
        assert result.concepts[0].system == "nci_thesaurus"
        assert result.concepts[0].code == "C68748"
        assert result.concepts[0].match_type == "exact"

    def test_scopes_lab_entities_to_loinc(self, coder):
        entity = Entity(text="ANC", label="LAB_TEST", start=0, end=3)
        result = coder.code_entity(entity)
        assert result.concepts[0].system == "loinc"
        assert result.concepts[0].code == "751-8"
        assert result.concepts[0].match_type == "synonym"

    def test_fuzzy_rejects_generic_lung_cancer_for_specific_subtypes(self, coder):
        entity = Entity(text="lung cancer", label="DISEASE", start=0, end=11)
        result = coder.code_entity(entity)
        assert result.concepts == []

    def test_rejects_conflicting_negated_subtype_candidates(self, coder):
        entity = Entity(text="non-small cell lung cancer", label="DISEASE", start=0, end=27)
        result = coder.code_entity(entity)
        assert result.concepts[0].system == "mesh"
        assert result.concepts[0].code == "D002289"
        assert result.concepts[0].display == "Carcinoma, Non-Small-Cell Lung"

    def test_rejects_conflicting_positive_subtype_candidates(self, coder):
        entity = Entity(text="small cell lung cancer", label="DISEASE", start=0, end=22)
        result = coder.code_entity(entity)
        assert result.concepts[0].system == "mesh"
        assert result.concepts[0].code == "D055752"
        assert result.concepts[0].display == "Small Cell Lung Carcinoma"

    def test_codes_infectious_pulmonary_and_ophthalmology_terms(self, coder):
        cases = [
            ("HIV infection", "D015658"),
            ("active infection", "D007239"),
            ("immunodeficiency", "D007153"),
            ("inflammatory bowel disease", "D015212"),
            ("cardiovascular disorder", "D002318"),
            ("cerebrovascular disease", "D002561"),
            ("cns metastases", "D001859"),
            ("clinically severe pulmonary compromise", "D012131"),
            ("interstitial lung disease", "D017563"),
            ("corneal disease", "D003316"),
            ("dry eye syndrome", "D015352"),
            ("blepharitis", "D001762"),
        ]

        for text, expected_code in cases:
            entity = Entity(text=text, label="DISEASE", start=0, end=len(text))
            result = coder.code_entity(entity)
            assert result.concepts[0].system == "mesh"
            assert result.concepts[0].code == expected_code

    def test_context_variants_help_code_alias_paired_entities(self, coder):
        entity = Entity(text="pneumonitis", label="DISEASE", start=0, end=11)
        result = coder.code_entity(entity, context_variants=["interstitial lung disease"])
        assert result.concepts[0].system == "mesh"
        assert result.concepts[0].code == "D017563"

    def test_disabling_fuzzy_still_allows_synonym_resolution_for_broad_disease_terms(self, coder):
        entity = Entity(text="cardiovascular disorder", label="DISEASE", start=0, end=24)
        result = coder.code_entity(entity, allow_fuzzy=False)
        assert result.concepts[0].system == "mesh"
        assert result.concepts[0].code == "D002318"
        assert result.concepts[0].match_type == "synonym"

    def test_scopes_procedure_entities_to_snomed(self, coder):
        cases = [
            ("archival tumor tissue sample", "17636008"),
            ("newly obtained biopsy", "86273004"),
            ("major surgery", "387713003"),
        ]

        for text, expected_code in cases:
            entity = Entity(text=text, label="PROCEDURE", start=0, end=len(text))
            result = coder.code_entity(entity)
            assert result.concepts[0].system == "snomed_ct"
            assert result.concepts[0].code == expected_code

    def test_codes_pd_l1_therapy_class_to_nci_when_phrase_is_specific(self, coder):
        entity = Entity(text="PD-L1 therapy", label="DRUG", start=0, end=13)
        result = coder.code_entity(entity)
        assert result.concepts[0].system == "nci_thesaurus"
        assert result.concepts[0].code == "C128057"

    def test_codes_pd_1_therapy_class_to_nci_when_phrase_is_specific(self, coder):
        entity = Entity(text="PD-1 therapy", label="DRUG", start=0, end=12)
        result = coder.code_entity(entity)
        assert result.concepts[0].system == "nci_thesaurus"
        assert result.concepts[0].code == "C178320"

    def test_codes_long_form_pd_l1_therapy_class_to_nci_when_phrase_is_specific(self, coder):
        entity = Entity(
            text="programmed death-ligand 1 (PD-L1) therapy",
            label="DRUG",
            start=0,
            end=42,
        )
        result = coder.code_entity(entity, allow_fuzzy=False)
        assert result.concepts[0].system == "nci_thesaurus"
        assert result.concepts[0].code == "C128057"
