import Link from "next/link";
import type { Route } from "next";

import { ingestTrialAction, searchIngestAction } from "@/app/actions";
import { PageHeader } from "@/components/page-header";
import { Panel } from "@/components/panel";
import { StatGrid } from "@/components/stat-grid";
import { StatusPill } from "@/components/status-pill";
import { ctmApi } from "@/lib/api/client";
import { formatDate } from "@/lib/format";

export const dynamic = "force-dynamic";

type SearchParams = {
  error?: string;
  nct_id?: string;
  limit?: string;
  batch?: string;
  attempted?: string;
  returned?: string;
  ingested?: string;
  skipped?: string;
  failed?: string;
  total_count?: string;
  has_more?: string;
  condition?: string;
  status?: string;
  phase?: string;
};

export default async function PipelinePage({
  searchParams
}: {
  searchParams?: Promise<SearchParams>;
}) {
  const params = (await searchParams) ?? {};
  const [status, runs, trials] = await Promise.all([
    ctmApi.getPipelineStatus(),
    ctmApi.listPipelineRuns("?per_page=25"),
    ctmApi.listTrials("?per_page=5")
  ]);

  return (
    <>
      <PageHeader
        label="Pipeline"
        title="Ingest, inspect, and advance the trial corpus."
        description="This page is the operational entrypoint for the MVP. Start here to ingest trials from ClinicalTrials.gov, watch extraction runs, and move directly into review and matching."
        actions={
          <>
            <Link className="rounded-full bg-ink px-5 py-3 text-sm font-semibold text-sand" href="/review">
              Open review queue
            </Link>
            <Link className="rounded-full border border-ink/15 px-5 py-3 text-sm font-semibold text-ink" href={"/coverage" as Route}>
              Coverage dashboard
            </Link>
            <Link className="rounded-full border border-ink/15 px-5 py-3 text-sm font-semibold text-ink" href="/trials">
              Browse trials
            </Link>
          </>
        }
      />

      {params.error ? (
        <Panel
          title={params.condition || params.status || params.phase ? "Search Ingest Error" : "Operation Error"}
          eyebrow={params.condition || params.status || params.phase ? "Search request failed" : "Submit failed"}
        >
          <p className="text-sm leading-7 text-ember">{params.error}</p>
        </Panel>
      ) : null}

      {params.batch === "1" ? (
        <Panel title="Latest Search-Ingest Batch" eyebrow="Just completed">
          <div className="grid gap-4 md:grid-cols-5">
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Attempted</p>
              <p className="mt-2 text-2xl font-semibold text-ink">{params.attempted ?? "0"}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Ingested</p>
              <p className="mt-2 text-2xl font-semibold text-ink">{params.ingested ?? "0"}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Skipped</p>
              <p className="mt-2 text-2xl font-semibold text-ink">{params.skipped ?? "0"}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Failed</p>
              <p className="mt-2 text-2xl font-semibold text-ink">{params.failed ?? "0"}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Returned</p>
              <p className="mt-2 text-2xl font-semibold text-ink">{params.returned ?? "0"}</p>
            </div>
          </div>
          <p className="mt-4 text-sm leading-7 text-ink/68">
            Query:
            {" "}
            {[params.condition, params.status, params.phase].filter(Boolean).join(" · ") || "custom batch"}
            {params.total_count ? ` · total available ${params.total_count}` : ""}
            {params.has_more === "1" ? " · more results are available through the API page token flow" : ""}
          </p>
        </Panel>
      ) : null}

      <StatGrid
        items={[
          { label: "Total runs", value: status.total_runs },
          { label: "Completed", value: status.completed },
          { label: "Failed", value: status.failed },
          { label: "Review pending", value: status.review_pending }
        ]}
      />

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <Panel title="Single Trial Ingest" eyebrow="Protected write">
          <form action={ingestTrialAction} className="grid gap-4">
            <input
              className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3"
              defaultValue={params.nct_id ?? ""}
              name="nct_id"
              placeholder="NCT05346328"
              required
            />
            <p className="text-sm leading-7 text-ink/65">
              Use this when you want a deterministic demo path: ingest one known trial, inspect its criteria, then move into review and matching.
            </p>
            <button className="rounded-2xl bg-ink px-5 py-3 font-semibold text-sand" type="submit">
              Ingest trial
            </button>
          </form>
        </Panel>

        <Panel title="Search and Ingest Batch" eyebrow="Protected write">
          <form action={searchIngestAction} className="grid gap-4">
            <div className="grid gap-4 md:grid-cols-2">
              <input
                className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3"
                defaultValue={params.condition}
                name="condition"
                placeholder="non-small cell lung cancer"
              />
              <input
                className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3"
                defaultValue={params.phase}
                name="phase"
                placeholder="PHASE2"
              />
            </div>
            <div className="grid gap-4 md:grid-cols-[1fr_160px]">
              <input
                className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3"
                defaultValue={params.status}
                name="status"
                placeholder="RECRUITING"
              />
              <input
                className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3"
                defaultValue={params.limit ?? "5"}
                max="100"
                min="1"
                name="limit"
                placeholder="5"
                type="number"
              />
            </div>
            <p className="text-sm leading-7 text-ink/65">
              Provide at least one search field. Keep the limit small for demos so the review queue and recent runs stay easy to explain.
            </p>
            <button className="rounded-2xl bg-ink px-5 py-3 font-semibold text-sand" type="submit">
              Search and ingest
            </button>
          </form>
        </Panel>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <Panel title="How to Demonstrate the MVP" eyebrow="Suggested path">
          <div className="grid gap-4 text-sm leading-7 text-ink/72">
            <div className="rounded-3xl bg-sand/70 p-4">
              1. Ingest a single NCT ID or a small batch here.
            </div>
            <div className="rounded-3xl bg-sand/70 p-4">
              2. Open the ingested trial to show source text, latest criteria, and FHIR.
            </div>
            <div className="rounded-3xl bg-sand/70 p-4">
              3. Resolve anything on the review page that needs a human decision.
            </div>
            <div className="rounded-3xl bg-sand/70 p-4">
              4. Create a patient profile and run a match to show deterministic trial scoring and explanations.
            </div>
          </div>
        </Panel>

        <Panel title="Latest Ingested Trials" eyebrow="Quick access">
          {trials.items.length ? (
            <div className="grid gap-4">
              {trials.items.map((trial) => (
                <Link
                  key={trial.id}
                  href={`/trials/${trial.id}`}
                  className="flex items-start justify-between gap-4 rounded-3xl border border-ink/8 bg-sand/55 p-4 transition hover:border-tide/25"
                >
                  <div>
                    <p className="text-sm font-semibold text-ink">{trial.brief_title}</p>
                    <p className="mt-1 text-xs uppercase tracking-[0.22em] text-ink/45">{trial.nct_id}</p>
                  </div>
                  <StatusPill value={trial.extraction_status} />
                </Link>
              ))}
            </div>
          ) : (
            <div className="rounded-3xl border border-dashed border-ink/12 bg-sand/55 p-5 text-sm leading-7 text-ink/68">
              No ingested trials yet. Start with a single NCT ID above if you want the cleanest demo story.
            </div>
          )}
        </Panel>
      </div>

      <Panel title="Recent Runs" eyebrow="Execution history">
        {runs.items.length ? (
          <div className="grid gap-4">
            {runs.items.map((run) => (
              <article key={run.id} className="grid gap-3 rounded-3xl border border-ink/8 bg-sand/55 p-5 lg:grid-cols-[0.6fr_1.4fr_0.8fr]">
                <div>
                  <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Started</p>
                  <p className="mt-2 text-sm text-ink">{formatDate(run.started_at)}</p>
                </div>
                <div>
                  <p className="text-sm font-semibold text-ink">{run.id}</p>
                  <p className="mt-1 text-sm text-ink/68">
                    Version {run.pipeline_version} · criteria {run.criteria_extracted_count ?? 0} · review {run.review_required_count ?? 0}
                  </p>
                  {run.error_message ? <p className="mt-2 text-sm text-ember">{run.error_message}</p> : null}
                </div>
                <div className="flex items-start justify-end">
                  <StatusPill value={run.status} />
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="rounded-3xl border border-dashed border-ink/12 bg-sand/55 p-5 text-sm leading-7 text-ink/68">
            No pipeline runs exist yet. The first ingest will create the initial extraction history and populate this timeline.
          </div>
        )}
      </Panel>
    </>
  );
}
