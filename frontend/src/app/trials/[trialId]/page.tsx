import { FhirResearchStudyView } from "@/components/fhir-research-study-view";
import { reextractTrialAction } from "@/app/actions";
import { PageHeader } from "@/components/page-header";
import { Panel } from "@/components/panel";
import { StatusPill } from "@/components/status-pill";
import { ctmApi } from "@/lib/api/client";
import { formatDate, titleize } from "@/lib/format";

export default async function TrialDetailPage({
  params
}: {
  params: Promise<{ trialId: string }>;
}) {
  const { trialId } = await params;
  const [trial, criteria, fhir] = await Promise.all([
    ctmApi.getTrial(trialId),
    ctmApi.getTrialCriteria(trialId, "?per_page=50"),
    ctmApi.getTrialFhir(trialId)
  ]);

  return (
    <>
      <PageHeader
        label={trial.nct_id}
        title={trial.brief_title}
        description={trial.official_title ?? "ClinicalTrials.gov source-aligned trial detail."}
        actions={
          <form action={reextractTrialAction}>
            <input name="trial_id" type="hidden" value={trial.id} />
            <button className="rounded-full bg-ember px-5 py-3 text-sm font-semibold text-white" type="submit">
              Re-extract trial
            </button>
          </form>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <Panel title="Trial Summary" eyebrow="ClinicalTrials.gov">
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-ink/45">Status</p>
              <div className="mt-2"><StatusPill value={trial.status} /></div>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-ink/45">Phase</p>
              <p className="mt-2 text-lg font-semibold text-ink">{trial.phase ?? "Unavailable"}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-ink/45">Structured age</p>
              <p className="mt-2 text-sm text-ink/75">
                {trial.eligible_min_age ?? "Any"} to {trial.eligible_max_age ?? "Any"}
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-ink/45">Structured sex</p>
              <p className="mt-2 text-sm text-ink/75">{trial.eligible_sex ?? "ALL"}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-ink/45">Criteria in latest run</p>
              <p className="mt-2 text-sm text-ink/75">{trial.criteria_summary.total}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-ink/45">Pending review</p>
              <p className="mt-2 text-sm text-ink/75">{trial.criteria_summary.review_pending}</p>
            </div>
          </div>
        </Panel>

        <Panel title="Eligibility Narrative" eyebrow="Source text">
          <p className="whitespace-pre-wrap text-sm leading-7 text-ink/80">
            {trial.eligibility_text ?? "No eligibility text stored."}
          </p>
        </Panel>
      </div>

      <Panel title="Latest Criteria" eyebrow="Canonical extraction">
        <div className="grid gap-4">
          {criteria.criteria.map((criterion) => (
            <article key={criterion.id} className="rounded-3xl border border-ink/8 bg-sand/55 p-5">
              <div className="mb-3 flex flex-wrap items-center gap-3">
                <StatusPill value={criterion.type} />
                <StatusPill value={criterion.parse_status} />
                {criterion.review_required ? <StatusPill value={criterion.review_status ?? "pending"} /> : null}
              </div>
              <p className="text-base font-medium text-ink">{criterion.original_text}</p>
              <div className="mt-3 flex flex-wrap gap-5 text-sm text-ink/68">
                <span>{titleize(criterion.category)}</span>
                <span>Confidence {Math.round(criterion.confidence * 100)}%</span>
                <span>Created {formatDate(criterion.created_at)}</span>
              </div>
            </article>
          ))}
        </div>
      </Panel>

      <Panel title="FHIR Preview" eyebrow="Derived export">
        <FhirResearchStudyView resource={fhir} />
      </Panel>
    </>
  );
}
