from collections import Counter
from pathlib import Path

import pytest

from app.extraction.pipeline import ExtractionPipeline
from app.scripts.curated_corpus_report import build_curated_corpus_report

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


def test_curated_corpus_report_summarizes_fixture_metrics():
    report = build_curated_corpus_report(["therapy_class_and_procedures", "medication_exception_logic"])

    assert report["summary"]["fixture_count"] == 2
    assert report["summary"]["criteria_count"] == 12
    assert report["summary"]["review_required_count"] == 0
    assert report["summary"]["structurally_exportable_fhir_count"] == 2
    assert report["summary"]["medication_statement_projected_count"] == 5
    assert report["summary"]["blocked_missing_class_code_count"] == 4
    assert report["summary"]["blocked_missing_rxnorm_count"] == 0
    assert report["summary"]["review_required_ambiguous_class_count"] == 1
    fixture_names = [fixture["fixture"] for fixture in report["fixtures"]]
    assert fixture_names == ["therapy_class_and_procedures", "medication_exception_logic"]

    therapy_fixture = next(
        fixture for fixture in report["fixtures"] if fixture["fixture"] == "therapy_class_and_procedures"
    )
    assert therapy_fixture["structurally_exportable_fhir_count"] == 2
    assert therapy_fixture["medication_statement_projected_count"] == 0
    assert therapy_fixture["blocked_missing_class_code_count"] == 1
    assert therapy_fixture["review_required_ambiguous_class_count"] == 1

    medication_fixture = next(
        fixture for fixture in report["fixtures"] if fixture["fixture"] == "medication_exception_logic"
    )
    assert medication_fixture["structurally_exportable_fhir_count"] == 0
    assert medication_fixture["medication_statement_projected_count"] == 5
    assert medication_fixture["blocked_missing_class_code_count"] == 3
