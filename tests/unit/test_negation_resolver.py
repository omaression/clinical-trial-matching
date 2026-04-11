import pytest

from app.extraction.negation_resolver import LogicGrouper, NegationResolver, TemporalParser
from app.extraction.types import Entity


@pytest.fixture
def negation():
    return NegationResolver()


@pytest.fixture
def temporal():
    return TemporalParser()


@pytest.fixture
def logic():
    return LogicGrouper()


class TestDistributedNegation:
    def test_negation_across_list(self, negation):
        text = "No prior treatment with trastuzumab, pertuzumab, or lapatinib"
        entities = [
            Entity(text="trastuzumab", label="DRUG", start=28, end=39),
            Entity(text="pertuzumab", label="DRUG", start=41, end=51),
            Entity(text="lapatinib", label="DRUG", start=56, end=65),
        ]
        result = negation.resolve(text, entities)
        assert result.negated is True
        assert result.negated_entities == ["trastuzumab", "pertuzumab", "lapatinib"]

    def test_no_negation(self, negation):
        text = "Histologically confirmed breast cancer"
        entities = [Entity(text="breast cancer", label="DISEASE", start=25, end=38)]
        result = negation.resolve(text, entities)
        assert result.negated is False

    def test_single_entity_negation(self, negation):
        text = "No active brain metastases"
        entities = [Entity(text="brain metastases", label="DISEASE", start=10, end=26)]
        result = negation.resolve(text, entities)
        assert result.negated is True


class TestUnlessClauses:
    def test_unless_splits_criterion(self, negation):
        text = "No prior treatment with trastuzumab, unless administered in the adjuvant setting > 6 months ago"
        entities = [Entity(text="trastuzumab", label="DRUG", start=28, end=39)]
        result = negation.resolve(text, entities)
        assert result.negated is True
        assert result.has_exception is True
        assert "adjuvant" in result.exception_text


class TestNonNegatingPhrases:
    def test_not_limited_to_does_not_trigger_negation(self, negation):
        text = (
            "FGFR 1-3 alterations, including but not limited to amplification, mutation, "
            "fusion/rearrangement"
        )
        entities = [Entity(text="FGFR", label="BIOMARKER", start=0, end=4)]
        result = negation.resolve(text, entities)
        assert result.negated is False

    def test_not_amenable_to_does_not_trigger_negation(self, negation):
        text = "Stage IIIB or IV NSCLC not amenable to curative treatment"
        entities = [Entity(text="NSCLC", label="DISEASE", start=18, end=23)]
        result = negation.resolve(text, entities)
        assert result.negated is False


class TestTemporalParser:
    def test_within_days(self, temporal):
        result = temporal.parse("within 28 days")
        assert result.operator == "within"
        assert result.value == 28
        assert result.unit == "days"

    def test_at_least_months(self, temporal):
        result = temporal.parse("at least 6 months ago")
        assert result.operator == "at_least"
        assert result.value == 6
        assert result.unit == "months"

    def test_no_temporal(self, temporal):
        result = temporal.parse("Histologically confirmed breast cancer")
        assert result is None


class TestLogicGrouper:
    def test_detect_or(self, logic):
        text = "breast cancer OR metastatic disease"
        result = logic.detect(text)
        assert result.operator == "OR"

    def test_detect_and_or(self, logic):
        text = "trastuzumab and/or pertuzumab"
        result = logic.detect(text)
        assert result.operator == "OR"

    def test_default_and(self, logic):
        text = "Age >= 18 years"
        result = logic.detect(text)
        assert result.operator == "AND"
