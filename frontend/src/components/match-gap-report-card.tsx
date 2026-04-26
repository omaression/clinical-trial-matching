import { StatusPill } from "@/components/status-pill";
import type { MatchGapEntry } from "@/lib/api/types";

export function MatchGapReportCard({
  title,
  eyebrow,
  emptyMessage,
  items
}: {
  title: string;
  eyebrow: string;
  emptyMessage: string;
  items: MatchGapEntry[];
}) {
  return (
    <article className="rounded-[30px] border border-ink/10 bg-white/75 p-6 shadow-card">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-tide">{eyebrow}</p>
          <h3 className="mt-2 text-lg font-semibold text-ink">{title}</h3>
        </div>
        <p className="text-sm font-semibold text-ink/55">{items.length}</p>
      </div>

      {items.length === 0 ? (
        <p className="text-sm leading-7 text-ink/65">{emptyMessage}</p>
      ) : (
        <div className="grid gap-4">
          {items.map((item, index) => (
            <div key={`${item.kind}-${item.category}-${index}`} className="rounded-3xl border border-ink/8 bg-sand/55 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <StatusPill value={item.state} />
                <span className="text-xs uppercase tracking-[0.22em] text-ink/45">{item.label}</span>
                <span className="text-xs uppercase tracking-[0.22em] text-ink/35">{item.kind.replaceAll("_", " ")}</span>
              </div>
              <p className="mt-3 text-sm font-semibold text-ink">{item.criterion_text}</p>
              <p className="mt-2 text-sm leading-7 text-ink/72">{item.summary ?? "No additional summary was captured for this gap."}</p>
              <div className="mt-3 rounded-2xl bg-white/70 px-4 py-3">
                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-ink/45">Evidence reference</p>
                <p className="mt-2 text-sm leading-7 text-ink/72">
                  {item.source_snippet ?? "No direct evidence snippet captured for this gap yet."}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}
