from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

FOLLOW_UP_BUCKETS = ("review_required", "missing_data", "clarifiable_blockers", "unsupported")


@dataclass(frozen=True)
class MatchReviewItemSnapshot:
    item_key: str
    bucket: str
    reason_code: str
    category: str
    criterion_text: str
    outcome: str | None
    state: str
    state_reason: str | None
    source_snippet: str | None
    evidence_payload: dict[str, Any] | None
    summary: str | None


def _string_value(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _item_key(*, bucket: str, ordinal: int, category: str, criterion_text: str, reason_code: str) -> str:
    digest_source = "\0".join([category, criterion_text, reason_code])
    digest = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()[:12]
    return f"{bucket}:{ordinal}:{digest}"


def build_match_review_item_snapshots(
    gap_report_payload: dict[str, Any] | None,
) -> list[MatchReviewItemSnapshot]:
    if not isinstance(gap_report_payload, dict):
        return []

    snapshots: list[MatchReviewItemSnapshot] = []
    for bucket in FOLLOW_UP_BUCKETS:
        bucket_items = gap_report_payload.get(bucket, [])
        if not isinstance(bucket_items, list):
            continue
        for ordinal, entry in enumerate(bucket_items):
            if not isinstance(entry, dict):
                continue
            category = _string_value(entry.get("category")) or "logic_group"
            criterion_text = _string_value(entry.get("criterion_text")) or ""
            reason_code = (
                _string_value(entry.get("state_reason"))
                or _string_value(entry.get("kind"))
                or bucket
            )
            state = _string_value(entry.get("state")) or "review_required"
            evidence_payload = entry.get("evidence_payload")
            if not isinstance(evidence_payload, dict):
                evidence_payload = None
            snapshots.append(
                MatchReviewItemSnapshot(
                    item_key=_item_key(
                        bucket=bucket,
                        ordinal=ordinal,
                        category=category,
                        criterion_text=criterion_text,
                        reason_code=reason_code,
                    ),
                    bucket=bucket,
                    reason_code=reason_code,
                    category=category,
                    criterion_text=criterion_text,
                    outcome=_string_value(entry.get("outcome")),
                    state=state,
                    state_reason=_string_value(entry.get("state_reason")),
                    source_snippet=_string_value(entry.get("source_snippet")),
                    evidence_payload=evidence_payload,
                    summary=_string_value(entry.get("summary")),
                )
            )
    return snapshots
