from app.extraction.types import (
    ClassifiedCriterion,
    CriterionText,
    Entity,
    PipelineResult,
    QuantitativeValue,
)


def test_criterion_text_defaults():
    ct = CriterionText(text="Age >= 18", type="inclusion")
    assert ct.review_required is False
    assert ct.review_reason is None


def test_entity_with_expansion():
    e = Entity(text="TNBC", label="DISEASE", start=0, end=4, expanded_text="Triple Negative Breast Cancer")
    assert e.expanded_text == "Triple Negative Breast Cancer"
    assert e.display_text == "TNBC"


def test_entity_without_expansion():
    e = Entity(text="breast cancer", label="DISEASE", start=0, end=13)
    assert e.expanded_text is None
    assert e.display_text == "breast cancer"


def test_quantitative_value_range():
    qv = QuantitativeValue(operator="range", value_low=0, value_high=1, unit=None, raw_expression="0-1")
    assert qv.operator == "range"


def test_classified_criterion_unparsed():
    cc = ClassifiedCriterion.unparsed(original_text="Complex criterion text", type="inclusion")
    assert cc.parse_status == "unparsed"
    assert cc.category == "other"
    assert cc.confidence == 0.0
    assert cc.review_required is True


def test_pipeline_result_counts():
    c1 = ClassifiedCriterion(
        original_text="Age >= 18",
        type="inclusion",
        category="age",
        parse_status="parsed",
        confidence=0.95,
    )
    c2 = ClassifiedCriterion(
        original_text="Complex thing",
        type="inclusion",
        category="other",
        parse_status="unparsed",
        confidence=0.0,
        review_required=True,
    )
    result = PipelineResult(criteria=[c1, c2], pipeline_version="0.1.1")
    assert result.criteria_count == 2
    assert result.review_required_count == 1
