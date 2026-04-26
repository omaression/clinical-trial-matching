import Link from "next/link";

import { PageHeader } from "@/components/page-header";
import { Panel } from "@/components/panel";
import { StatGrid } from "@/components/stat-grid";
import { ctmApi } from "@/lib/api/client";

export const dynamic = "force-dynamic";

function renderBreakdownEntries(breakdown: Record<string, number>) {
  const entries = Object.entries(breakdown);
  if (!entries.length) {
    return <p className="text-sm leading-7 text-ink/68">No items in this bucket yet.</p>;
  }

  return (
    <div className="space-y-3">
      {entries.map(([label, value]) => (
        <div key={label} className="flex items-center justify-between gap-4 rounded-3xl bg-sand/70 px-4 py-3">
          <p className="text-sm text-ink/72">{label.replaceAll("_", " ")}</p>
          <p className="text-sm font-semibold text-ink">{value}</p>
        </div>
      ))}
    </div>
  );
}

export default async function CoveragePage() {
  const coverage = await ctmApi.getPipelineCoverage();

  return (
    <>
      <PageHeader
        label="Coverage Dashboard"
        title="Track extraction and matching coverage without hiding uncertainty."
        description="This is an internal evaluation lens: it shows where the system is confidently structured, where review load remains high, and where persisted match-gap reporting is already available."
        actions={
          <>
            <Link className="rounded-full bg-ink px-5 py-3 text-sm font-semibold text-sand" href="/pipeline">
              Back to pipeline
            </Link>
            <Link className="rounded-full border border-ink/15 px-5 py-3 text-sm font-semibold text-ink" href="/review">
              Open review queue
            </Link>
          </>
        }
      />

      <StatGrid
        items={[
          {
            label: "Latest-run criteria",
            value: coverage.extraction_overview.latest_run_criteria_count,
            detail: `${coverage.extraction_overview.latest_run_trial_count} trials in current extraction snapshot`
          },
          {
            label: "Review pending",
            value: coverage.extraction_overview.review_pending_count,
            detail: `${coverage.extraction_overview.review_required_count} review-required criteria overall`
          },
          {
            label: "Persisted gap reports",
            value: coverage.matching_overview.persisted_gap_report_count,
            detail: `${coverage.matching_overview.legacy_match_count} historical match results still conservative`
          },
          {
            label: "Curated fixtures",
            value: coverage.curated_corpus_summary.fixture_count,
            detail: `${coverage.curated_corpus_summary.criteria_count} representative criteria across the fixture set`
          }
        ]}
      />

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Extraction confidence snapshot" eyebrow="Current latest-run state">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-3xl bg-sand/70 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Structured safe</p>
              <p className="mt-2 text-2xl font-semibold text-ink">{coverage.extraction_overview.structured_safe_count}</p>
            </div>
            <div className="rounded-3xl bg-sand/70 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Low confidence</p>
              <p className="mt-2 text-2xl font-semibold text-ink">{coverage.extraction_overview.structured_low_confidence_count}</p>
            </div>
            <div className="rounded-3xl bg-sand/70 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Review required</p>
              <p className="mt-2 text-2xl font-semibold text-ink">{coverage.extraction_overview.review_required_count}</p>
            </div>
            <div className="rounded-3xl bg-sand/70 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Unsupported</p>
              <p className="mt-2 text-2xl font-semibold text-ink">{coverage.extraction_overview.blocked_unsupported_count}</p>
            </div>
          </div>
        </Panel>

        <Panel title="Match coverage snapshot" eyebrow="Persisted gap-report availability">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-3xl bg-sand/70 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Eligible / possible / ineligible</p>
              <p className="mt-2 text-lg font-semibold text-ink">
                {coverage.matching_overview.status_breakdown.eligible ?? 0} / {coverage.matching_overview.status_breakdown.possible ?? 0} / {coverage.matching_overview.status_breakdown.ineligible ?? 0}
              </p>
            </div>
            <div className="rounded-3xl bg-sand/70 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Total match results</p>
              <p className="mt-2 text-2xl font-semibold text-ink">{coverage.matching_overview.total_match_results}</p>
            </div>
            <div className="rounded-3xl bg-sand/70 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Missing-data gaps</p>
              <p className="mt-2 text-2xl font-semibold text-ink">{coverage.matching_overview.gap_bucket_counts.missing_data}</p>
            </div>
            <div className="rounded-3xl bg-sand/70 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Review-required gaps</p>
              <p className="mt-2 text-2xl font-semibold text-ink">{coverage.matching_overview.gap_bucket_counts.review_required}</p>
            </div>
          </div>
        </Panel>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <Panel title="Review reason pressure" eyebrow="Why humans are still needed">{renderBreakdownEntries(coverage.review_reason_breakdown)}</Panel>
        <Panel title="Blocked criteria pressure" eyebrow="Where extraction still exits the safe lane">
          {renderBreakdownEntries(coverage.blocked_criteria_breakdown)}
        </Panel>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <Panel title="Curated corpus summary" eyebrow="Regression-friendly fixture slice">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-3xl bg-sand/70 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Criteria</p>
              <p className="mt-2 text-2xl font-semibold text-ink">{coverage.curated_corpus_summary.criteria_count}</p>
            </div>
            <div className="rounded-3xl bg-sand/70 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Review required</p>
              <p className="mt-2 text-2xl font-semibold text-ink">{coverage.curated_corpus_summary.review_required_count}</p>
            </div>
            <div className="rounded-3xl bg-sand/70 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">FHIR exportable</p>
              <p className="mt-2 text-2xl font-semibold text-ink">{coverage.curated_corpus_summary.structurally_exportable_fhir_count}</p>
            </div>
            <div className="rounded-3xl bg-sand/70 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Medication projections</p>
              <p className="mt-2 text-2xl font-semibold text-ink">{coverage.curated_corpus_summary.medication_statement_projected_count}</p>
            </div>
          </div>
          <p className="mt-4 text-sm leading-7 text-ink/68">
            The curated fixture set is useful for showing directional improvement over time, but it is still a representative internal corpus rather than a public benchmark.
          </p>
        </Panel>

        <Panel title="Coverage interpretation guardrails" eyebrow="Read this before overclaiming">
          <div className="space-y-3">
            <div className="rounded-3xl bg-sand/70 p-4 text-sm leading-7 text-ink/72">
              Curated corpus source: {coverage.curated_corpus_metadata.source}
              {coverage.curated_corpus_metadata.generated_at
                ? ` · generated ${coverage.curated_corpus_metadata.generated_at}`
                : " · snapshot unavailable in this runtime"}
            </div>
            {coverage.notes.map((note) => (
              <div key={note} className="rounded-3xl bg-sand/70 p-4 text-sm leading-7 text-ink/72">
                {note}
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <Panel title="Fixture-level detail" eyebrow="What the representative corpus currently looks like">
        <div className="grid gap-4 lg:grid-cols-2">
          {coverage.curated_corpus_fixtures.map((fixture) => (
            <article key={fixture.fixture} className="rounded-3xl border border-ink/8 bg-sand/55 p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold text-ink">{fixture.fixture.replaceAll("_", " ")}</p>
                  <p className="mt-1 text-xs uppercase tracking-[0.22em] text-ink/45">
                    {fixture.criteria_count} criteria · {fixture.review_required_count} review-required
                  </p>
                </div>
                <p className="text-sm font-semibold text-ink">{fixture.medication_statement_projected_count} projected</p>
              </div>
              <p className="mt-4 text-sm leading-7 text-ink/68">
                Missing class-code blockers: {fixture.blocked_missing_class_code_count} · ambiguous classes: {fixture.review_required_ambiguous_class_count}
              </p>
            </article>
          ))}
        </div>
      </Panel>
    </>
  );
}
