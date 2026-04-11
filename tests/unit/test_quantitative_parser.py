import pytest

from app.extraction.quantitative_parser import QuantitativeParser


@pytest.fixture
def parser():
    return QuantitativeParser()


class TestComparisonOperators:
    def test_gte_symbol(self, parser):
        result = parser.parse("≥ 18 years", [])
        assert result.operator == "gte"
        assert result.value_low == 18
        assert result.unit == "years"

    def test_gte_word(self, parser):
        result = parser.parse("at least 18 years", [])
        assert result.operator == "gte"
        assert result.value_low == 18

    def test_lte_symbol(self, parser):
        result = parser.parse("≤ 2.5× ULN", [])
        assert result.operator == "lte"
        assert result.value_low == 2.5
        assert result.unit == "× ULN"

    def test_gt_symbol(self, parser):
        result = parser.parse("> 50%", [])
        assert result.operator == "gte"
        assert result.value_low == 50
        assert result.unit == "%"


class TestRanges:
    def test_simple_range(self, parser):
        result = parser.parse("0-1", [])
        assert result.operator == "range"
        assert result.value_low == 0
        assert result.value_high == 1

    def test_word_range(self, parser):
        result = parser.parse("0 to 1", [])
        assert result.operator == "range"
        assert result.value_low == 0
        assert result.value_high == 1

    def test_age_range(self, parser):
        result = parser.parse("18-65 years", [])
        assert result.operator == "range"
        assert result.value_low == 18
        assert result.value_high == 65
        assert result.unit == "years"

    def test_trailing_punctuation_is_removed_from_unit(self, parser):
        result = parser.parse("Age >= 18 years.", [])
        assert result.operator == "gte"
        assert result.value_low == 18
        assert result.unit == "years"


class TestScientificNotation:
    def test_sci_notation(self, parser):
        result = parser.parse("≥ 1.5 x 10⁹/L", [])
        assert result.operator == "gte"
        assert result.value_low == pytest.approx(1.5e9)
        assert result.unit == "/L"

    def test_percentage(self, parser):
        result = parser.parse("≥ 1%", [])
        assert result.operator == "gte"
        assert result.value_low == 1
        assert result.unit == "%"


class TestRawExpression:
    def test_raw_expression_preserved(self, parser):
        result = parser.parse("≥ 1.5 x 10⁹/L", [])
        assert result.raw_expression == "≥ 1.5 x 10⁹/L"


class TestNoMatch:
    def test_non_quantitative_returns_none(self, parser):
        result = parser.parse("Histologically confirmed breast cancer", [])
        assert result is None
