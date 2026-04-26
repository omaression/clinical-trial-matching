from __future__ import annotations

from types import SimpleNamespace
from typing import Any


def _label_for_category(category: str) -> str:
    return category.replace("_", " ").title()


def _source_snippet_for_payload(evidence_payload: dict[str, Any] | None) -> str | None:
    if not isinstance(evidence_payload, dict):
        return None
    explicit_snippet = evidence_payload.get("source_snippet") or evidence_payload.get("source_text")
    if isinstance(explicit_snippet, str) and explicit_snippet.strip():
        return explicit_snippet.strip()
    return None


def _patient_flag_field_name(item) -> str | None:
    evidence = getattr(item, "evidence_payload", None)
    if not isinstance(evidence, dict):
        return None
    patient_flag_field = evidence.get("patient_flag_field")
    if isinstance(patient_flag_field, str) and patient_flag_field:
        return patient_flag_field
    return None


def _has_missing_patient_data(item) -> bool:
    state_reason = getattr(item, "state_reason", None)
    if state_reason == "legacy_state_unverifiable":
        return False

    evidence = getattr(item, "evidence_payload", None)
    if not isinstance(evidence, dict):
        return False

    if evidence.get("snapshot_missing_data") is True:
        return True

    scalar_patient_keys = (
        "patient_age_years",
        "patient_sex",
        "patient_is_healthy_volunteer",
        "patient_ecog_status",
    )
    if any(key in evidence and evidence[key] is None for key in scalar_patient_keys):
        return True

    list_patient_keys = (
        "patient_conditions",
        "patient_biomarkers",
        "patient_labs",
        "patient_therapies",
    )
    if any(key in evidence and isinstance(evidence[key], list) and not evidence[key] for key in list_patient_keys):
        return True

    if getattr(item, "category", None) == "lab_value":
        labs = evidence.get("patient_labs")
        if (
            isinstance(labs, list)
            and labs
            and all(lab.get("value_numeric") is None for lab in labs if isinstance(lab, dict))
        ):
            return True

    if getattr(item, "category", None) in {"prior_therapy", "line_of_therapy"}:
        therapies = evidence.get("patient_therapies")
        if isinstance(therapies, list) and therapies and all(
            therapy.get("line_of_therapy") is None for therapy in therapies if isinstance(therapy, dict)
        ):
            return True

    patient_flags = evidence.get("patient_flags")
    if isinstance(patient_flags, dict):
        field_name = _patient_flag_field_name(item)
        if field_name and patient_flags.get(field_name) is None:
            return True

    if getattr(item, "category", None) == "concomitant_medication":
        medications = evidence.get("patient_medications")
        if not isinstance(medications, list) or not medications:
            return True
        if evidence.get("exception_logic") or evidence.get("allowance_text"):
            return False
        if any(
            evidence.get(key) is not None
            for key in ("timeframe_operator", "timeframe_value", "timeframe_unit")
        ):
            return False
        return False

    return False


def _is_hard_blocker(item) -> bool:
    return getattr(item, "state", None) == "structured_safe"


def _group_key(item) -> tuple[object, str] | None:
    evidence = getattr(item, "evidence_payload", None)
    if not isinstance(evidence, dict):
        return None
    snapshot_metadata = evidence.get("snapshot_match_metadata")
    if isinstance(snapshot_metadata, dict):
        logic_group_id = snapshot_metadata.get("logic_group_id")
        logic_operator = snapshot_metadata.get("logic_operator")
        if logic_group_id and logic_operator == "OR":
            return logic_group_id, logic_operator
    logic_group_id = evidence.get("logic_group_id")
    logic_operator = evidence.get("logic_operator")
    if logic_group_id and logic_operator == "OR":
        return logic_group_id, logic_operator
    return None


def _collapsed_group_state(items: list[Any]) -> tuple[str, str | None, str | None]:
    exemplar = items[0]
    outcomes = {getattr(item, "outcome", None) for item in items}
    criterion_type = getattr(exemplar, "criterion_type", None)

    if criterion_type == "inclusion":
        if "matched" in outcomes:
            outcome = "matched"
        elif "requires_review" in outcomes:
            outcome = "requires_review"
        elif "unknown" in outcomes:
            outcome = "unknown"
        else:
            outcome = "not_matched"
    else:
        if "triggered" in outcomes:
            outcome = "triggered"
        elif "requires_review" in outcomes:
            outcome = "requires_review"
        elif "unknown" in outcomes:
            outcome = "unknown"
        else:
            outcome = "not_triggered"

    matching_members = [item for item in items if getattr(item, "outcome", None) == outcome] or items
    state_members = items if outcome in {"not_matched", "not_triggered", "unknown"} else matching_members
    member_states = {getattr(item, "state", None) for item in state_members}

    if outcome in {"not_matched", "not_triggered", "unknown"}:
        if "review_required" in member_states:
            return outcome, "review_required", "review_required"
        if "blocked_unsupported" in member_states:
            return outcome, "blocked_unsupported", "blocked_unsupported"
        if "structured_low_confidence" in member_states:
            return outcome, "structured_low_confidence", "low_confidence"
        if "structured_safe" in member_states:
            return outcome, "structured_safe", None
    else:
        if "structured_safe" in member_states:
            return outcome, "structured_safe", None
        if "structured_low_confidence" in member_states:
            return outcome, "structured_low_confidence", "low_confidence"
        if "review_required" in member_states:
            return outcome, "review_required", "review_required"
        if "blocked_unsupported" in member_states:
            return outcome, "blocked_unsupported", "blocked_unsupported"

    return outcome, getattr(exemplar, "state", None), getattr(exemplar, "state_reason", None)


def _group_display_item(items: list[Any]):
    exemplar = items[0]
    collapsed_outcome, collapsed_state, collapsed_state_reason = _collapsed_group_state(items)
    evidence = getattr(exemplar, "evidence_payload", None)
    evidence_payload = evidence if isinstance(evidence, dict) else {}
    member_texts = evidence_payload.get("member_criterion_texts")
    if not isinstance(member_texts, list) or not member_texts:
        member_texts = [getattr(item, "criterion_text", "") for item in items if getattr(item, "criterion_text", "")]
    member_categories = evidence_payload.get("member_categories")
    if not isinstance(member_categories, list) or not member_categories:
        member_categories = [getattr(item, "category", None) for item in items if getattr(item, "category", None)]
    category = member_categories[0] if member_categories and len(set(member_categories)) == 1 else "logic_group"
    criterion_text = (
        " OR ".join(dict.fromkeys(member_texts))
        if member_texts
        else getattr(exemplar, "criterion_text", "")
    )
    merged_evidence = {
        **evidence_payload,
        "member_criterion_texts": list(dict.fromkeys(member_texts)),
        "member_categories": list(dict.fromkeys(member_categories)),
        "snapshot_missing_data": any(_has_missing_patient_data(item) for item in items),
    }
    return SimpleNamespace(
        criterion_id=getattr(exemplar, "criterion_id", None),
        pipeline_run_id=getattr(exemplar, "pipeline_run_id", None),
        source_type=getattr(exemplar, "source_type", None),
        source_label=getattr(exemplar, "source_label", None),
        criterion_type=getattr(exemplar, "criterion_type", None),
        category=category,
        criterion_text=criterion_text,
        outcome=collapsed_outcome,
        state=collapsed_state,
        state_reason=collapsed_state_reason,
        explanation_text=getattr(exemplar, "explanation_text", None),
        explanation_type=getattr(exemplar, "explanation_type", None),
        evidence_payload=merged_evidence,
    )


def _effective_items(items: list[Any]) -> list[Any]:
    grouped: dict[tuple[object, str], list[Any]] = {}
    grouped_order: list[tuple[object, str]] = []
    effective: list[Any] = []
    for item in items:
        key = _group_key(item)
        if key is None:
            effective.append(item)
            continue
        if key not in grouped:
            grouped_order.append(key)
            grouped[key] = []
        grouped[key].append(item)
    for key in grouped_order:
        effective.append(_group_display_item(grouped[key]))
    return effective


def _build_entry(item, kind: str) -> dict[str, Any]:
    evidence_payload = getattr(item, "evidence_payload", None)
    return {
        "kind": kind,
        "label": _label_for_category(getattr(item, "category", "logic_group")),
        "category": getattr(item, "category", "logic_group"),
        "criterion_text": getattr(item, "criterion_text", ""),
        "outcome": getattr(item, "outcome", None),
        "state": getattr(item, "state", None),
        "state_reason": getattr(item, "state_reason", None),
        "summary": getattr(item, "explanation_text", None),
        "source_snippet": _source_snippet_for_payload(evidence_payload),
        "evidence_payload": evidence_payload,
    }


def build_gap_report_payload(items: list[Any]) -> dict[str, list[dict[str, Any]]]:
    report = {
        "hard_blockers": [],
        "clarifiable_blockers": [],
        "missing_data": [],
        "review_required": [],
        "unsupported": [],
    }
    for item in _effective_items(items):
        state = getattr(item, "state", None)
        outcome = getattr(item, "outcome", None)
        state_reason = getattr(item, "state_reason", None)

        if state == "blocked_unsupported":
            report["unsupported"].append(_build_entry(item, "unsupported"))
            continue

        if outcome == "unknown" and state_reason == "legacy_state_unverifiable":
            report["review_required"].append(_build_entry(item, "review_required"))
            continue

        if outcome == "requires_review" or (state == "review_required" and outcome != "unknown"):
            report["review_required"].append(_build_entry(item, "review_required"))
            continue

        if outcome == "unknown" and state == "review_required":
            report["review_required"].append(_build_entry(item, "review_required"))
            continue

        if outcome == "unknown" and _has_missing_patient_data(item):
            report["missing_data"].append(_build_entry(item, "missing_data"))
            continue

        if outcome in {"not_matched", "triggered"}:
            if state == "structured_low_confidence" and not _is_hard_blocker(item):
                report["clarifiable_blockers"].append(_build_entry(item, "clarifiable_blocker"))
            elif _is_hard_blocker(item):
                report["hard_blockers"].append(_build_entry(item, "hard_blocker"))
            else:
                report["clarifiable_blockers"].append(_build_entry(item, "clarifiable_blocker"))
            continue

        if outcome == "unknown":
            report["review_required"].append(_build_entry(item, "review_required"))
            continue

        if state == "structured_low_confidence" and outcome in {"matched", "not_triggered"}:
            report["review_required"].append(_build_entry(item, "review_required"))
    return report


def legacy_gap_report_payload(match_result) -> dict[str, list[dict[str, object | None]]]:
    unknown_count = getattr(match_result, "unknown_count", None) or 0
    requires_review_count = getattr(match_result, "requires_review_count", None) or 0
    unfavorable_count = getattr(match_result, "unfavorable_count", None) or 0
    base_entry = {
        "label": "Historical Snapshot",
        "category": "historical_snapshot",
        "criterion_text": "Gap report was not snapshotted for this historical match result.",
        "state": match_result.state,
        "state_reason": match_result.state_reason or "legacy_state_unverifiable",
        "summary": match_result.summary_explanation,
        "source_snippet": None,
        "evidence_payload": None,
    }
    report = {
        "hard_blockers": [],
        "clarifiable_blockers": [],
        "missing_data": [],
        "review_required": [],
        "unsupported": [],
    }
    if match_result.state == "blocked_unsupported":
        report["unsupported"].append({**base_entry, "kind": "unsupported", "outcome": "unknown"})
    if (
        match_result.overall_status == "ineligible"
        and unfavorable_count > 0
        and match_result.state == "structured_safe"
    ):
        report["hard_blockers"].append({**base_entry, "kind": "hard_blocker", "outcome": "not_matched"})
    if (
        unknown_count > 0
        or requires_review_count > 0
        or (match_result.state not in {"structured_safe", "blocked_unsupported"})
    ):
        report["review_required"].append({**base_entry, "kind": "review_required", "outcome": "unknown"})
    return report
