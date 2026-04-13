"""Generate a local verification report for the curated eligibility corpus."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.extraction.pipeline import ExtractionPipeline
from app.fhir.criterion_projection import CriterionProjectionMapper
from app.fhir.mapper import FHIRMapper

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "sample_eligibility_texts"
DEFAULT_FIXTURE_NAMES = (
    "therapy_class_and_procedures",
    "medication_exception_logic",
    "nct07084584_cyp3a4_exception",
    "nct03872596_cyp3a4_washout",
    "nct05346328_stage_biomarker",
    "nct05346328_line_of_therapy",
)


def build_curated_corpus_report(fixture_names: list[str] | None = None) -> dict[str, Any]:
    pipeline = ExtractionPipeline()
    mapper = FHIRMapper()
    projection_mapper = CriterionProjectionMapper()
    fixture_names = fixture_names or list(DEFAULT_FIXTURE_NAMES)

    fixtures: list[dict[str, Any]] = []
    summary_categories: Counter[str] = Counter()
    summary_review_reasons: Counter[str] = Counter()
    total_structurally_exportable = 0
    total_medication_statement_projected = 0
    total_blocked_missing_rxnorm = 0
    total_blocked_missing_class_code = 0
    total_review_required_ambiguous_class = 0
    total_review_required = 0
    total_uncoded_accepted = 0
    total_criteria = 0

    for fixture_name in fixture_names:
        text_path = FIXTURES_DIR / f"{fixture_name}.txt"
        text = text_path.read_text()
        result = pipeline.extract(text)
        category_counts = Counter(criterion.category for criterion in result.criteria)
        review_reasons = Counter(
            criterion.review_reason or "unspecified"
            for criterion in result.criteria
            if criterion.review_required
        )
        exportable = mapper._filter_exportable(result.criteria)
        projections = [
            projection
            for criterion in result.criteria
            for projection in projection_mapper.project_criterion(criterion)
        ]
        projection_status_counts = Counter(projection.projection_status for projection in projections)
        projection_resource_counts = Counter(
            projection.resource_type or "none" for projection in projections
        )
        uncoded_accepted = sum(
            1
            for criterion in result.criteria
            if not criterion.review_required and not criterion.coded_concepts
        )

        fixture_report = {
            "fixture": fixture_name,
            "criteria_count": result.criteria_count,
            "review_required_count": result.review_required_count,
            "review_reasons": dict(sorted(review_reasons.items())),
            "structurally_exportable_fhir_count": len(exportable),
            "uncoded_but_accepted_count": uncoded_accepted,
            "medication_statement_projected_count": projection_resource_counts["MedicationStatement"],
            "blocked_missing_rxnorm_count": projection_status_counts["blocked_missing_rxnorm"],
            "blocked_missing_class_code_count": projection_status_counts["blocked_missing_class_code"],
            "review_required_ambiguous_class_count": projection_status_counts["review_required_ambiguous_class"],
            "category_distribution": dict(sorted(category_counts.items())),
            "projection_status_distribution": dict(sorted(projection_status_counts.items())),
        }
        fixtures.append(fixture_report)

        summary_categories.update(category_counts)
        summary_review_reasons.update(review_reasons)
        total_structurally_exportable += len(exportable)
        total_medication_statement_projected += projection_resource_counts["MedicationStatement"]
        total_blocked_missing_rxnorm += projection_status_counts["blocked_missing_rxnorm"]
        total_blocked_missing_class_code += projection_status_counts["blocked_missing_class_code"]
        total_review_required_ambiguous_class += projection_status_counts["review_required_ambiguous_class"]
        total_review_required += result.review_required_count
        total_uncoded_accepted += uncoded_accepted
        total_criteria += result.criteria_count

    return {
        "fixtures": fixtures,
        "summary": {
            "fixture_count": len(fixtures),
            "criteria_count": total_criteria,
            "review_required_count": total_review_required,
            "structurally_exportable_fhir_count": total_structurally_exportable,
            "medication_statement_projected_count": total_medication_statement_projected,
            "blocked_missing_rxnorm_count": total_blocked_missing_rxnorm,
            "blocked_missing_class_code_count": total_blocked_missing_class_code,
            "review_required_ambiguous_class_count": total_review_required_ambiguous_class,
            "uncoded_but_accepted_count": total_uncoded_accepted,
            "category_distribution": dict(sorted(summary_categories.items())),
            "review_reasons": dict(sorted(summary_review_reasons.items())),
        },
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = ["# Curated Corpus Verification", ""]
    summary = report["summary"]
    lines.extend(
        [
            f"- Fixtures: {summary['fixture_count']}",
            f"- Criteria: {summary['criteria_count']}",
            f"- Review required: {summary['review_required_count']}",
            f"- Structurally exportable FHIR criteria: {summary['structurally_exportable_fhir_count']}",
            f"- MedicationStatement projections: {summary['medication_statement_projected_count']}",
            f"- Blocked missing RxNorm: {summary['blocked_missing_rxnorm_count']}",
            f"- Blocked missing class code: {summary['blocked_missing_class_code_count']}",
            f"- Review-required ambiguous classes: {summary['review_required_ambiguous_class_count']}",
            f"- Uncoded but accepted: {summary['uncoded_but_accepted_count']}",
            "",
            "## Fixtures",
        ]
    )

    for fixture in report["fixtures"]:
        lines.extend(
            [
                "",
                f"### {fixture['fixture']}",
                f"- Criteria: {fixture['criteria_count']}",
                f"- Review required: {fixture['review_required_count']}",
                f"- Structurally exportable FHIR criteria: {fixture['structurally_exportable_fhir_count']}",
                f"- MedicationStatement projections: {fixture['medication_statement_projected_count']}",
                f"- Blocked missing RxNorm: {fixture['blocked_missing_rxnorm_count']}",
                f"- Blocked missing class code: {fixture['blocked_missing_class_code_count']}",
                f"- Review-required ambiguous classes: {fixture['review_required_ambiguous_class_count']}",
                f"- Uncoded but accepted: {fixture['uncoded_but_accepted_count']}",
                f"- Categories: {json.dumps(fixture['category_distribution'], sort_keys=True)}",
                f"- Review reasons: {json.dumps(fixture['review_reasons'], sort_keys=True)}",
                f"- Projection statuses: {json.dumps(fixture['projection_status_distribution'], sort_keys=True)}",
            ]
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

    report = build_curated_corpus_report(args.fixtures)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
        return
    print(render_markdown_report(report))


if __name__ == "__main__":
    main()
