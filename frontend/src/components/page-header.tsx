export function PageHeader({
  label,
  title,
  description,
  actions
}: {
  label: string;
  title: string;
  description: string;
  actions?: React.ReactNode;
}) {
  return (
    <header className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr] lg:items-end">
      <div className="space-y-4">
        <p className="text-xs font-semibold uppercase tracking-[0.38em] text-tide">{label}</p>
        <div className="space-y-3">
          <h1 className="max-w-4xl text-4xl font-semibold leading-tight text-ink md:text-5xl">{title}</h1>
          <p className="max-w-3xl text-base leading-7 text-ink/72 md:text-lg">{description}</p>
        </div>
      </div>
      {actions ? <div className="flex flex-wrap justify-start gap-3 lg:justify-end">{actions}</div> : null}
    </header>
  );
}
