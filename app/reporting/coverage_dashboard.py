from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    CuratedCorpusFixtureCoverageResponse,
    CuratedCorpusMetadataResponse,
    CuratedCorpusSummaryCoverageResponse,
)
from app.api.state import criterion_state_from_extracted
from app.matching.gap_report import legacy_gap_report_payload
from app.models.database import ExtractedCriterion, MatchResult, MatchRun, PipelineRun

COVERAGE_NOTES = [
    "Coverage metrics are operational quality signals for extraction and matching, not clinical performance claims.",
    "Review-required and blocked counts are safety indicators to prioritize, not debt to hide.",
    "Historical rows outside the latest per-patient match snapshot are excluded to avoid drift in coverage totals.",
]
CURATED_CORPUS_SNAPSHOT_PATH = Path(__file__).resolve().parent / "assets" / "curated_corpus_coverage_snapshot.json"
REQUIRED_CURATED_SNAPSHOT_KEYS = {"metadata", "summary", "fixtures"}


def _latest_completed_runs_subquery():
    ranked_runs = (
        select(
            PipelineRun.id.label("id"),
            PipelineRun.trial_id.label("trial_id"),
            func.row_number()
            .over(
                partition_by=PipelineRun.trial_id,
                order_by=(
                    PipelineRun.finished_at.desc().nullslast(),
                    PipelineRun.started_at.desc(),
                    PipelineRun.id.desc(),
                ),
            )
            .label("run_rank"),
        )
        .where(PipelineRun.status == "completed")
        .subquery()
    )
    return select(ranked_runs.c.id, ranked_runs.c.trial_id).where(ranked_runs.c.run_rank == 1)


def _latest_completed_match_run_ids_subquery():
    ranked_runs = (
        select(
            MatchRun.id.label("id"),
            MatchRun.patient_id.label("patient_id"),
            func.row_number()
            .over(
                partition_by=MatchRun.patient_id,
                order_by=(
                    MatchRun.completed_at.desc(),
                    MatchRun.created_at.desc(),
                    MatchRun.id.desc(),
                ),
            )
            .label("run_rank"),
        )
        .where(MatchRun.status == "completed")
        .subquery()
    )
    return select(ranked_runs.c.id, ranked_runs.c.patient_id).where(ranked_runs.c.run_rank == 1)


def _empty_curated_corpus_snapshot() -> dict[str, Any]:
    return {
        "metadata": {
            "generated_at": None,
            "generator": None,
            "fixture_names": [],
            "source": "unavailable",
        },
        "summary": {
            "fixture_count": 0,
            "criteria_count": 0,
            "review_required_count": 0,
            "structurally_exportable_fhir_count": 0,
            "medication_statement_projected_count": 0,
            "blocked_missing_rxnorm_count": 0,
            "blocked_missing_class_code_count": 0,
            "blocked_missing_class_code_terms": {},
            "review_required_ambiguous_class_count": 0,
            "uncoded_but_accepted_count": 0,
            "category_distribution": {},
            "review_reasons": {},
        },
        "fixtures": [],
    }


def _load_curated_corpus_snapshot() -> tuple[dict[str, Any], bool]:
    if not CURATED_CORPUS_SNAPSHOT_PATH.exists():
        return _empty_curated_corpus_snapshot(), False
    try:
        payload = json.loads(CURATED_CORPUS_SNAPSHOT_PATH.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return _empty_curated_corpus_snapshot(), False
    if not isinstance(payload, dict) or not REQUIRED_CURATED_SNAPSHOT_KEYS <= set(payload):
        return _empty_curated_corpus_snapshot(), False
    try:
        metadata = CuratedCorpusMetadataResponse.model_validate(payload.get("metadata")).model_dump(mode="json")
        summary = CuratedCorpusSummaryCoverageResponse.model_validate(payload.get("summary")).model_dump(mode="json")
        fixtures = [
            CuratedCorpusFixtureCoverageResponse.model_validate(item).model_dump(mode="json")
            for item in payload.get("fixtures", [])
        ]
    except Exception:
        return _empty_curated_corpus_snapshot(), False
    return {
        "metadata": metadata,
        "summary": summary,
        "fixtures": fixtures,
    }, True


def _build_extraction_overview(
    criteria_rows: list[tuple[str, bool, str | None, str | None, float | None]],
    latest_run_trial_count: int,
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    state_counts: Counter[str] = Counter()
    review_reason_breakdown: Counter[str] = Counter()
    blocked_criteria_breakdown: Counter[str] = Counter()

    for category, review_required, review_reason, review_status, confidence in criteria_rows:
        criterion = SimpleNamespace(
            category=category,
            review_required=review_required,
            review_reason=review_reason,
            review_status=review_status,
            confidence=confidence,
        )
        state, _ = criterion_state_from_extracted(criterion)
        state_counts[state] += 1
        if review_required and review_status == "pending":
            review_reason_breakdown[review_reason or "unspecified"] += 1
        if state == "blocked_unsupported":
            blocked_criteria_breakdown[category] += 1

    extraction_overview = {
        "latest_run_trial_count": latest_run_trial_count,
        "latest_run_criteria_count": len(criteria_rows),
        "review_pending_count": sum(review_reason_breakdown.values()),
        "structured_safe_count": state_counts["structured_safe"],
        "structured_low_confidence_count": state_counts["structured_low_confidence"],
        "review_required_count": state_counts["review_required"],
        "blocked_unsupported_count": state_counts["blocked_unsupported"],
    }
    return (
        extraction_overview,
        dict(sorted(review_reason_breakdown.items())),
        dict(sorted(blocked_criteria_breakdown.items())),
    )


def _build_matching_overview(
    match_rows: list[
        tuple[
            str,
            dict[str, Any] | None,
            str,
            str | None,
            int,
            int,
            int,
            str | None,
        ]
    ]
) -> dict[str, Any]:
    status_breakdown: Counter[str] = Counter()
    gap_bucket_counts: Counter[str] = Counter()
    persisted_gap_report_count = 0
    legacy_match_count = 0

    for (
        overall_status,
        payload,
        state,
        state_reason,
        unknown_count,
        requires_review_count,
        unfavorable_count,
        summary_explanation,
    ) in match_rows:
        status_breakdown[overall_status] += 1
        if isinstance(payload, dict):
            persisted_gap_report_count += 1
            effective_payload = payload
        else:
            legacy_match_count += 1
            effective_payload = legacy_gap_report_payload(
                SimpleNamespace(
                    overall_status=overall_status,
                    state=state,
                    state_reason=state_reason,
                    unknown_count=unknown_count,
                    requires_review_count=requires_review_count,
                    unfavorable_count=unfavorable_count,
                    summary_explanation=summary_explanation,
                )
            )
        for bucket in (
            "hard_blockers",
            "clarifiable_blockers",
            "missing_data",
            "review_required",
            "unsupported",
        ):
            gap_bucket_counts[bucket] += len(effective_payload.get(bucket) or [])

    return {
        "total_match_results": len(match_rows),
        "persisted_gap_report_count": persisted_gap_report_count,
        "legacy_match_count": legacy_match_count,
        "status_breakdown": dict(sorted(status_breakdown.items())),
        "gap_bucket_counts": {
            "hard_blockers": gap_bucket_counts["hard_blockers"],
            "clarifiable_blockers": gap_bucket_counts["clarifiable_blockers"],
            "missing_data": gap_bucket_counts["missing_data"],
            "review_required": gap_bucket_counts["review_required"],
            "unsupported": gap_bucket_counts["unsupported"],
        },
    }


def build_pipeline_coverage_payload(db: Session) -> dict[str, Any]:
    latest_runs_subquery = _latest_completed_runs_subquery().subquery()
    criteria_rows = (
        db.query(
            ExtractedCriterion.category,
            ExtractedCriterion.review_required,
            ExtractedCriterion.review_reason,
            ExtractedCriterion.review_status,
            ExtractedCriterion.confidence,
        )
        .filter(ExtractedCriterion.pipeline_run_id.in_(select(latest_runs_subquery.c.id)))
        .all()
    )
    latest_run_trial_count = db.query(latest_runs_subquery.c.trial_id).count()
    extraction_overview, review_reason_breakdown, blocked_criteria_breakdown = _build_extraction_overview(
        criteria_rows,
        latest_run_trial_count,
    )

    latest_match_runs_subquery = _latest_completed_match_run_ids_subquery().subquery()
    match_rows = (
        db.query(
            MatchResult.overall_status,
            MatchResult.gap_report_payload,
            MatchResult.state,
            MatchResult.state_reason,
            MatchResult.unknown_count,
            MatchResult.requires_review_count,
            MatchResult.unfavorable_count,
            MatchResult.summary_explanation,
        )
        .filter(MatchResult.match_run_id.in_(select(latest_match_runs_subquery.c.id)))
        .all()
    )
    curated_report, curated_snapshot_available = _load_curated_corpus_snapshot()
    notes = list(COVERAGE_NOTES)
    if not curated_snapshot_available:
        notes.append(
            "Curated corpus snapshot is unavailable in this runtime,"
            " so fixture coverage is omitted instead of recomputing it live."
        )
    return {
        "extraction_overview": extraction_overview,
        "review_reason_breakdown": review_reason_breakdown,
        "blocked_criteria_breakdown": blocked_criteria_breakdown,
        "matching_overview": _build_matching_overview(match_rows),
        "curated_corpus_metadata": curated_report["metadata"],
        "curated_corpus_summary": curated_report["summary"],
        "curated_corpus_fixtures": curated_report["fixtures"],
        "notes": notes,
    }
