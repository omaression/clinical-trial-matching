import { StructuredDataView } from "@/components/structured-data-view";
import Link from "next/link";

import { PageHeader } from "@/components/page-header";
import { Panel } from "@/components/panel";
import { StatusPill } from "@/components/status-pill";
import { ctmApi } from "@/lib/api/client";
import { formatPercent } from "@/lib/format";

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
            <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Score</p>
            <p className="mt-2 text-2xl font-semibold text-ink">{formatPercent(match.score)}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Blockers</p>
            <p className="mt-2 text-2xl font-semibold text-ink">{match.unfavorable_count}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Unknown or review</p>
            <p className="mt-2 text-2xl font-semibold text-ink">{match.unknown_count + match.requires_review_count}</p>
          </div>
        </div>
      </Panel>

      <div className="grid gap-4">
        {match.criteria.map((criterion) => (
          <article key={criterion.id} className="rounded-[30px] border border-ink/10 bg-white/75 p-6 shadow-card">
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <StatusPill value={criterion.outcome} />
              <span className="text-xs uppercase tracking-[0.24em] text-ink/45">{criterion.category}</span>
              <span className="text-xs uppercase tracking-[0.24em] text-ink/45">{criterion.source_type}</span>
            </div>
            <p className="text-base font-semibold text-ink">{criterion.criterion_text}</p>
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
    </>
  );
}
