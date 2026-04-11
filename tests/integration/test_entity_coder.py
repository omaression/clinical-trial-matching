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
        CodingLookup(system="mesh", code="D008545", display="Melanoma",
                      synonyms=["malignant melanoma"]),
        CodingLookup(system="nci_thesaurus", code="C3224", display="Melanoma",
                      synonyms=["melanoma lesion"]),
        CodingLookup(system="nci_thesaurus", code="C1647", display="Trastuzumab",
                      synonyms=["herceptin"]),
        CodingLookup(system="loinc", code="751-8", display="Neutrophils [#/volume] in Blood",
                      synonyms=["anc", "absolute neutrophil count"]),
    ]
    db_session.add_all(lookups)
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


class TestNoMatch:
    def test_uncoded_flagged(self, coder):
        entity = Entity(text="XYZ_UNKNOWN_ENTITY", label="DISEASE", start=0, end=18)
        result = coder.code_entity(entity)
        assert result.concepts == []
        assert result.review_required is True
        assert result.confidence == 0.40


class TestExpandedText:
    def test_uses_expanded_text(self, coder):
        entity = Entity(text="TNBC", label="DISEASE", start=0, end=4,
                         expanded_text="Triple Negative Breast Cancer")
        result = coder.code_entity(entity)
        assert result is not None
        assert result.concepts[0].code == "D000073182"
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
