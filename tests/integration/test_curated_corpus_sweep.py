from collections import Counter
from pathlib import Path

import pytest

from app.extraction.pipeline import ExtractionPipeline

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_eligibility_texts"


@pytest.fixture(scope="module")
def pipeline():
    return ExtractionPipeline()


@pytest.mark.parametrize(
    ("fixture_name", "expected_count", "expected_review_count", "required_categories"),
    [
        (
            "therapy_class_and_procedures",
            9,
            0,
            {"prior_therapy", "procedural_requirement", "diagnosis", "cns_metastases"},
        ),
        ("medication_exception_logic", 3, 0, {"concomitant_medication"}),
        ("nct07084584_cyp3a4_exception", 1, 0, {"concomitant_medication"}),
        ("nct03872596_cyp3a4_washout", 1, 1, {"concomitant_medication"}),
        ("nct05346328_stage_biomarker", 1, 1, {"disease_stage"}),
        ("nct05346328_line_of_therapy", 1, 1, {"prior_therapy"}),
    ],
)
def test_curated_corpus_sweep_metrics(
    pipeline,
    fixture_name: str,
    expected_count: int,
    expected_review_count: int,
    required_categories: set[str],
):
    text = (FIXTURES / f"{fixture_name}.txt").read_text()
    result = pipeline.extract(text)

    category_counts = Counter(criterion.category for criterion in result.criteria)
    review_count = sum(1 for criterion in result.criteria if criterion.review_required)

    assert result.criteria_count == expected_count
    assert review_count == expected_review_count
    assert required_categories <= set(category_counts)
    assert not any(
        criterion.category == "other" and criterion.parse_status == "unparsed"
        for criterion in result.criteria
    )
