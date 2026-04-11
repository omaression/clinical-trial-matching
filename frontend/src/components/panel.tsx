export function Panel({
  title,
  eyebrow,
  children,
  right
}: {
  title: string;
  eyebrow?: string;
  children: React.ReactNode;
  right?: React.ReactNode;
}) {
  return (
    <section className="rounded-[32px] border border-ink/10 bg-white/75 p-6 shadow-card backdrop-blur">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          {eyebrow ? (
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.28em] text-tide">{eyebrow}</p>
          ) : null}
          <h2 className="text-xl font-semibold text-ink">{title}</h2>
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}
