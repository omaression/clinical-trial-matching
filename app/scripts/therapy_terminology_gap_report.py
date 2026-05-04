"""Generate a deterministic report of unresolved therapy-class terminology gaps."""

from __future__ import annotations

import argparse
import json
import warnings
from collections import Counter
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore", category=SyntaxWarning, module=r"pysbd(\.|$)")

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "sample_eligibility_texts"
DEFAULT_FIXTURE_NAMES = (
    "concomitant_cns",
    "medication_exception_logic",
    "mixed_polarity",
    "nct03872596_cyp3a4_washout",
    "nct07084584_cyp3a4_exception",
    "therapy_class_and_procedures",
)
_UNRESOLVED_CLASS_PROJECTION_STATUSES = frozenset(
    {
        "blocked_missing_class_code",
        "review_required_ambiguous_class",
    }
)


def build_therapy_terminology_gap_report(fixture_names: list[str] | None = None) -> dict[str, Any]:
    from app.extraction.pipeline import ExtractionPipeline
    from app.fhir.criterion_projection import CriterionProjectionMapper

    pipeline = ExtractionPipeline()
    projection_mapper = CriterionProjectionMapper()
    selected_fixtures = list(fixture_names or DEFAULT_FIXTURE_NAMES)

    gaps_by_key: dict[tuple[str, str], dict[str, Any]] = {}

    for fixture_name in selected_fixtures:
        text = (FIXTURES_DIR / f"{fixture_name}.txt").read_text()
        result = pipeline.extract(text)

        for criterion in result.criteria:
            for projection in projection_mapper.project_criterion(criterion):
                if projection.projection_status not in _UNRESOLVED_CLASS_PROJECTION_STATUSES:
                    continue

                key = (projection.projection_status, projection.normalized_term)
                gap = gaps_by_key.setdefault(
                    key,
                    {
                        "projection_status": projection.projection_status,
                        "terminology_status": projection.terminology_status,
                        "normalized_term": projection.normalized_term,
                        "occurrence_count": 0,
                        "fixtures": set(),
                        "criterion_categories": Counter(),
                        "criterion_types": Counter(),
                        "examples": set(),
                    },
                )
                gap["occurrence_count"] += 1
                gap["fixtures"].add(fixture_name)
                gap["criterion_categories"][criterion.category] += 1
                gap["criterion_types"][criterion.type] += 1
                gap["examples"].add(
                    (
                        fixture_name,
                        criterion.type,
                        criterion.category,
                        projection.mention_text,
                        criterion.original_text,
                    )
                )

    gaps = []
    summary_status_counts: Counter[str] = Counter()
    summary_category_counts: Counter[str] = Counter()
    total_occurrences = 0

    for key in sorted(gaps_by_key):
        gap = gaps_by_key[key]
        summary_status_counts[gap["projection_status"]] += gap["occurrence_count"]
        summary_category_counts.update(gap["criterion_categories"])
        total_occurrences += gap["occurrence_count"]

        example_rows = [
            {
                "fixture": fixture_name,
                "criterion_type": criterion_type,
                "criterion_category": criterion_category,
                "mention_text": mention_text,
                "criterion_text": criterion_text,
            }
            for fixture_name, criterion_type, criterion_category, mention_text, criterion_text in sorted(
                gap["examples"]
            )[:3]
        ]
        gaps.append(
            {
                "projection_status": gap["projection_status"],
                "terminology_status": gap["terminology_status"],
                "normalized_term": gap["normalized_term"],
                "occurrence_count": gap["occurrence_count"],
                "fixture_count": len(gap["fixtures"]),
                "fixtures": sorted(gap["fixtures"]),
                "criterion_categories": dict(sorted(gap["criterion_categories"].items())),
                "criterion_types": dict(sorted(gap["criterion_types"].items())),
                "representative_examples": example_rows,
            }
        )

    return {
        "metadata": {
            "fixture_names": selected_fixtures,
        },
        "summary": {
            "fixture_count": len(selected_fixtures),
            "gap_count": len(gaps),
            "occurrence_count": total_occurrences,
            "breakdown_by_status": dict(sorted(summary_status_counts.items())),
            "breakdown_by_category": dict(sorted(summary_category_counts.items())),
        },
        "gaps": gaps,
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Therapy Terminology Gaps",
        "",
        f"- Fixtures: {summary['fixture_count']}",
        f"- Gaps: {summary['gap_count']}",
        f"- Occurrences: {summary['occurrence_count']}",
        f"- Breakdown by status: {json.dumps(summary['breakdown_by_status'], sort_keys=True)}",
        f"- Breakdown by category: {json.dumps(summary['breakdown_by_category'], sort_keys=True)}",
    ]

    for gap in report["gaps"]:
        lines.extend(
            [
                "",
                f"## {gap['normalized_term']}",
                f"- Status: {gap['projection_status']}",
                f"- Terminology status: {gap['terminology_status']}",
                f"- Occurrences: {gap['occurrence_count']}",
                f"- Fixtures: {json.dumps(gap['fixtures'])}",
                f"- Categories: {json.dumps(gap['criterion_categories'], sort_keys=True)}",
                f"- Types: {json.dumps(gap['criterion_types'], sort_keys=True)}",
                "- Representative examples:",
            ]
        )
        for example in gap["representative_examples"]:
            lines.append(
                "  - "
                f"{example['fixture']} [{example['criterion_type']}/{example['criterion_category']}] "
                f"mention={json.dumps(example['mention_text'])} text={json.dumps(example['criterion_text'])}"
            )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format.",
    )
    parser.add_argument(
        "--fixture",
        action="append",
        dest="fixtures",
        help="Specific fixture name to include. Repeatable.",
    )
    args = parser.parse_args()

    report = build_therapy_terminology_gap_report(args.fixtures)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
        return
    print(render_markdown_report(report))


if __name__ == "__main__":
    main()
