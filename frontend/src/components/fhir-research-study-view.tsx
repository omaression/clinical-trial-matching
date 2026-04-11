import { StructuredDataView } from "@/components/structured-data-view";

type FhirCoding = {
  system?: string;
  code?: string;
  display?: string;
};

type FhirExtension = {
  url?: string;
  valueString?: string;
  valueDecimal?: number;
  valueCoding?: FhirCoding;
  extension?: FhirExtension[];
};

type FhirResearchStudy = {
  resourceType?: string;
  identifier?: Array<{ system?: string; value?: string }>;
  title?: string;
  status?: string;
  phase?: { coding?: FhirCoding[] };
  condition?: Array<{ text?: string }>;
  enrollment?: Array<Record<string, unknown>>;
  extension?: FhirExtension[];
};

type EligibilityCriterionView = {
  category?: string;
  text: string;
  codings: string[];
  metadata: Record<string, unknown>;
};

type EligibilityGroupView = {
  label: string;
  criteria: EligibilityCriterionView[];
};

function formatCoding(coding: FhirCoding): string {
  const label = coding.display || coding.code || "Unnamed coding";
  return coding.system ? `${label} (${coding.system})` : label;
}

function extensionValue(field: FhirExtension): unknown {
  if (field.valueCoding) {
    return formatCoding(field.valueCoding);
  }
  if (field.valueString !== undefined) {
    return field.valueString;
  }
  if (field.valueDecimal !== undefined) {
    return field.valueDecimal;
  }
  return undefined;
}

function groupLabel(url?: string): string {
  const tail = url?.split("/").pop();
  if (tail === "inclusion") {
    return "Inclusion criteria";
  }
  if (tail === "exclusion") {
    return "Exclusion criteria";
  }
  return "Eligibility criteria";
}

function eligibilityGroups(resource: FhirResearchStudy): EligibilityGroupView[] {
  return (resource.extension ?? [])
    .filter((group) => group.extension?.length)
    .map((group) => ({
      label: groupLabel(group.url),
      criteria: (group.extension ?? []).map((criterion) => {
        const metadata: Record<string, unknown> = {};
        const codings: string[] = [];
        let text = "Criterion";
        let category: string | undefined;

        for (const field of criterion.extension ?? []) {
          if (!field.url) {
            continue;
          }
          const value = extensionValue(field);
          if (field.url === "text" && typeof value === "string" && value) {
            text = value;
            continue;
          }
          if (field.url === "category" && typeof value === "string" && value) {
            category = value;
            continue;
          }
          if (field.url === "coding" && typeof value === "string") {
            codings.push(value);
            continue;
          }
          if (value !== undefined) {
            metadata[field.url] = value;
          }
        }

        if (codings.length) {
          metadata.codings = codings;
        }

        return { category, text, codings, metadata };
      })
    }));
}

export function FhirResearchStudyView({ resource }: { resource: Record<string, unknown> }) {
  const study = resource as FhirResearchStudy;
  const groups = eligibilityGroups(study);

  return (
    <div className="grid gap-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-3xl bg-ink px-5 py-5 text-sand">
          <p className="text-xs uppercase tracking-[0.22em] text-sand/55">Resource Type</p>
          <p className="mt-2 text-2xl font-semibold">{study.resourceType ?? "ResearchStudy"}</p>
        </div>
        <div className="rounded-3xl bg-sand/75 p-5">
          <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Identifier</p>
          <p className="mt-2 text-lg font-semibold text-ink">{study.identifier?.[0]?.value ?? "Unavailable"}</p>
        </div>
        <div className="rounded-3xl bg-sand/75 p-5">
          <p className="text-xs uppercase tracking-[0.22em] text-ink/45">FHIR Status</p>
          <p className="mt-2 text-lg font-semibold text-ink">{study.status ?? "Unavailable"}</p>
        </div>
        <div className="rounded-3xl bg-sand/75 p-5">
          <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Phase</p>
          <p className="mt-2 text-lg font-semibold text-ink">{study.phase?.coding?.[0]?.display ?? "Unavailable"}</p>
        </div>
      </div>

      <section className="rounded-[30px] border border-ink/8 bg-white/75 p-6 shadow-card">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-tide">Research Study Summary</p>
        <h3 className="mt-3 text-2xl font-semibold text-ink">{study.title ?? "Untitled ResearchStudy"}</h3>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <div className="rounded-2xl border border-ink/8 bg-sand/50 p-4">
            <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Condition</p>
            {(study.condition ?? []).length ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {(study.condition ?? []).map((condition, index) => (
                  <span
                    key={`${condition.text ?? "condition"}-${index}`}
                    className="rounded-full bg-white px-3 py-1 text-sm text-ink/75"
                  >
                    {condition.text ?? "Unnamed condition"}
                  </span>
                ))}
              </div>
            ) : (
              <p className="mt-3 text-sm leading-7 text-ink/68">No condition codings were exported for this study.</p>
            )}
          </div>
          <div className="rounded-2xl border border-ink/8 bg-sand/50 p-4">
            <p className="text-xs uppercase tracking-[0.22em] text-ink/45">Enrollment Constraint</p>
            <div className="mt-3 text-sm leading-7 text-ink/72">
              <StructuredDataView
                data={study.enrollment?.[0] ?? null}
                emptyLabel="No structured enrollment constraints were exported."
              />
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-[30px] border border-ink/8 bg-white/75 p-6 shadow-card">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-tide">Eligibility Extensions</p>
            <h3 className="mt-2 text-2xl font-semibold text-ink">FHIR-ready criterion export</h3>
          </div>
          <p className="text-sm text-ink/60">{groups.reduce((count, group) => count + group.criteria.length, 0)} criteria exported</p>
        </div>
        {groups.length ? (
          <div className="mt-5 grid gap-5">
            {groups.map((group) => (
              <div key={group.label} className="rounded-3xl border border-ink/8 bg-sand/50 p-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h4 className="text-sm font-semibold uppercase tracking-[0.22em] text-ink/55">{group.label}</h4>
                  <span className="rounded-full bg-white px-3 py-1 text-xs uppercase tracking-[0.18em] text-ink/55">
                    {group.criteria.length} items
                  </span>
                </div>
                <div className="mt-4 grid gap-4">
                  {group.criteria.map((criterion, index) => (
                    <article key={`${group.label}-${index}`} className="rounded-2xl border border-ink/8 bg-white/70 p-4">
                      <div className="flex flex-wrap items-center gap-3">
                        {criterion.category ? (
                          <span className="rounded-full bg-sand px-3 py-1 text-xs uppercase tracking-[0.18em] text-ink/60">
                            {criterion.category}
                          </span>
                        ) : null}
                        {criterion.codings.length ? (
                          <span className="text-xs uppercase tracking-[0.18em] text-ink/45">
                            {criterion.codings.length} coded concept{criterion.codings.length === 1 ? "" : "s"}
                          </span>
                        ) : null}
                      </div>
                      <p className="mt-3 text-base font-semibold leading-7 text-ink">{criterion.text}</p>
                      <div className="mt-4">
                        <StructuredDataView
                          data={criterion.metadata}
                          emptyLabel="No additional FHIR extension fields were exported for this criterion."
                        />
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-4 text-sm leading-7 text-ink/68">No exportable eligibility extensions are present for this trial.</p>
        )}
      </section>
    </div>
  );
}
