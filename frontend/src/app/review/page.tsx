import { reviewCriterionAction } from "@/app/actions";
import { PageHeader } from "@/components/page-header";
import { Panel } from "@/components/panel";
import { StatusPill } from "@/components/status-pill";
import { ctmApi } from "@/lib/api/client";

type SearchParams = {
  reason?: string;
  page?: string;
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

  return (
    <>
      <PageHeader
        label="Review Queue"
        title="Resolve machine uncertainty without leaving the console."
        description="Each row is the latest pending criterion from the latest completed run. Accept, reject, or correct against the canonical row."
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
        {queue.items.map((criterion) => (
          <Panel
            key={criterion.id}
            title={criterion.original_text}
            eyebrow={`${criterion.category} · ${criterion.review_reason ?? "pending"}`}
            right={<StatusPill value={criterion.review_status ?? "pending"} />}
          >
            <form action={reviewCriterionAction} className="grid gap-4 lg:grid-cols-[0.6fr_0.6fr_1.2fr_auto]">
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
                name="corrected_data"
                placeholder='Optional corrected_data JSON for "correct" action'
              />
              <button className="rounded-2xl bg-ink px-5 py-3 font-semibold text-sand" type="submit">
                Submit
              </button>
            </form>
          </Panel>
        ))}
      </div>
    </>
  );
}
