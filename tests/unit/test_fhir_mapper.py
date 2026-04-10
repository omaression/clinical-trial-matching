import pytest
import uuid
from app.fhir.mapper import FHIRMapper
from app.models.database import Trial, ExtractedCriterion


@pytest.fixture
def sample_trial():
    trial = Trial(
        nct_id="NCT04567890",
        raw_json={"test": True},
        content_hash="abc",
        brief_title="Test Study",
        status="RECRUITING",
        phase="PHASE3",
        conditions=["Breast Cancer"],
        eligible_min_age="18 Years",
        eligible_max_age="75 Years",
        eligible_sex="FEMALE",
    )
    return trial


def _make_criterion(**kwargs):
    """Helper to build an ExtractedCriterion-like object without DB."""
    defaults = {
        "type": "inclusion",
        "category": "other",
        "original_text": "",
        "parse_status": "parsed",
        "confidence": 0.95,
        "pipeline_version": "0.1.0",
        "coded_concepts": [],
        "review_required": False,
        "review_status": None,
        "operator": None,
        "value_low": None,
        "value_high": None,
        "unit": None,
        "negated": False,
    }
    defaults.update(kwargs)

    class FakeCriterion:
        pass

    c = FakeCriterion()
    for k, v in defaults.items():
        setattr(c, k, v)
    return c


@pytest.fixture
def mapper():
    return FHIRMapper()


class TestResearchStudyMapping:
    def test_basic_fields(self, mapper, sample_trial):
        criteria = [
            _make_criterion(type="inclusion", category="age", original_text="Age >= 18"),
        ]
        resource = mapper.to_research_study(sample_trial, criteria)
        assert resource["resourceType"] == "ResearchStudy"
        assert resource["identifier"][0]["value"] == "NCT04567890"
        assert resource["title"] == "Test Study"
        assert resource["status"] == "active"

    def test_phase_mapping(self, mapper, sample_trial):
        resource = mapper.to_research_study(sample_trial, [])
        assert "phase" in resource


class TestCriteriaExclusion:
    def test_unparsed_excluded(self, mapper, sample_trial):
        criteria = [
            _make_criterion(
                type="inclusion", category="other", original_text="Complex text",
                parse_status="unparsed", confidence=0.0, review_required=True,
            ),
        ]
        resource = mapper.to_research_study(sample_trial, criteria)
        ext = resource.get("extension", [])
        # Unparsed should not appear — no inclusion extension at all
        inc_exts = [e for e in ext if e.get("url", "").endswith("inclusion")]
        assert len(inc_exts) == 0

    def test_corrected_included(self, mapper, sample_trial):
        criteria = [
            _make_criterion(
                type="inclusion", category="diagnosis", original_text="TNBC",
                parse_status="parsed", confidence=1.0,
                coded_concepts=[{"system": "mesh", "code": "D000073182", "display": "TNBC"}],
                review_status="corrected",
            ),
        ]
        resource = mapper.to_research_study(sample_trial, criteria)
        ext = resource.get("extension", [])
        inclusion_ext = [e for e in ext if e.get("url", "").endswith("inclusion")]
        assert len(inclusion_ext) > 0
