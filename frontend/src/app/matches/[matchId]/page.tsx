import { StructuredDataView } from "@/components/structured-data-view";
import Link from "next/link";

import { MatchExplanationCard } from "@/components/match-explanation-card";
import { MatchGapReportCard } from "@/components/match-gap-report-card";
import { PageHeader } from "@/components/page-header";
import { Panel } from "@/components/panel";
import { StatusPill } from "@/components/status-pill";
import { ctmApi } from "@/lib/api/client";
import { formatPercent } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function MatchDetailPage({
  params
}: {
  params: Promise<{ matchId: string }>;
}) {
  const { matchId } = await params;
  const match = await ctmApi.getMatch(matchId);

  return (
    <>
      <PageHeader
        label={match.trial_nct_id}
        title={match.trial_brief_title}
        description={match.summary_explanation ?? "Deterministic patient-trial match result."}
        actions={
          <Link className="rounded-full border border-ink/15 px-5 py-3 text-sm font-semibold text-ink" href={`/patients/${match.patient_id}`}>
            Back to patient
          </Link>
        }
      />

      <Panel title="Match Summary" eyebrow="Trial-level outcome">
        <div className="grid gap-4 md:grid-cols-4">
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Status</p>
            <div className="mt-2"><StatusPill value={match.overall_status} /></div>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Confidence state</p>
            <div className="mt-2"><StatusPill value={match.state} /></div>
            {match.state_reason ? <p className="mt-2 text-sm text-ink/60">{match.state_reason.replaceAll("_", " ")}</p> : null}
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Determinate fit</p>
            <p className="mt-2 text-2xl font-semibold text-ink">{formatPercent(match.determinate_score)}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Coverage</p>
            <p className="mt-2 text-2xl font-semibold text-ink">{formatPercent(match.coverage_ratio)}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Blockers</p>
            <p className="mt-2 text-2xl font-semibold text-ink">{match.unfavorable_count}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Unknown or review</p>
            <p className="mt-2 text-2xl font-semibold text-ink">{match.unresolved_count}</p>
          </div>
        </div>
      </Panel>

      <Panel title="Evidence-Grounded Explanation" eyebrow="Grouped eligibility rationale">
        <p className="text-sm leading-7 text-ink/72">
          These cards summarize why the trial matched, what blocked eligibility, and which criteria still need review.
        </p>
        <div className="mt-6 grid gap-4 xl:grid-cols-3">
          <MatchExplanationCard
            title="Matched criteria"
            eyebrow="Supports fit"
            items={match.explanation.matched}
            emptyMessage="No matched supporting criteria were surfaced for this result."
          />
          <MatchExplanationCard
            title="Blockers"
            eyebrow="Why this may be ineligible"
            items={match.explanation.blockers}
            emptyMessage="No blocking criteria were recorded for this result."
          />
          <MatchExplanationCard
            title="Needs review"
            eyebrow="Unresolved criteria"
            items={match.explanation.review_required}
            emptyMessage="No unresolved or review-required criteria remain for this result."
          />
        </div>
      </Panel>

      <Panel title="Match-Gap Report" eyebrow="Why this result is not yet fully actionable">
        <p className="text-sm leading-7 text-ink/72">
          The gap report separates hard blockers from clarifiable blockers, missing patient data, review-required criteria, and unsupported logic.
        </p>
        <div className="mt-6 grid gap-4 xl:grid-cols-2">
          <MatchGapReportCard
            title="Hard blockers"
            eyebrow="Likely incompatible"
            items={match.gap_report.hard_blockers}
            emptyMessage="No hard blockers were detected for this result."
          />
          <MatchGapReportCard
            title="Clarifiable blockers"
            eyebrow="Could change with better evidence"
            items={match.gap_report.clarifiable_blockers}
            emptyMessage="No clarifiable blockers were detected for this result."
          />
          <MatchGapReportCard
            title="Missing data"
            eyebrow="Need more patient information"
            items={match.gap_report.missing_data}
            emptyMessage="No missing-data gaps were detected for this result."
          />
          <MatchGapReportCard
            title="Review required"
            eyebrow="Needs human confirmation"
            items={match.gap_report.review_required}
            emptyMessage="No review-required gaps remain for this result."
          />
          <MatchGapReportCard
            title="Unsupported"
            eyebrow="Not safely automated"
            items={match.gap_report.unsupported}
            emptyMessage="No unsupported gaps were detected for this result."
          />
        </div>
      </Panel>

      <Panel title="Criterion Breakdown" eyebrow="Raw persisted criterion results">
        <div className="grid gap-4">
          {match.criteria.map((criterion) => (
            <article key={criterion.id} className="rounded-[30px] border border-ink/10 bg-white/75 p-6 shadow-card">
              <div className="mb-4 flex flex-wrap items-center gap-3">
                <StatusPill value={criterion.outcome} />
                <StatusPill value={criterion.state} />
                <span className="text-xs uppercase tracking-[0.24em] text-ink/45">{criterion.category}</span>
                <span className="text-xs uppercase tracking-[0.24em] text-ink/45">{criterion.source_type}</span>
              </div>
              <p className="text-base font-semibold text-ink">{criterion.criterion_text}</p>
              {criterion.state_reason ? (
                <p className="mt-2 text-xs uppercase tracking-[0.18em] text-ink/45">{criterion.state_reason.replaceAll("_", " ")}</p>
              ) : null}
              <p className="mt-3 text-sm leading-7 text-ink/72">{criterion.explanation_text}</p>
              {criterion.evidence_payload ? (
                <details className="mt-4 rounded-2xl bg-sand/65 p-4">
                  <summary className="cursor-pointer text-sm font-semibold text-ink">Structured evidence</summary>
                  <div className="mt-4">
                    <StructuredDataView data={criterion.evidence_payload} emptyLabel="No structured evidence payload is available." />
                  </div>
                </details>
              ) : null}
            </article>
          ))}
        </div>
      </Panel>
    </>
  );
}
