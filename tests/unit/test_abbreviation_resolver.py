import pytest

from app.extraction.abbreviation_resolver import AbbreviationResolver
from app.extraction.types import Entity


@pytest.fixture
def resolver():
    return AbbreviationResolver(dict_path="data/dictionaries/onc_abbreviations.jsonl")


class TestStaticDictionary:
    def test_expand_known_abbreviation(self, resolver):
        entities = [Entity(text="TNBC", label="DISEASE", start=0, end=4)]
        resolved = resolver.resolve(entities, "Patient has TNBC")
        assert resolved[0].expanded_text == "Triple Negative Breast Cancer"
        assert resolved[0].text == "TNBC"

    def test_expand_lab_abbreviation(self, resolver):
        entities = [Entity(text="ANC", label="LAB_TEST", start=0, end=3)]
        resolved = resolver.resolve(entities, "ANC >= 1500")
        assert resolved[0].expanded_text == "Absolute Neutrophil Count"

    def test_unknown_abbreviation_unchanged(self, resolver):
        entities = [Entity(text="XYZ123", label="DISEASE", start=0, end=6)]
        resolved = resolver.resolve(entities, "XYZ123 positive")
        assert resolved[0].expanded_text is None

    def test_case_insensitive_lookup(self, resolver):
        entities = [Entity(text="tnbc", label="DISEASE", start=0, end=4)]
        resolved = resolver.resolve(entities, "tnbc diagnosis")
        assert resolved[0].expanded_text == "Triple Negative Breast Cancer"

    def test_multi_word_entity_not_expanded(self, resolver):
        entities = [Entity(text="breast cancer", label="DISEASE", start=0, end=13)]
        resolved = resolver.resolve(entities, "breast cancer")
        assert resolved[0].expanded_text is None


class TestLookupText:
    def test_lookup_uses_expanded(self, resolver):
        entities = [Entity(text="TNBC", label="DISEASE", start=0, end=4)]
        resolved = resolver.resolve(entities, "TNBC")
        assert resolved[0].lookup_text == "Triple Negative Breast Cancer"

    def test_lookup_falls_back_to_original(self, resolver):
        entities = [Entity(text="trastuzumab", label="DRUG", start=0, end=11)]
        resolved = resolver.resolve(entities, "trastuzumab")
        assert resolved[0].lookup_text == "trastuzumab"


class TestDynamicAbbreviations:
    def test_dynamic_abbreviation_expands_when_not_in_static_dictionary(self, resolver):
        entities = [Entity(text="NSCLC", label="DISEASE", start=0, end=5)]
        resolved = resolver.resolve(
            entities,
            "non-small cell lung cancer (NSCLC)",
            dynamic_abbreviations={"nsclc": "non-small cell lung cancer"},
        )
        assert resolved[0].expanded_text == "non-small cell lung cancer"
