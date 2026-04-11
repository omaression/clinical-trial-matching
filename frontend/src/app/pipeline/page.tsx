import { PageHeader } from "@/components/page-header";
import { Panel } from "@/components/panel";
import { StatGrid } from "@/components/stat-grid";
import { StatusPill } from "@/components/status-pill";
import { ctmApi } from "@/lib/api/client";
import { formatDate } from "@/lib/format";

export default async function PipelinePage() {
  const [status, runs] = await Promise.all([
    ctmApi.getPipelineStatus(),
    ctmApi.listPipelineRuns("?per_page=25")
  ]);

  return (
    <>
      <PageHeader
        label="Pipeline"
        title="Watch extraction throughput and review load."
        description="Operational pages stay server-side and authenticated. This surface shows the same backend state the ingestion and review routes persist."
      />

      <StatGrid
        items={[
          { label: "Total runs", value: status.total_runs },
          { label: "Completed", value: status.completed },
          { label: "Failed", value: status.failed },
          { label: "Review pending", value: status.review_pending }
        ]}
      />

      <Panel title="Recent Runs" eyebrow="Execution history">
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
      </Panel>
    </>
  );
}
