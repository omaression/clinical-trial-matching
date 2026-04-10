import pytest
from pathlib import Path
from app.extraction.pipeline import ExtractionPipeline
from app.extraction.types import PipelineResult

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="module")
def pipeline():
    return ExtractionPipeline()


class TestSimpleBreastCancer:
    def test_extracts_all_criteria(self, pipeline):
        text = (FIXTURES / "sample_eligibility_texts" / "simple_breast_cancer.txt").read_text()
        result = pipeline.extract(text)
        assert isinstance(result, PipelineResult)
        assert result.criteria_count >= 5
        inclusion = [c for c in result.criteria if c.type == "inclusion"]
        exclusion = [c for c in result.criteria if c.type == "exclusion"]
        assert len(inclusion) >= 3
        assert len(exclusion) >= 2

    def test_age_criterion_parsed(self, pipeline):
        text = (FIXTURES / "sample_eligibility_texts" / "simple_breast_cancer.txt").read_text()
        result = pipeline.extract(text)
        age = [c for c in result.criteria if c.category == "age"]
        assert len(age) == 1
        assert age[0].operator == "gte"
        assert age[0].value_low == 18
        assert age[0].unit == "years"

    def test_exclusion_negated(self, pipeline):
        text = (FIXTURES / "sample_eligibility_texts" / "simple_breast_cancer.txt").read_text()
        result = pipeline.extract(text)
        exclusion = [c for c in result.criteria if c.type == "exclusion"]
        brain = [c for c in exclusion if "brain" in c.original_text.lower()]
        assert len(brain) == 1


class TestMissingHeaders:
    def test_polarity_fallback_classifies_correctly(self, pipeline):
        text = (FIXTURES / "sample_eligibility_texts" / "missing_headers.txt").read_text()
        result = pipeline.extract(text)
        types = {c.type for c in result.criteria}
        assert "inclusion" in types
        assert "exclusion" in types


class TestPipelineVersion:
    def test_version_stamped(self, pipeline):
        result = pipeline.extract("Age >= 18 years")
        assert result.pipeline_version == "0.1.0"


class TestNoCriteriaDropped:
    def test_unparseable_preserved(self, pipeline):
        text = "Adequate renal function as determined by the investigator"
        result = pipeline.extract(text)
        assert result.criteria_count >= 1
        assert any(c.original_text == text for c in result.criteria)
