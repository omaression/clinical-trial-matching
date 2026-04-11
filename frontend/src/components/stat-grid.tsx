export function StatGrid({
  items
}: {
  items: Array<{ label: string; value: string | number; detail?: string }>;
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <article
          key={item.label}
          className="rounded-[26px] border border-ink/10 bg-white/70 p-5 shadow-card backdrop-blur"
        >
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-ink/45">{item.label}</p>
          <p className="mt-3 text-3xl font-semibold text-ink">{item.value}</p>
          {item.detail ? <p className="mt-2 text-sm text-ink/62">{item.detail}</p> : null}
        </article>
      ))}
    </div>
  );
}
