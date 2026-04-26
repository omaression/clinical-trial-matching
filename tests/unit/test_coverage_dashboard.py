from pathlib import Path

from app.reporting import coverage_dashboard
from app.scripts.curated_corpus_report import build_curated_corpus_report


def test_load_curated_corpus_snapshot_returns_empty_payload_when_artifact_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(
        coverage_dashboard,
        "CURATED_CORPUS_SNAPSHOT_PATH",
        Path(tmp_path) / "missing-curated-corpus-snapshot.json",
    )

    snapshot, available = coverage_dashboard._load_curated_corpus_snapshot()

    assert available is False
    assert snapshot["metadata"]["source"] == "unavailable"
    assert snapshot["summary"]["fixture_count"] == 0
    assert snapshot["summary"]["criteria_count"] == 0
    assert snapshot["fixtures"] == []


def test_load_curated_corpus_snapshot_returns_empty_payload_when_json_is_malformed(monkeypatch, tmp_path):
    malformed_path = Path(tmp_path) / "curated-corpus-coverage-snapshot.json"
    malformed_path.write_text("{not valid json")
    monkeypatch.setattr(coverage_dashboard, "CURATED_CORPUS_SNAPSHOT_PATH", malformed_path)

    snapshot, available = coverage_dashboard._load_curated_corpus_snapshot()

    assert available is False
    assert snapshot["metadata"]["source"] == "unavailable"
    assert snapshot["fixtures"] == []


def test_load_curated_corpus_snapshot_returns_empty_payload_when_shape_is_invalid(monkeypatch, tmp_path):
    invalid_path = Path(tmp_path) / "curated-corpus-coverage-snapshot.json"
    invalid_path.write_text('{"metadata": {}, "summary": {}, "fixtures": []}')
    monkeypatch.setattr(coverage_dashboard, "CURATED_CORPUS_SNAPSHOT_PATH", invalid_path)

    snapshot, available = coverage_dashboard._load_curated_corpus_snapshot()

    assert available is False
    assert snapshot["metadata"]["source"] == "unavailable"


def test_checked_in_curated_corpus_snapshot_has_provenance_metadata():
    snapshot, available = coverage_dashboard._load_curated_corpus_snapshot()

    assert available is True
    assert snapshot["metadata"]["source"] == "checked_in_snapshot"
    assert snapshot["metadata"]["generator"] == "app.scripts.curated_corpus_report.build_curated_corpus_report"
    assert snapshot["metadata"]["generated_at"]
    assert snapshot["metadata"]["fixture_names"]
    assert snapshot["summary"]["fixture_count"] == len(snapshot["fixtures"])


def test_checked_in_curated_corpus_snapshot_matches_current_curated_report():
    snapshot, available = coverage_dashboard._load_curated_corpus_snapshot()

    assert available is True
    current_report = build_curated_corpus_report(snapshot["metadata"]["fixture_names"])
    assert snapshot["summary"] == current_report["summary"]
    assert snapshot["fixtures"] == current_report["fixtures"]


def test_legacy_gap_report_payload_handles_null_counts():
    report = coverage_dashboard.legacy_gap_report_payload(
        type(
            "HistoricalMatchResult",
            (),
            {
                "overall_status": "possible",
                "state": "review_required",
                "state_reason": None,
                "unknown_count": None,
                "requires_review_count": None,
                "unfavorable_count": None,
                "summary_explanation": "Historical uncertainty",
            },
        )()
    )

    assert report["review_required"]
