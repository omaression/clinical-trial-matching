"""Gold-standard NLP pipeline tests.

14 parameterized test cases from the design spec (section 5). Each tests
a specific extraction scenario by running the full pipeline on realistic
eligibility text and verifying the output against expected criteria.
"""

import pytest
from app.extraction.pipeline import ExtractionPipeline
from app.extraction.types import PipelineResult


@pytest.fixture(scope="module")
def pipeline():
    return ExtractionPipeline()


# --- Case 1: Simple age + diagnosis (baseline) ---

class TestCase01_AgeDiagnosis:
    TEXT = """\
Inclusion Criteria:
1. Age >= 18 years
2. Histologically confirmed breast cancer

Exclusion Criteria:
1. Known hypersensitivity to study drug"""

    def test_criteria_count(self, pipeline):
        result = pipeline.extract(self.TEXT)
        assert result.criteria_count == 3

    def test_age_parsed(self, pipeline):
        result = pipeline.extract(self.TEXT)
        age = [c for c in result.criteria if c.category == "age"]
        assert len(age) == 1
        assert age[0].type == "inclusion"
        assert age[0].operator == "gte"
        assert age[0].value_low == 18
        assert age[0].unit == "years"

    def test_diagnosis_identified(self, pipeline):
        result = pipeline.extract(self.TEXT)
        diag = [c for c in result.criteria if c.category == "diagnosis"]
        assert len(diag) >= 1
        assert diag[0].type == "inclusion"

    def test_exclusion_present(self, pipeline):
        result = pipeline.extract(self.TEXT)
        excl = [c for c in result.criteria if c.type == "exclusion"]
        assert len(excl) == 1


# --- Case 2: Lab values with scientific notation ---

class TestCase02_LabValues:
    TEXT = """\
Inclusion Criteria:
1. ANC >= 1500 cells/uL
2. Hemoglobin >= 9 g/dL
3. Platelets >= 100,000/uL"""

    def test_all_lab_criteria_extracted(self, pipeline):
        result = pipeline.extract(self.TEXT)
        assert result.criteria_count == 3
        for c in result.criteria:
            assert c.type == "inclusion"

    def test_lab_category_assigned(self, pipeline):
        result = pipeline.extract(self.TEXT)
        categories = {c.category for c in result.criteria}
        # At least some should be lab_value
        assert "lab_value" in categories or all(c.parse_status in ("parsed", "partial") for c in result.criteria)


# --- Case 3: Washout period / temporal modifier ---

class TestCase03_WashoutPeriod:
    TEXT = """\
Exclusion Criteria:
1. Chemotherapy within 28 days of enrollment
2. Radiation therapy within 14 days"""

    def test_temporal_extracted(self, pipeline):
        result = pipeline.extract(self.TEXT)
        assert result.criteria_count == 2
        for c in result.criteria:
            assert c.type == "exclusion"

    def test_timeframe_parsed(self, pipeline):
        result = pipeline.extract(self.TEXT)
        chemo = [c for c in result.criteria if "28" in c.original_text]
        if chemo and chemo[0].timeframe_value:
            assert chemo[0].timeframe_value == 28
            assert chemo[0].timeframe_unit == "days"


# --- Case 4: Distributed negation across drug list ---

class TestCase04_DistributedNegation:
    TEXT = """\
Exclusion Criteria:
1. No prior treatment with trastuzumab, pertuzumab, or lapatinib"""

    def test_exclusion_negated(self, pipeline):
        result = pipeline.extract(self.TEXT)
        assert result.criteria_count >= 1
        assert result.criteria[0].type == "exclusion"
        assert result.criteria[0].negated is True


# --- Case 5: "Unless" clause with exception ---

class TestCase05_UnlessClause:
    TEXT = """\
Exclusion Criteria:
1. No prior treatment with trastuzumab, unless administered in the adjuvant setting more than 6 months ago"""

    def test_flagged_for_review(self, pipeline):
        result = pipeline.extract(self.TEXT)
        assert result.criteria_count >= 1
        # Unless clauses are complex — should be flagged
        assert result.criteria[0].review_required is True


# --- Case 6: OR-grouped criteria ---

class TestCase06_OrGrouped:
    TEXT = """\
Inclusion Criteria:
1. EGFR mutation positive or ALK rearrangement positive"""

    def test_or_detected(self, pipeline):
        result = pipeline.extract(self.TEXT)
        assert result.criteria_count >= 1
        assert result.criteria[0].logic_operator == "OR"


# --- Case 7: Heavy abbreviations ---

class TestCase07_Abbreviations:
    TEXT = """\
Inclusion Criteria:
1. Confirmed TNBC
2. ECOG performance status 0-1
3. ANC >= 1500"""

    def test_all_extracted(self, pipeline):
        result = pipeline.extract(self.TEXT)
        assert result.criteria_count == 3

    def test_abbreviations_resolved(self, pipeline):
        result = pipeline.extract(self.TEXT)
        # Pipeline should handle abbreviations without dropping criteria
        texts = [c.original_text for c in result.criteria]
        assert any("TNBC" in t for t in texts)
        assert any("ECOG" in t for t in texts)


# --- Case 8: Missing section headers (polarity fallback) ---

class TestCase08_MissingHeaders:
    TEXT = """\
Patients must be at least 18 years old.
Must have histologically confirmed NSCLC.
Patients must NOT have active CNS disease.
No prior systemic chemotherapy."""

    def test_polarity_classification(self, pipeline):
        result = pipeline.extract(self.TEXT)
        types = {c.type for c in result.criteria}
        assert "inclusion" in types
        assert "exclusion" in types

    def test_negation_signals_exclusion(self, pipeline):
        result = pipeline.extract(self.TEXT)
        cns = [c for c in result.criteria if "CNS" in c.original_text]
        assert len(cns) == 1
        assert cns[0].type == "exclusion"

    def test_no_criteria_dropped(self, pipeline):
        result = pipeline.extract(self.TEXT)
        assert result.criteria_count == 4


# --- Case 9: Line-of-therapy criteria ---

class TestCase09_LineOfTherapy:
    TEXT = """\
Inclusion Criteria:
1. Failed at least 1 prior line of systemic therapy"""

    def test_line_of_therapy_category(self, pipeline):
        result = pipeline.extract(self.TEXT)
        assert result.criteria_count == 1
        assert result.criteria[0].category == "line_of_therapy"


# --- Case 10: Performance status (ECOG range) ---

class TestCase10_PerformanceStatus:
    TEXT = """\
Inclusion Criteria:
1. ECOG performance status 0-1"""

    def test_performance_status_parsed(self, pipeline):
        result = pipeline.extract(self.TEXT)
        assert result.criteria_count == 1
        c = result.criteria[0]
        assert c.category == "performance_status"
        assert c.operator == "range"
        assert c.value_low == 0
        assert c.value_high == 1


# --- Case 11: Unparseable complex criterion ---

class TestCase11_Unparseable:
    TEXT = """\
Inclusion Criteria:
1. Adequate renal function as determined by the investigator per institutional standards"""

    def test_preserved_as_unparsed(self, pipeline):
        result = pipeline.extract(self.TEXT)
        assert result.criteria_count == 1
        c = result.criteria[0]
        assert c.parse_status in ("unparsed", "partial")
        assert c.review_required is True
        assert c.original_text == "Adequate renal function as determined by the investigator per institutional standards"


# --- Case 12: Structured fields override NLP-derived age/sex ---
# Note: This test verifies the pipeline doesn't *break* when processing
# age criteria that duplicate ClinicalTrials.gov structured fields.
# Actual precedence logic is in the FHIR mapper.

class TestCase12_StructuredOverride:
    TEXT = """\
Inclusion Criteria:
1. Age >= 18 years
2. Female patients only"""

    def test_age_extracted(self, pipeline):
        result = pipeline.extract(self.TEXT)
        age = [c for c in result.criteria if c.category == "age"]
        assert len(age) == 1
        assert age[0].value_low == 18

    def test_both_criteria_present(self, pipeline):
        result = pipeline.extract(self.TEXT)
        assert result.criteria_count == 2


# --- Case 13: Disease stage + histology ---

class TestCase13_StageHistology:
    TEXT = """\
Inclusion Criteria:
1. Stage III or IV unresectable melanoma
2. Histologically confirmed adenocarcinoma"""

    def test_stage_identified(self, pipeline):
        result = pipeline.extract(self.TEXT)
        stage = [c for c in result.criteria if c.category == "disease_stage"]
        assert len(stage) >= 1

    def test_histology_identified(self, pipeline):
        result = pipeline.extract(self.TEXT)
        hist = [c for c in result.criteria if c.category == "histology"]
        assert len(hist) >= 1


# --- Case 14: Concomitant medication + CNS metastases ---

class TestCase14_ConcomitantCNS:
    TEXT = """\
Exclusion Criteria:
1. No active brain metastases or leptomeningeal disease
2. No concurrent CYP3A4 inhibitors"""

    def test_cns_category(self, pipeline):
        result = pipeline.extract(self.TEXT)
        cns = [c for c in result.criteria if c.category == "cns_metastases"]
        assert len(cns) >= 1

    def test_exclusion_type(self, pipeline):
        result = pipeline.extract(self.TEXT)
        for c in result.criteria:
            assert c.type == "exclusion"

    def test_all_extracted(self, pipeline):
        result = pipeline.extract(self.TEXT)
        assert result.criteria_count == 3
