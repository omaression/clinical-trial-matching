import { reviewCriterionAction } from "@/app/actions";
import { PageHeader } from "@/components/page-header";
import { Panel } from "@/components/panel";
import { StatusPill } from "@/components/status-pill";
import { ctmApi } from "@/lib/api/client";
import Link from "next/link";

export const dynamic = "force-dynamic";

const MATCH_BUCKET_LABELS = {
  review_required: "Needs match review",
  missing_data: "Needs patient data",
  clarifiable_blockers: "Clarifiable blocker",
  unsupported: "System limitation"
} as const;

type SearchParams = {
  reason?: string;
  page?: string;
  match_page?: string;
};

export default async function ReviewPage({
  searchParams
}: {
  searchParams?: Promise<SearchParams>;
}) {
  const params = (await searchParams) ?? {};
  const query = new URLSearchParams();
  if (params.reason) query.set("reason", params.reason);
  if (params.page) query.set("page", params.page);
  query.set("per_page", "20");
  const queue = await ctmApi.getReviewQueue(`?${query.toString()}`);
  const showMatchPanel = !params.reason;
  const matchQuery = new URLSearchParams();
  if (params.match_page) matchQuery.set("page", params.match_page);
  matchQuery.set("per_page", "20");
  const matchQueue = showMatchPanel ? await ctmApi.getMatchReviewQueue(`?${matchQuery.toString()}`) : null;
  const matchPage = Number(params.match_page ?? "1");
  const hasPreviousMatchPage = matchPage > 1;
  const hasNextMatchPage = matchQueue ? matchPage * matchQueue.per_page < matchQueue.total : false;

  return (
    <>
      <PageHeader
        label="Review Queue"
        title="Resolve extraction uncertainty and inspect downstream match ambiguity."
        description="The primary queue remains actionable extracted criteria from the latest completed run. A separate panel surfaces latest match-side unresolved criteria so operators can inspect affected patient-trial results without conflating them with the canonical adjudication workflow."
      />

      <Panel title="Breakdown" eyebrow="Reasons">
        <div className="flex flex-wrap gap-3">
          {Object.entries(queue.breakdown_by_reason).map(([reason, count]) => (
            <a
              key={reason}
              href={`/review?reason=${encodeURIComponent(reason)}`}
              className="rounded-full border border-ink/10 bg-sand/70 px-4 py-2 text-sm font-medium text-ink"
            >
              {reason} · {count}
            </a>
          ))}
        </div>
      </Panel>

      <div className="grid gap-5">
        {queue.items.length ? (
          queue.items.map((criterion) => (
            <Panel
              key={criterion.id}
              title={criterion.original_text}
              eyebrow={`${criterion.category} · ${criterion.review_reason ?? "pending"}`}
              right={<StatusPill value={criterion.review_status ?? "pending"} />}
            >
              <form action={reviewCriterionAction} className="grid gap-4 lg:grid-cols-[0.55fr_0.55fr_1fr_1fr_auto]">
                <input name="criterion_id" type="hidden" value={criterion.id} />
                <input
                  className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3"
                  defaultValue="ops-console"
                  name="reviewed_by"
                  placeholder="Reviewed by"
                  required
                />
                <select
                  className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3"
                  defaultValue="accept"
                  name="action"
                >
                  <option value="accept">Accept</option>
                  <option value="reject">Reject</option>
                  <option value="correct">Correct</option>
                </select>
                <textarea
                  className="min-h-24 rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3"
                  defaultValue=""
                  name="review_notes"
                  placeholder="Optional review notes"
                />
                <textarea
                  className="min-h-24 rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3"
                  defaultValue=""
                  name="corrected_data"
                  placeholder='Optional corrected_data JSON for "correct" action'
                />
                <button className="rounded-2xl bg-ink px-5 py-3 font-semibold text-sand" type="submit">
                  Submit
                </button>
              </form>
            </Panel>
          ))
        ) : (
          <Panel title="Nothing needs review" eyebrow="Queue clear">
            <p className="text-sm leading-7 text-ink/68">
              The current latest-run criteria set is fully accepted or unambiguous. If you want to demonstrate the review workflow, ingest another trial from
              {" "}
              <Link className="font-semibold text-ink underline decoration-ink/20 underline-offset-4" href="/pipeline">
                Pipeline
              </Link>
              {" "}
              and return here.
            </p>
          </Panel>
        )}

        <Panel
          title="Affected match-side follow-up items"
          eyebrow={showMatchPanel && matchQueue ? `Read-only downstream context · ${matchQueue.total} total items` : "Read-only downstream context"}
          right={
            showMatchPanel && matchQueue && matchQueue.total > matchQueue.per_page ? (
              <div className="flex items-center gap-3 text-sm">
                {hasPreviousMatchPage ? (
                  <Link
                    className="font-semibold text-ink underline decoration-ink/20 underline-offset-4"
                    href={`/review?${new URLSearchParams({
                      ...(params.page ? { page: params.page } : {}),
                      match_page: String(matchPage - 1)
                    }).toString()}`}
                  >
                    Previous match page
                  </Link>
                ) : null}
                {hasNextMatchPage ? (
                  <Link
                    className="font-semibold text-ink underline decoration-ink/20 underline-offset-4"
                    href={`/review?${new URLSearchParams({
                      ...(params.page ? { page: params.page } : {}),
                      match_page: String(matchPage + 1)
                    }).toString()}`}
                  >
                    Next match page
                  </Link>
                ) : null}
              </div>
            ) : null
          }
        >
          {!showMatchPanel ? (
            <p className="text-sm leading-7 text-ink/68">
              Match-side follow-up context is hidden while an extraction review-reason filter is active because the match queue uses a different reason vocabulary.
              Clear the extraction reason filter to inspect downstream match follow-up items.
            </p>
          ) : matchQueue && matchQueue.items.length ? (
            <div className="grid gap-4">
              {matchQueue.items.map((item) => (
                <article key={item.id} className="rounded-[28px] border border-ink/10 bg-white/75 p-5 shadow-card">
                  <div className="mb-3 flex flex-wrap items-center gap-3">
                    <StatusPill value={item.state} />
                    <span className="text-xs uppercase tracking-[0.22em] text-ink/45">{MATCH_BUCKET_LABELS[item.bucket]}</span>
                    <span className="text-xs uppercase tracking-[0.22em] text-ink/45">{item.category}</span>
                    {(item.reason_codes.length ? item.reason_codes : item.reason_code ? [item.reason_code] : ["pending"]).map((reason) => (
                      <span key={`${item.id}-${reason}`} className="text-xs uppercase tracking-[0.22em] text-ink/45">
                        {reason}
                      </span>
                    ))}
                  </div>
                  <p className="text-base font-semibold text-ink">{item.original_text}</p>
                  <div className="mt-3 grid gap-2 text-sm text-ink/70 lg:grid-cols-2">
                    <p>
                      <span className="font-semibold text-ink">Trial:</span> {item.trial_nct_id} · {item.trial_brief_title}
                    </p>
                    <p>
                      <span className="font-semibold text-ink">Patient:</span> {item.patient_id}
                    </p>
                    {item.source_snippet ? (
                      <p className="lg:col-span-2">
                        <span className="font-semibold text-ink">Source snippet:</span> {item.source_snippet}
                      </p>
                    ) : null}
                  </div>
                  <div className="mt-4 flex flex-wrap gap-3">
                    <Link
                      className="inline-flex font-semibold text-ink underline decoration-ink/20 underline-offset-4"
                      href={`/matches/${item.match_result_id}`}
                    >
                      Open match detail
                    </Link>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <p className="text-sm leading-7 text-ink/68">
              No latest match results currently expose unresolved match-side criteria.
            </p>
          )}
        </Panel>
      </div>
    </>
  );
}
