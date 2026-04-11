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
        title="Run the platform from one place."
        description="This frontend stays server-side for protected operations and exposes the current ingestion, review, and matching state without leaking backend credentials to the browser."
        actions={
          <>
            <Link className="rounded-full bg-ink px-5 py-3 text-sm font-semibold text-sand" href="/patients">
              Intake patient
            </Link>
            <Link className="rounded-full border border-ink/15 px-5 py-3 text-sm font-semibold text-ink" href="/review">
              Review queue
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
        </Panel>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <Panel title="Pending Review" eyebrow="Human-in-the-loop">
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
        </Panel>

        <Panel title="Patient Registry" eyebrow="Matching">
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
        </Panel>
      </div>
    </>
  );
}
