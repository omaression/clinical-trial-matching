import Link from "next/link";

import { PageHeader } from "@/components/page-header";
import { Panel } from "@/components/panel";
import { StatGrid } from "@/components/stat-grid";
import { StatusPill } from "@/components/status-pill";
import { ctmApi } from "@/lib/api/client";
import { formatDate } from "@/lib/format";

export default async function HomePage() {
  const [health, pipeline, review, patients, trials] = await Promise.all([
    ctmApi.getHealth(),
    ctmApi.getPipelineStatus(),
    ctmApi.getReviewQueue("?per_page=5"),
    ctmApi.listPatients("?per_page=5"),
    ctmApi.listTrials("?per_page=5")
  ]);

  return (
    <>
      <PageHeader
        label="Command Surface"
        title="Demonstrate the MVP from one console."
        description="The usable path is now explicit: ingest trials, inspect extraction output, resolve review-required criteria, create a patient, and run deterministic matching with explanations."
        actions={
          <>
            <Link className="rounded-full bg-ink px-5 py-3 text-sm font-semibold text-sand" href="/pipeline">
              Start in pipeline
            </Link>
            <Link className="rounded-full border border-ink/15 px-5 py-3 text-sm font-semibold text-ink" href="/patients">
              Intake patient
            </Link>
          </>
        }
      />

      <StatGrid
        items={[
          { label: "Health", value: health.status, detail: `${health.database} database, ${health.spacy_model} model` },
          { label: "Trials", value: pipeline.total_trials, detail: `${pipeline.review_pending} criteria awaiting review` },
          { label: "Runs", value: pipeline.total_runs, detail: `${pipeline.completed} completed / ${pipeline.failed} failed` },
          { label: "Patients", value: patients.total, detail: "Server-side protected patient registry" }
        ]}
      />

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Panel title="MVP Demo Path" eyebrow="End to end">
          <div className="grid gap-4">
            <div className="rounded-3xl bg-sand/80 p-5">
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">1. Ingest</p>
              <p className="mt-2 text-sm leading-7 text-ink/72">
                Start on the pipeline page and ingest a single NCT ID or a small ClinicalTrials.gov search batch.
              </p>
            </div>
            <div className="rounded-3xl bg-sand/80 p-5">
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">2. Inspect and review</p>
              <p className="mt-2 text-sm leading-7 text-ink/72">
                Open a trial to show source-structured eligibility, canonical extracted criteria, and derived FHIR output. Then resolve anything in the review queue.
              </p>
            </div>
            <div className="rounded-3xl bg-sand/80 p-5">
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">3. Intake a patient</p>
              <p className="mt-2 text-sm leading-7 text-ink/72">
                Create a normalized patient profile with conditions, biomarkers, medications, and one or two labs.
              </p>
            </div>
            <div className="rounded-3xl bg-sand/80 p-5">
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">4. Run matching</p>
              <p className="mt-2 text-sm leading-7 text-ink/72">
                Launch a match run and open the persisted trial-level result with per-criterion explanations and evidence payloads.
              </p>
            </div>
          </div>
        </Panel>

        <Panel title="Pipeline Snapshot" eyebrow="Operations">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-3xl bg-sand/80 p-5">
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Extraction version</p>
              <p className="mt-2 text-2xl font-semibold text-ink">{pipeline.version}</p>
            </div>
            <div className="rounded-3xl bg-sand/80 p-5">
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Pending review</p>
              <p className="mt-2 text-2xl font-semibold text-ink">{pipeline.review_pending}</p>
            </div>
          </div>
        </Panel>

        <Panel title="Recent Trials" eyebrow="Latest">
          {trials.items.length ? (
            <div className="space-y-4">
              {trials.items.map((trial) => (
                <Link
                  key={trial.id}
                  href={`/trials/${trial.id}`}
                  className="flex items-start justify-between gap-4 rounded-3xl border border-ink/8 bg-sand/65 p-4 transition hover:border-tide/30"
                >
                  <div>
                    <p className="text-sm font-semibold text-ink">{trial.brief_title}</p>
                    <p className="mt-1 text-xs uppercase tracking-[0.24em] text-ink/45">{trial.nct_id}</p>
                  </div>
                  <StatusPill value={trial.status} />
                </Link>
              ))}
            </div>
          ) : (
            <div className="rounded-3xl border border-dashed border-ink/12 bg-sand/55 p-5 text-sm leading-7 text-ink/68">
              No trials are ingested yet. Open <Link className="font-semibold text-ink underline decoration-ink/20 underline-offset-4" href="/pipeline">Pipeline</Link> and run a single-NCT ingest or a small search-ingest batch.
            </div>
          )}
        </Panel>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <Panel title="Pending Review" eyebrow="Human-in-the-loop">
          {review.items.length ? (
            <div className="space-y-4">
              {review.items.map((criterion) => (
                <article key={criterion.id} className="rounded-3xl border border-ink/8 bg-white/70 p-4">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <StatusPill value={criterion.review_reason ?? "pending"} />
                    <p className="text-xs uppercase tracking-[0.22em] text-ink/45">{criterion.category}</p>
                  </div>
                  <p className="text-sm leading-6 text-ink">{criterion.original_text}</p>
                </article>
              ))}
            </div>
          ) : (
            <div className="rounded-3xl border border-dashed border-ink/12 bg-sand/55 p-5 text-sm leading-7 text-ink/68">
              Nothing is pending review right now. After ingest, anything ambiguous or uncoded will appear here for accept, correct, or reject actions.
            </div>
          )}
        </Panel>

        <Panel title="Patient Registry" eyebrow="Matching">
          {patients.items.length ? (
            <div className="space-y-4">
              {patients.items.map((patient) => (
                <Link
                  key={patient.id}
                  href={`/patients/${patient.id}`}
                  className="flex items-center justify-between gap-4 rounded-3xl border border-ink/8 bg-white/70 p-4 transition hover:border-ember/25"
                >
                  <div>
                    <p className="text-sm font-semibold text-ink">{patient.external_id ?? patient.id.slice(0, 8)}</p>
                    <p className="mt-1 text-sm text-ink/65">
                      {patient.sex ?? "Unknown sex"} · {patient.birth_date ? formatDate(patient.birth_date) : "No birth date"}
                    </p>
                  </div>
                  <p className="text-xs uppercase tracking-[0.24em] text-ink/45">Open</p>
                </Link>
              ))}
            </div>
          ) : (
            <div className="rounded-3xl border border-dashed border-ink/12 bg-sand/55 p-5 text-sm leading-7 text-ink/68">
              No patient profiles exist yet. Use <Link className="font-semibold text-ink underline decoration-ink/20 underline-offset-4" href="/patients">Patient Intake</Link> to create one, then run a match against the latest ingested trial set.
            </div>
          )}
        </Panel>
      </div>
    </>
  );
}
