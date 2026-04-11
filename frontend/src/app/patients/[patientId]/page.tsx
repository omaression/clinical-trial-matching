import Link from "next/link";

import { matchPatientAction } from "@/app/actions";
import { PageHeader } from "@/components/page-header";
import { Panel } from "@/components/panel";
import { StatusPill } from "@/components/status-pill";
import { ctmApi } from "@/lib/api/client";
import { formatDate, formatPercent } from "@/lib/format";

export default async function PatientDetailPage({
  params
}: {
  params: Promise<{ patientId: string }>;
}) {
  const { patientId } = await params;
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
        <Panel title="Profile" eyebrow="Normalized facts">
          <div className="space-y-4 text-sm text-ink/75">
            <p>Sex: {patient.sex ?? "Unknown"}</p>
            <p>Birth date: {patient.birth_date ? formatDate(patient.birth_date) : "Unavailable"}</p>
            <p>ECOG: {patient.ecog_status ?? "Unavailable"}</p>
            <p>Conditions: {patient.conditions.map((item) => item.description).join(", ") || "None"}</p>
            <p>Biomarkers: {patient.biomarkers.map((item) => item.description).join(", ") || "None"}</p>
            <p>Medications: {patient.medications.map((item) => item.description).join(", ") || "None"}</p>
          </div>
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
                  <p className="text-lg font-semibold text-ink">{formatPercent(match.score)}</p>
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
