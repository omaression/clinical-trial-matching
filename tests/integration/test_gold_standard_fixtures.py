import json
from pathlib import Path

import pytest

from app.extraction.pipeline import ExtractionPipeline

FIXTURES = Path(__file__).parent.parent / "fixtures"
TEXT_FIXTURES = FIXTURES / "sample_eligibility_texts"
EXPECTED_FIXTURES = FIXTURES / "expected_criteria"


def _load_gold_fixtures():
    params = []
    for expected_path in sorted(EXPECTED_FIXTURES.glob("*.json")):
        name = expected_path.stem
        text_path = TEXT_FIXTURES / f"{name}.txt"
        if not text_path.exists():
            continue
        params.append(
            pytest.param(
                name,
                text_path.read_text(),
                json.loads(expected_path.read_text()),
                id=name,
            )
        )
    return params


@pytest.fixture(scope="module")
def pipeline():
    return ExtractionPipeline()


@pytest.mark.parametrize(("name", "text", "expected"), _load_gold_fixtures())
def test_gold_standard_fixture_matches_expected_fields(name, text, expected, pipeline):
    result = pipeline.extract(text)
    assert result.criteria_count == len(expected), name

    for actual, expected_criterion in zip(result.criteria, expected):
        actual_payload = actual.model_dump()
        actual_payload.pop("entities", None)
        actual_payload["coded_concepts"] = [
            concept.model_dump() if hasattr(concept, "model_dump") else concept
            for concept in actual_payload.get("coded_concepts", [])
        ]
        actual_payload.pop("logic_group_id", None)

        for field, expected_value in expected_criterion.items():
            assert actual_payload[field] == expected_value, (
                f"{name}: expected {field}={expected_value!r}, got {actual_payload[field]!r}"
            )
