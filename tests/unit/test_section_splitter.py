import pytest
from pathlib import Path
from app.extraction.section_splitter import SectionSplitter

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_eligibility_texts"


@pytest.fixture
def splitter():
    return SectionSplitter()


class TestStructuredHeaders:
    def test_simple_inclusion_exclusion(self, splitter):
        text = (FIXTURES / "simple_breast_cancer.txt").read_text()
        results = splitter.split(text)
        inclusion = [r for r in results if r.type == "inclusion"]
        exclusion = [r for r in results if r.type == "exclusion"]
        assert len(inclusion) == 3
        assert len(exclusion) == 2
        assert "Age >= 18" in inclusion[0].text
        assert "brain metastases" in exclusion[0].text

    def test_criteria_stripped_of_numbering(self, splitter):
        text = (FIXTURES / "simple_breast_cancer.txt").read_text()
        results = splitter.split(text)
        for r in results:
            assert not r.text.startswith(("1.", "2.", "3."))


class TestMissingHeaders:
    def test_polarity_fallback(self, splitter):
        text = (FIXTURES / "missing_headers.txt").read_text()
        results = splitter.split(text)
        cns = [r for r in results if "CNS" in r.text]
        assert len(cns) == 1
        assert cns[0].type == "exclusion"
        chemo = [r for r in results if "chemotherapy" in r.text]
        assert len(chemo) == 1
        assert chemo[0].type == "exclusion"

    def test_positive_defaults_to_inclusion(self, splitter):
        text = (FIXTURES / "missing_headers.txt").read_text()
        results = splitter.split(text)
        age = [r for r in results if "18 years" in r.text]
        assert len(age) == 1
        assert age[0].type == "inclusion"


class TestMixedPolarity:
    def test_polarity_override_flags_review(self, splitter):
        text = (FIXTURES / "mixed_polarity.txt").read_text()
        results = splitter.split(text)
        immuno = [r for r in results if "immunotherapy" in r.text]
        assert len(immuno) == 1
        assert immuno[0].type == "exclusion"
        assert immuno[0].review_required is True
        assert immuno[0].review_reason == "polarity_override"


class TestEdgeCases:
    def test_empty_text(self, splitter):
        assert splitter.split("") == []

    def test_single_criterion(self, splitter):
        results = splitter.split("Age >= 18 years")
        assert len(results) == 1
        assert results[0].type == "inclusion"
