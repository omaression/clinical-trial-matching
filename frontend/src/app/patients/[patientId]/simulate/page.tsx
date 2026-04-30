import Link from "next/link";

import { PageHeader } from "@/components/page-header";
import { Panel } from "@/components/panel";
import { StatusPill } from "@/components/status-pill";
import { ctmApi } from "@/lib/api/client";
import { loadSimulationScenario } from "@/lib/simulation-store";

export const dynamic = "force-dynamic";

type SearchParams = Record<string, string | string[] | undefined>;

function firstValue(value: string | string[] | undefined): string | undefined {
  if (Array.isArray(value)) {
    return value[0];
  }
  return value;
}

function hasVisibleDelta(result: {
  status_changed: boolean;
  blockers_removed: string[];
  blockers_added: string[];
  missing_data_removed: string[];
  missing_data_added: string[];
  clarifiable_blockers_removed: string[];
  clarifiable_blockers_added: string[];
  unsupported_removed: string[];
  unsupported_added: string[];
  review_required_removed: string[];
  review_required_added: string[];
}): boolean {
  return (
    result.status_changed ||
    result.blockers_removed.length > 0 ||
    result.blockers_added.length > 0 ||
    result.missing_data_removed.length > 0 ||
    result.missing_data_added.length > 0 ||
    result.clarifiable_blockers_removed.length > 0 ||
    result.clarifiable_blockers_added.length > 0 ||
    result.unsupported_removed.length > 0 ||
    result.unsupported_added.length > 0 ||
    result.review_required_removed.length > 0 ||
    result.review_required_added.length > 0
  );
}

function renderAppliedList(items: { description: string }[] | null | undefined): string {
  if (items === undefined || items === null) {
    return "Baseline preserved";
  }
  if (items.length === 0) {
    return "Cleared";
  }
  return items.map((item) => item.description).join(", ");
}

function SummaryCard({ label, value, helper }: { label: string; value: number | string; helper: string }) {
  return (
    <div className="rounded-3xl border border-ink/8 bg-sand/55 p-5">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-ink/45">{label}</p>
      <p className="mt-3 text-3xl font-semibold text-ink">{value}</p>
      <p className="mt-2 text-sm text-ink/60">{helper}</p>
    </div>
  );
}

export default async function PatientSimulationPage({
  params,
  searchParams
}: {
  params: Promise<{ patientId: string }>;
  searchParams?: Promise<SearchParams>;
}) {
  const { patientId } = await params;
  const queryParams = (await searchParams) ?? {};
  const scenarioToken = firstValue(queryParams.scenario);
  const request = scenarioToken ? await loadSimulationScenario(scenarioToken, patientId) : null;
  const patient = await ctmApi.getPatient(patientId);

  if (request === null) {
    return (
      <>
        <PageHeader
          label="What-if Scenario"
          title={`Simulated match for ${patient.external_id ?? patient.id}`}
          description="Exploratory eligibility deltas only. This simulation does not update patient facts or persist match results."
          actions={
            <Link className="rounded-full bg-ink px-5 py-3 text-sm font-semibold text-sand" href={`/patients/${patient.id}`}>
              Back to patient
            </Link>
          }
        />

        <Panel title="Scenario unavailable" eyebrow="Expired or invalid token">
          <p className="text-sm text-ink/70">
            The saved what-if inputs were not found or have expired. Return to the patient page and run a fresh simulation
            so results are never shown without the intended scenario patch.
          </p>
        </Panel>
      </>
    );
  }

  const simulation = await ctmApi.simulatePatientMatch(patientId, request);

  const changedResults = simulation.results.filter(hasVisibleDelta);
  const visibleResults = changedResults.length > 0 ? changedResults : simulation.results.slice(0, 10);

  return (
    <>
      <PageHeader
        label="What-if Scenario"
        title={`Simulated match for ${patient.external_id ?? patient.id}`}
        description="Exploratory eligibility deltas only. This simulation does not update patient facts or persist match results."
        actions={
          <Link className="rounded-full bg-ink px-5 py-3 text-sm font-semibold text-sand" href={`/patients/${patient.id}`}>
            Back to patient
          </Link>
        }
      />

      <div className="grid gap-6 lg:grid-cols-4">
        <SummaryCard
          label="Newly eligible"
          value={simulation.deltas.newly_eligible}
          helper="Trials that moved to eligible in the scenario."
        />
        <SummaryCard
          label="Newly blocked"
          value={simulation.deltas.newly_blocked}
          helper="Trials that became less favorable."
        />
        <SummaryCard
          label="Changed"
          value={simulation.deltas.status_changed}
          helper="Results with any status change."
        />
        <SummaryCard
          label="Baseline source"
          value={simulation.baseline_source}
          helper="Baseline and scenario are recomputed against the same current corpus."
        />
      </div>

      <Panel title="Scenario inputs" eyebrow="Applied patch">
        <div className="grid gap-3 text-sm text-ink/70 md:grid-cols-2">
          <p>ECOG: {simulation.applied_changes.ecog_status ?? "Baseline preserved"}</p>
          <p>Biomarkers: {renderAppliedList(simulation.applied_changes.biomarkers)}</p>
          <p>Medications: {renderAppliedList(simulation.applied_changes.medications)}</p>
          <p>Therapies: {renderAppliedList(simulation.applied_changes.therapies)}</p>
          <p>Labs: {renderAppliedList(simulation.applied_changes.labs)}</p>
        </div>
      </Panel>

      <Panel title="Simulation result deltas" eyebrow="Baseline vs simulated">
        <div className="grid gap-4">
          {visibleResults.map((result) => (
            <div key={result.trial_id} className="rounded-3xl border border-ink/8 bg-sand/55 p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold text-ink">{result.trial_brief_title}</p>
                  <p className="mt-1 text-xs uppercase tracking-[0.22em] text-ink/45">{result.trial_nct_id}</p>
                </div>
                <div className="flex items-center gap-2">
                  {result.baseline_status ? <StatusPill value={result.baseline_status} /> : null}
                  <span className="text-ink/40">→</span>
                  {result.scenario_status ? <StatusPill value={result.scenario_status} /> : null}
                </div>
              </div>
              <div className="mt-4 grid gap-3 text-sm text-ink/68 md:grid-cols-2">
                <div>
                  <p className="font-semibold text-ink">Blockers removed</p>
                  <p>{result.blockers_removed.join("; ") || "None"}</p>
                </div>
                <div>
                  <p className="font-semibold text-ink">Blockers added</p>
                  <p>{result.blockers_added.join("; ") || "None"}</p>
                </div>
                <div>
                  <p className="font-semibold text-ink">Missing data removed</p>
                  <p>{result.missing_data_removed.join("; ") || "None"}</p>
                </div>
                <div>
                  <p className="font-semibold text-ink">Missing data added</p>
                  <p>{result.missing_data_added.join("; ") || "None"}</p>
                </div>
                <div>
                  <p className="font-semibold text-ink">Clarifiable blockers removed</p>
                  <p>{result.clarifiable_blockers_removed.join("; ") || "None"}</p>
                </div>
                <div>
                  <p className="font-semibold text-ink">Clarifiable blockers added</p>
                  <p>{result.clarifiable_blockers_added.join("; ") || "None"}</p>
                </div>
                <div>
                  <p className="font-semibold text-ink">Unsupported criteria removed</p>
                  <p>{result.unsupported_removed.join("; ") || "None"}</p>
                </div>
                <div>
                  <p className="font-semibold text-ink">Unsupported criteria added</p>
                  <p>{result.unsupported_added.join("; ") || "None"}</p>
                </div>
                <div>
                  <p className="font-semibold text-ink">Review required removed</p>
                  <p>{result.review_required_removed.join("; ") || "None"}</p>
                </div>
                <div>
                  <p className="font-semibold text-ink">Review required added</p>
                  <p>{result.review_required_added.join("; ") || "None"}</p>
                </div>
              </div>
              <p className="mt-4 text-sm text-ink/60">{result.scenario_summary_explanation}</p>
            </div>
          ))}
        </div>
      </Panel>
    </>
  );
}
