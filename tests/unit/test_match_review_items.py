from app.matching.review_items import build_match_review_item_snapshots


def test_build_match_review_item_snapshots_persists_follow_up_buckets_only():
    payload = {
        "review_required": [
            {
                "category": "biomarker",
                "criterion_text": "EGFR status unclear",
                "outcome": "unknown",
                "state": "review_required",
                "state_reason": "review_required:manual_review_needed",
                "summary": "Needs adjudication.",
                "source_snippet": "EGFR equivocal",
                "evidence_payload": {"source_snippet": "EGFR equivocal"},
            }
        ],
        "missing_data": [
            {
                "kind": "missing_data",
                "category": "lab_value",
                "criterion_text": "ANC >= 1500/uL",
                "outcome": "unknown",
                "state": "structured_low_confidence",
            }
        ],
        "hard_blockers": [
            {
                "category": "age",
                "criterion_text": "Age < 18",
                "outcome": "not_matched",
                "state": "structured_safe",
            }
        ],
    }

    items = build_match_review_item_snapshots(payload)

    assert [item.bucket for item in items] == ["review_required", "missing_data"]
    assert items[0].reason_code == "review_required:manual_review_needed"
    assert items[0].item_key.startswith("review_required:0:")
    assert items[0].source_snippet == "EGFR equivocal"
    assert items[0].evidence_payload == {"source_snippet": "EGFR equivocal"}
    assert items[1].reason_code == "missing_data"
    assert items[1].item_key.startswith("missing_data:0:")


def test_build_match_review_item_snapshots_ignores_malformed_bucket_values():
    payload = {
        "review_required": {"not": "a list"},
        "unsupported": [
            {
                "category": "concomitant_medication",
                "criterion_text": "No strong CYP3A inhibitors",
                "state": "blocked_unsupported",
            }
        ],
    }

    items = build_match_review_item_snapshots(payload)

    assert len(items) == 1
    assert items[0].bucket == "unsupported"
    assert items[0].reason_code == "unsupported"
    assert items[0].state == "blocked_unsupported"
