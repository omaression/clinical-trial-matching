import Link from "next/link";

import { PageHeader } from "@/components/page-header";
import { Panel } from "@/components/panel";
import { StatusPill } from "@/components/status-pill";
import { ctmApi } from "@/lib/api/client";
import { formatDate } from "@/lib/format";

type SearchParams = {
  page?: string;
  per_page?: string;
  status?: string;
  phase?: string;
  condition?: string;
};

export default async function TrialsPage({
  searchParams
}: {
  searchParams?: Promise<SearchParams>;
}) {
  const params = (await searchParams) ?? {};
  const query = new URLSearchParams();
  if (params.page) query.set("page", params.page);
  if (params.per_page) query.set("per_page", params.per_page);
  if (params.status) query.set("status", params.status);
  if (params.phase) query.set("phase", params.phase);
  if (params.condition) query.set("condition", params.condition);

  const trials = await ctmApi.listTrials(query.size ? `?${query.toString()}` : "");

  return (
    <>
      <PageHeader
        label="Trial Browser"
        title="Browse the current latest-run trial catalog."
        description="Public trial reads stay open, but this console keeps the latest extraction, review burden, and source-structured eligibility in one place."
      />

      <Panel title="Filters" eyebrow="Search">
        <form className="grid gap-4 md:grid-cols-4" action="/trials">
          <input
            className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3"
            defaultValue={params.condition}
            name="condition"
            placeholder="Condition"
          />
          <input
            className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3"
            defaultValue={params.phase}
            name="phase"
            placeholder="Phase"
          />
          <input
            className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3"
            defaultValue={params.status}
            name="status"
            placeholder="Status"
          />
          <button className="rounded-2xl bg-ink px-4 py-3 font-semibold text-sand" type="submit">
            Apply filters
          </button>
        </form>
      </Panel>

      {trials.items.length ? (
        <div className="grid gap-5">
          {trials.items.map((trial) => (
            <Link
              key={trial.id}
              href={`/trials/${trial.id}`}
              className="grid gap-4 rounded-[30px] border border-ink/10 bg-white/75 p-6 shadow-card transition hover:border-tide/30 lg:grid-cols-[1.2fr_0.4fr_0.4fr]"
            >
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-[0.26em] text-ink/45">{trial.nct_id}</p>
                <h2 className="text-xl font-semibold text-ink">{trial.brief_title}</h2>
                <p className="text-sm text-ink/65">Ingested {formatDate(trial.ingested_at)}</p>
              </div>
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Status</p>
                <StatusPill value={trial.status} />
              </div>
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Extraction</p>
                <StatusPill value={trial.extraction_status} />
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <Panel title="No trials available" eyebrow="Empty catalog">
          <p className="text-sm leading-7 text-ink/68">
            This catalog only shows ingested trials. Start from <Link className="font-semibold text-ink underline decoration-ink/20 underline-offset-4" href="/pipeline">Pipeline</Link>, ingest one NCT ID or a small search batch, then return here.
          </p>
        </Panel>
      )}
    </>
  );
}
