import { createPatientAction } from "@/app/actions";
import { PageHeader } from "@/components/page-header";
import { Panel } from "@/components/panel";
import { ctmApi } from "@/lib/api/client";
import { formatDate } from "@/lib/format";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function PatientsPage() {
  const patients = await ctmApi.listPatients("?per_page=50");

  return (
    <>
      <PageHeader
        label="Patient Intake"
        title="Create a patient profile and launch deterministic trial matching."
        description="The intake form is intentionally server-side and minimal: enough to exercise the normalized patient store and matching engine without leaking the backend key."
      />

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <Panel title="Create Patient" eyebrow="Protected write">
          <form action={createPatientAction} className="grid gap-4">
            <input className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3" name="external_id" placeholder="External ID" />
            <div className="grid gap-4 md:grid-cols-3">
              <select className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3" name="sex" defaultValue="">
                <option value="">Sex</option>
                <option value="female">Female</option>
                <option value="male">Male</option>
                <option value="other">Other</option>
                <option value="unknown">Unknown</option>
              </select>
              <input className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3" name="birth_date" placeholder="Birth date YYYY-MM-DD" />
              <input className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3" name="ecog_status" placeholder="ECOG" />
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <select className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3" name="can_consent" defaultValue="">
                <option value="">Can consent</option>
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
              <select className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3" name="protocol_compliant" defaultValue="">
                <option value="">Protocol compliant</option>
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
              <select className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3" name="is_healthy_volunteer" defaultValue="">
                <option value="">Healthy volunteer</option>
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <select className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3" name="claustrophobic" defaultValue="">
                <option value="">Claustrophobic</option>
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
              <select className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3" name="motion_intolerant" defaultValue="">
                <option value="">Motion intolerant</option>
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
              <select className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3" name="pregnant" defaultValue="">
                <option value="">Pregnant</option>
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
            </div>
            <div className="grid gap-4 md:grid-cols-1">
              <select className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3" name="mr_device_present" defaultValue="">
                <option value="">MR-incompatible device present</option>
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
            </div>
            <textarea className="min-h-24 rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3" name="conditions" placeholder="One condition per line" />
            <textarea className="min-h-24 rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3" name="biomarkers" placeholder="One biomarker per line" />
            <textarea className="min-h-24 rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3" name="medications" placeholder="One active medication per line" />
            <div className="grid gap-4 md:grid-cols-4">
              <input className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3" name="lab_name" placeholder="Lab name" />
              <input className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3" name="lab_code" placeholder="LOINC code" />
              <input className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3" name="lab_value" placeholder="Numeric value" />
              <input className="rounded-2xl border border-ink/10 bg-sand/70 px-4 py-3" name="lab_unit" placeholder="Unit" />
            </div>
            <button className="rounded-2xl bg-ink px-5 py-3 font-semibold text-sand" type="submit">
              Create patient
            </button>
          </form>
        </Panel>

        <Panel title="Registry" eyebrow="Existing patients">
          {patients.items.length ? (
            <div className="grid gap-4">
              {patients.items.map((patient) => (
                <Link
                  key={patient.id}
                  href={`/patients/${patient.id}`}
                  className="rounded-3xl border border-ink/8 bg-white/70 p-5 transition hover:border-tide/25"
                >
                  <p className="text-sm font-semibold text-ink">{patient.external_id ?? patient.id.slice(0, 8)}</p>
                  <p className="mt-1 text-sm text-ink/68">
                    {patient.sex ?? "Unknown sex"} · {patient.birth_date ? formatDate(patient.birth_date) : "No birth date"}
                  </p>
                </Link>
              ))}
            </div>
          ) : (
            <div className="rounded-3xl border border-dashed border-ink/12 bg-sand/55 p-5 text-sm leading-7 text-ink/68">
              No patient profiles exist yet. Create one on the left after you have at least one ingested trial, then open the patient record and run matching.
            </div>
          )}
        </Panel>
      </div>
    </>
  );
}
