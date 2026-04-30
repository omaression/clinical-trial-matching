import Link from "next/link";

import { matchPatientAction, simulateMatchAction } from "@/app/actions";
import { PageHeader } from "@/components/page-header";
import { Panel } from "@/components/panel";
import { StatusPill } from "@/components/status-pill";
import { ctmApi } from "@/lib/api/client";
import { formatDate, formatPercent } from "@/lib/format";

export const dynamic = "force-dynamic";

type SearchParams = Record<string, string | string[] | undefined>;

function firstValue(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function PatientDetailPage({
  params,
  searchParams
}: {
  params: Promise<{ patientId: string }>;
  searchParams?: Promise<SearchParams>;
}) {
  const { patientId } = await params;
  const queryParams = (await searchParams) ?? {};
  const error = firstValue(queryParams.error);
  const [patient, matches] = await Promise.all([
    ctmApi.getPatient(patientId),
    ctmApi.listPatientMatches(patientId, "?per_page=20")
  ]);

  return (
    <>
      <PageHeader
        label="Patient Detail"
        title={patient.external_id ?? patient.id}
        description="Launch a fresh match run or inspect persisted results and explanations."
        actions={
          <form action={matchPatientAction}>
            <input name="patient_id" type="hidden" value={patient.id} />
            <button className="rounded-full bg-ink px-5 py-3 text-sm font-semibold text-sand" type="submit">
              Run matching
            </button>
          </form>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
        {error ? (
          <div className="xl:col-span-2">
            <Panel title="Simulation request failed" eyebrow="Validation error">
              <p className="text-sm text-red-700">{error}</p>
            </Panel>
          </div>
        ) : null}

        <Panel title="Profile" eyebrow="Normalized facts">
          <div className="space-y-4 text-sm text-ink/75">
            <p>Sex: {patient.sex ?? "Unknown"}</p>
            <p>Birth date: {patient.birth_date ? formatDate(patient.birth_date) : "Unavailable"}</p>
            <p>ECOG: {patient.ecog_status ?? "Unavailable"}</p>
            <p>Can consent: {patient.can_consent === null || patient.can_consent === undefined ? "Unknown" : patient.can_consent ? "Yes" : "No"}</p>
            <p>Protocol compliant: {patient.protocol_compliant === null || patient.protocol_compliant === undefined ? "Unknown" : patient.protocol_compliant ? "Yes" : "No"}</p>
            <p>Claustrophobic: {patient.claustrophobic === null || patient.claustrophobic === undefined ? "Unknown" : patient.claustrophobic ? "Yes" : "No"}</p>
            <p>Motion intolerant: {patient.motion_intolerant === null || patient.motion_intolerant === undefined ? "Unknown" : patient.motion_intolerant ? "Yes" : "No"}</p>
            <p>Pregnant: {patient.pregnant === null || patient.pregnant === undefined ? "Unknown" : patient.pregnant ? "Yes" : "No"}</p>
            <p>MR-incompatible device present: {patient.mr_device_present === null || patient.mr_device_present === undefined ? "Unknown" : patient.mr_device_present ? "Yes" : "No"}</p>
            <p>Conditions: {patient.conditions.map((item) => item.description).join(", ") || "None"}</p>
            <p>Biomarkers: {patient.biomarkers.map((item) => item.description).join(", ") || "None"}</p>
            <p>Medications: {patient.medications.map((item) => item.description).join(", ") || "None"}</p>
          </div>
        </Panel>

        <Panel title="What-if simulator" eyebrow="Read-only scenario">
          <form action={simulateMatchAction} className="grid gap-4 text-sm text-ink/75">
            <input name="patient_id" type="hidden" value={patient.id} />
            <p>
              Runs a simulated match without changing this patient. Leave ECOG blank to preserve the current value;
              fact lists are preserved unless you explicitly choose to replace or clear them.
            </p>
            <label className="grid gap-2">
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-ink/45">ECOG status</span>
              <input
                className="rounded-2xl border border-ink/10 bg-white px-4 py-3 text-ink"
                inputMode="numeric"
                max={5}
                min={0}
                name="ecog_status"
                placeholder={
                  patient.ecog_status === null || patient.ecog_status === undefined
                    ? "Leave blank to preserve"
                    : `Current: ${patient.ecog_status}`
                }
                type="number"
              />
              <p className="text-xs text-ink/50">Leave blank to preserve the current ECOG value.</p>
            </label>
            <label className="grid gap-2">
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-ink/45">Biomarkers</span>
              <textarea
                className="min-h-24 rounded-2xl border border-ink/10 bg-white px-4 py-3 text-ink"
                name="biomarkers"
                placeholder="Optional replacement list; leave blank to preserve unless checked"
              />
              <label className="flex items-center gap-2 text-xs text-ink/55">
                <input name="biomarkers_replace" type="checkbox" value="true" />
                Replace biomarkers with this list; checked with a blank box simulates clearing them.
              </label>
            </label>
            <label className="grid gap-2">
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-ink/45">Medications</span>
              <textarea
                className="min-h-24 rounded-2xl border border-ink/10 bg-white px-4 py-3 text-ink"
                name="medications"
                placeholder="Optional replacement list; leave blank to preserve unless checked"
              />
              <label className="flex items-center gap-2 text-xs text-ink/55">
                <input name="medications_replace" type="checkbox" value="true" />
                Replace medications with this active-medication list; checked with a blank box simulates clearing them.
              </label>
            </label>
            <label className="grid gap-2">
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-ink/45">Therapies</span>
              <textarea
                className="min-h-24 rounded-2xl border border-ink/10 bg-white px-4 py-3 text-ink"
                name="therapies"
                placeholder="Optional replacement list; leave blank to preserve unless checked"
              />
              <label className="flex items-center gap-2 text-xs text-ink/55">
                <input name="therapies_replace" type="checkbox" value="true" />
                Replace therapies with this list; checked with a blank box simulates clearing them.
              </label>
            </label>
            <div className="grid gap-3 rounded-3xl border border-ink/8 bg-sand/45 p-4">
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-ink/45">Lab value</span>
              <input
                className="rounded-2xl border border-ink/10 bg-white px-4 py-3 text-ink"
                name="lab_name"
                placeholder="Lab name, e.g. ANC"
              />
              <div className="grid gap-3 md:grid-cols-2">
                <input
                  className="rounded-2xl border border-ink/10 bg-white px-4 py-3 text-ink"
                  inputMode="decimal"
                  name="lab_value"
                  placeholder="Numeric value"
                />
                <input
                  className="rounded-2xl border border-ink/10 bg-white px-4 py-3 text-ink"
                  name="lab_unit"
                  placeholder="Unit"
                />
              </div>
              <label className="flex items-center gap-2 text-xs text-ink/55">
                <input name="labs_replace" type="checkbox" value="true" />
                Replace labs with this value; checked with blank fields simulates clearing labs.
              </label>
            </div>
            <button className="rounded-full bg-ink px-5 py-3 text-sm font-semibold text-sand" type="submit">
              Run what-if scenario
            </button>
          </form>
        </Panel>

        <Panel title="Recent Match Results" eyebrow="Persisted runs">
          <div className="grid gap-4">
            {matches.items.map((match) => (
              <Link
                key={match.id}
                href={`/matches/${match.id}`}
                className="grid gap-3 rounded-3xl border border-ink/8 bg-sand/55 p-5 lg:grid-cols-[1.1fr_0.4fr_0.4fr]"
              >
                <div>
                  <p className="text-sm font-semibold text-ink">{match.trial_brief_title}</p>
                  <p className="mt-1 text-xs uppercase tracking-[0.22em] text-ink/45">{match.trial_nct_id}</p>
                  <p className="mt-2 text-sm text-ink/68">{match.summary_explanation}</p>
                </div>
                <div>
                  <StatusPill value={match.overall_status} />
                </div>
                <div className="text-right">
                  <p className="text-lg font-semibold text-ink">{formatPercent(match.determinate_score)}</p>
                  <p className="mt-1 text-xs uppercase tracking-[0.22em] text-ink/45">Determinate fit</p>
                  <p className="mt-2 text-sm text-ink/68">Coverage {formatPercent(match.coverage_ratio)}</p>
                  <p className="mt-1 text-xs uppercase tracking-[0.22em] text-ink/45">{formatDate(match.created_at)}</p>
                </div>
              </Link>
            ))}
          </div>
        </Panel>
      </div>
    </>
  );
}
