import pytest

from app.extraction.criteria_classifier import RuleBasedClassifier
from app.extraction.types import Entity


@pytest.fixture
def classifier():
    return RuleBasedClassifier()


class TestCategoryAssignment:
    def test_age_criterion(self, classifier):
        result = classifier.classify(
            "Age >= 18 years",
            [Entity(text="18 years", label="MEASURE", start=7, end=15)],
        )
        assert result.category == "age"
        assert result.operator == "gte"
        assert result.value_low == 18
        assert result.unit == "years"

    def test_diagnosis_criterion(self, classifier):
        result = classifier.classify(
            "Histologically confirmed breast cancer",
            [Entity(text="breast cancer", label="DISEASE", start=25, end=38)],
        )
        assert result.category == "diagnosis"

    def test_biomarker_criterion(self, classifier):
        result = classifier.classify(
            "HER2-positive",
            [Entity(text="HER2", label="BIOMARKER", start=0, end=4)],
        )
        assert result.category == "biomarker"
        assert result.value_text == "positive"

    def test_lab_value_criterion(self, classifier):
        result = classifier.classify(
            "ANC ≥ 1500 cells/μL",
            [
                Entity(text="ANC", label="LAB_TEST", start=0, end=3),
                Entity(text="1500 cells/μL", label="MEASURE", start=6, end=19),
            ],
        )
        assert result.category == "lab_value"
        assert result.operator == "gte"

    def test_performance_status(self, classifier):
        result = classifier.classify(
            "ECOG performance status 0-1",
            [
                Entity(text="ECOG", label="PERF_SCALE", start=0, end=4),
                Entity(text="0-1", label="MEASURE", start=24, end=27),
            ],
        )
        assert result.category == "performance_status"
        assert result.operator == "range"
        assert result.value_low == 0
        assert result.value_high == 1

    def test_prior_therapy_with_temporal(self, classifier):
        result = classifier.classify(
            "No prior chemotherapy within 28 days of enrollment",
            [
                Entity(text="chemotherapy", label="DRUG", start=9, end=21),
                Entity(text="28 days", label="TIMEFRAME", start=29, end=36),
            ],
        )
        assert result.category == "prior_therapy"
        assert result.negated is True
        assert result.timeframe_operator == "within"
        assert result.timeframe_value == 28
        assert result.timeframe_unit == "days"

    def test_line_of_therapy(self, classifier):
        result = classifier.classify(
            "Failed at least 1 prior line of systemic therapy",
            [Entity(text="1", label="MEASURE", start=16, end=17)],
        )
        assert result.category == "line_of_therapy"

    def test_cns_metastases(self, classifier):
        result = classifier.classify(
            "No active brain metastases",
            [Entity(text="brain metastases", label="DISEASE", start=10, end=26)],
        )
        assert result.category == "cns_metastases"
        assert result.negated is True

    def test_concomitant_medication_from_inhibitor_language(self, classifier):
        result = classifier.classify(
            "No concurrent CYP3A4 inhibitors",
            [],
        )
        assert result.category == "concomitant_medication"
        assert result.parse_status == "parsed"
        assert result.review_required is False

    def test_hypersensitivity_text_only_becomes_partial_not_unparsed(self, classifier):
        result = classifier.classify(
            "Known hypersensitivity to study drug",
            [],
        )
        assert result.category == "other"
        assert result.parse_status == "partial"
        assert result.review_required is False
        assert result.review_reason is None

    def test_age_sentence_routes_to_age_threshold(self, classifier):
        result = classifier.classify(
            "Patients must be at least 18 years old.",
            [Entity(text="18 years", label="MEASURE", start=26, end=34)],
        )
        assert result.category == "age"
        assert result.operator == "gte"
        assert result.value_low == 18
        assert result.unit == "years"
        assert result.timeframe_operator is None

    def test_sex_only_text_becomes_partial_supplementary_criterion(self, classifier):
        result = classifier.classify(
            "Female patients only",
            [],
        )
        assert result.category == "other"
        assert result.parse_status == "partial"
        assert result.value_text == "female"
        assert result.raw_expression == "Female patients only"
        assert result.review_required is False

    def test_text_only_washout_therapy_routes_to_prior_therapy(self, classifier):
        result = classifier.classify(
            "Chemotherapy within 28 days of enrollment",
            [Entity(text="28 days", label="DATE", start=20, end=27)],
        )
        assert result.category == "prior_therapy"
        assert result.timeframe_operator == "within"
        assert result.timeframe_value == 28
        assert result.timeframe_unit == "days"

    def test_prior_therapy_signal_beats_stage_language(self, classifier):
        result = classifier.classify(
            "No prior systemic chemotherapy for metastatic disease.",
            [Entity(text="chemotherapy", label="DRUG", start=18, end=30)],
        )
        assert result.category == "prior_therapy"
        assert result.negated is True

    def test_text_only_histology_becomes_parsed_without_review(self, classifier):
        result = classifier.classify(
            "Histologically confirmed adenocarcinoma",
            [],
        )
        assert result.category == "histology"
        assert result.parse_status == "parsed"
        assert result.review_required is False

    def test_text_only_concomitant_medication_becomes_parsed_without_review(self, classifier):
        result = classifier.classify(
            "No concurrent CYP3A4 inhibitors",
            [],
        )
        assert result.category == "concomitant_medication"
        assert result.parse_status == "parsed"
        assert result.review_required is False

    def test_simple_organ_function_becomes_parsed_without_review(self, classifier):
        result = classifier.classify(
            "Must have adequate organ function.",
            [],
        )
        assert result.category == "organ_function"
        assert result.parse_status == "parsed"
        assert result.review_required is False

    def test_text_only_cyp3a4_exception_becomes_reviewable_concomitant_medication(self, classifier):
        result = classifier.classify(
            (
                "Concurrent use of weak, moderate and strong CYP3A4 inhibitors/inducers "
                "(except for systemic itraconazole, ketoconazole, posaconazole, or "
                "voriconazole, which should have been started at least 7 days prior to enrolment)."
            ),
            [Entity(text="at least 7 days", label="DATE", start=182, end=197)],
        )
        assert result.category == "concomitant_medication"
        assert result.parse_status == "partial"
        assert result.timeframe_operator == "at_least"
        assert result.timeframe_value == 7
        assert result.timeframe_unit == "days"
        assert result.logic_operator == "OR"
        assert result.review_required is True
        assert result.review_reason == "complex_criteria"

    def test_text_only_cyp3a4_washout_becomes_reviewable_concomitant_medication(self, classifier):
        result = classifier.classify(
            (
                "Use of any moderate-strong CYP3A4 inhibitor or inducer within 14 days "
                "or 5 plasma half-lives (whichever is longer) prior to the administration "
                "of IMP and for the duration of the trial."
            ),
            [
                Entity(text="14 days", label="DATE", start=62, end=69),
                Entity(text="5", label="CARDINAL", start=73, end=74),
                Entity(text="half", label="CARDINAL", start=82, end=86),
                Entity(text="IMP", label="ORG", start=146, end=149),
            ],
        )
        assert result.category == "concomitant_medication"
        assert result.parse_status == "partial"
        assert result.timeframe_operator == "within"
        assert result.timeframe_value == 14
        assert result.timeframe_unit == "days"
        assert result.logic_operator == "OR"
        assert result.review_required is True
        assert result.review_reason == "complex_criteria"

    def test_genetic_variants_text_routes_to_molecular_alteration(self, classifier):
        result = classifier.classify(
            "Genetic variants of tumor tissue detected by NGS.",
            [Entity(text="NGS", label="ORG", start=43, end=46)],
        )
        assert result.category == "molecular_alteration"
        assert result.parse_status == "parsed"
        assert result.negated is False
        assert result.review_required is False

    def test_fgfr_not_limited_to_clause_stays_non_negated_reviewable_partial(self, classifier):
        result = classifier.classify(
            (
                "Histologically confirmed FGFR 1-3 alterations, including but not limited to "
                "amplification, mutation, fusion/rearrangement, etc."
            ),
            [Entity(text="FGFR", label="BIOMARKER", start=26, end=30)],
        )
        assert result.category == "molecular_alteration"
        assert result.parse_status == "partial"
        assert result.negated is False
        assert result.review_required is True
        assert result.review_reason == "complex_criteria"


class TestComplexityRouting:
    def test_complex_flagged_for_review(self, classifier):
        result = classifier.classify(
            (
                "No prior treatment with trastuzumab, unless administered in the "
                "adjuvant setting > 6 months ago, or pertuzumab"
            ),
            [
                Entity(text="trastuzumab", label="DRUG", start=28, end=39),
                Entity(text="pertuzumab", label="DRUG", start=98, end=108),
            ],
        )
        assert result.review_required is True
        assert result.review_reason == "complex_criteria"

    def test_text_only_unless_clause_keeps_negation_and_exception_timeframe(self, classifier):
        result = classifier.classify(
            "No prior treatment with trastuzumab, unless administered in the adjuvant setting more than 6 months ago",
            [],
        )
        assert result.category == "prior_therapy"
        assert result.parse_status == "partial"
        assert result.negated is True
        assert result.timeframe_operator == "at_least"
        assert result.timeframe_value == 6
        assert result.timeframe_unit == "months"
        assert result.review_required is True


class TestUnparsedPreservation:
    def test_investigator_defined_organ_function_stays_reviewable(self, classifier):
        result = classifier.classify("Adequate renal function as determined by investigator", [])
        assert result.category == "organ_function"
        assert result.parse_status == "partial"
        assert result.original_text == "Adequate renal function as determined by investigator"
        assert result.review_required is True
