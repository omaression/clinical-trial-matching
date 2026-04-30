"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";

import { ctmApi } from "@/lib/api/client";
import { saveSimulationScenario } from "@/lib/simulation-store";

const booleanStringSchema = z.enum(["true", "false"]);
const numericStringSchema = z.string().trim().refine(
  (value) => Number.isFinite(Number(value)),
  "Use a valid number."
);
const ecogStringSchema = z.string().trim().refine(
  (value) => /^\d+$/.test(value) && Number(value) >= 0 && Number(value) <= 5,
  "Use an ECOG status from 0 to 5."
);

const createPatientSchema = z.object({
  external_id: z.string().trim().optional(),
  sex: z.enum(["male", "female", "other", "unknown"]).optional(),
  birth_date: z.string().trim().optional(),
  ecog_status: ecogStringSchema.optional(),
  is_healthy_volunteer: booleanStringSchema.optional(),
  can_consent: booleanStringSchema.optional(),
  protocol_compliant: booleanStringSchema.optional(),
  claustrophobic: booleanStringSchema.optional(),
  motion_intolerant: booleanStringSchema.optional(),
  pregnant: booleanStringSchema.optional(),
  mr_device_present: booleanStringSchema.optional(),
  conditions: z.string().trim().optional(),
  biomarkers: z.string().trim().optional(),
  medications: z.string().trim().optional(),
  lab_name: z.string().trim().optional(),
  lab_code: z.string().trim().optional(),
  lab_display: z.string().trim().optional(),
  lab_value: numericStringSchema.optional(),
  lab_unit: z.string().trim().optional()
});

const ingestTrialSchema = z.object({
  nct_id: z.string().trim().regex(/^NCT\d{8}$/i, "Use an NCT ID like NCT05346328.")
});

const searchIngestSchema = z.object({
  condition: z.string().trim().optional(),
  status: z.string().trim().optional(),
  phase: z.string().trim().optional(),
  limit: z.coerce.number().int().min(1).max(100).default(10)
}).refine(
  (value) => Boolean(value.condition || value.status || value.phase),
  { message: "Provide at least one search field." }
);

const simulateMatchSchema = z.object({
  patient_id: z.string().uuid(),
  ecog_status: ecogStringSchema.optional(),
  biomarkers: z.string().trim().optional(),
  biomarkers_replace: z.enum(["true"]).optional(),
  medications: z.string().trim().optional(),
  medications_replace: z.enum(["true"]).optional(),
  therapies: z.string().trim().optional(),
  therapies_replace: z.enum(["true"]).optional(),
  lab_name: z.string().trim().optional(),
  lab_value: numericStringSchema.optional(),
  lab_unit: z.string().trim().optional(),
  labs_replace: z.enum(["true"]).optional()
});

function splitLines(value?: string): string[] {
  if (!value) {
    return [];
  }
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function safeNumber(value?: string): number | undefined {
  if (!value) {
    return undefined;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function safeBoolean(value?: string): boolean | undefined {
  if (value === "true") {
    return true;
  }
  if (value === "false") {
    return false;
  }
  return undefined;
}

function normalizeFormValue(value: FormDataEntryValue | null): string | undefined {
  if (typeof value !== "string") {
    return undefined;
  }

  const normalized = value.trim();
  return normalized === "" ? undefined : normalized;
}

function normalizedFormEntries(formData: FormData): Record<string, string | undefined> {
  const normalized: Record<string, string | undefined> = {};

  formData.forEach((value, key) => {
    normalized[key] = normalizeFormValue(value);
  });

  return normalized;
}

function optionalFormString(formData: FormData, key: string): string | undefined {
  return normalizeFormValue(formData.get(key));
}

function actionErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof z.ZodError) {
    return error.issues.map((issue) => issue.message).join(" ");
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

function redirectToPipelineWithError(error: string, values?: Record<string, string | undefined>): never {
  const query = new URLSearchParams({ error });
  for (const [key, value] of Object.entries(values ?? {})) {
    if (value) {
      query.set(key, value);
    }
  }
  redirect(`/pipeline?${query.toString()}`);
}

function redirectToPatientWithError(patientId: string, error: string, values?: Record<string, string | undefined>): never {
  const query = new URLSearchParams({ error });
  for (const [key, value] of Object.entries(values ?? {})) {
    if (value && key !== "patient_id") {
      query.set(key, value);
    }
  }
  redirect(`/patients/${patientId}?${query.toString()}`);
}

function redirectToPatientsWithError(error: string, values?: Record<string, string | undefined>): never {
  const query = new URLSearchParams({ error });
  for (const [key, value] of Object.entries(values ?? {})) {
    if (value) {
      query.set(key, value);
    }
  }
  redirect(`/patients?${query.toString()}`);
}

export async function createPatientAction(formData: FormData) {
  const submitted = normalizedFormEntries(formData);
  const parsed = createPatientSchema.safeParse(submitted);
  if (!parsed.success) {
    redirectToPatientsWithError(actionErrorMessage(parsed.error, "Patient creation failed validation."), submitted);
  }
  const data = parsed.data;

  let patient;
  try {
    patient = await ctmApi.createPatient({
      external_id: data.external_id || undefined,
      sex: data.sex,
      birth_date: data.birth_date || undefined,
      ecog_status: safeNumber(data.ecog_status),
      is_healthy_volunteer: safeBoolean(data.is_healthy_volunteer),
      can_consent: safeBoolean(data.can_consent),
      protocol_compliant: safeBoolean(data.protocol_compliant),
      claustrophobic: safeBoolean(data.claustrophobic),
      motion_intolerant: safeBoolean(data.motion_intolerant),
      pregnant: safeBoolean(data.pregnant),
      mr_device_present: safeBoolean(data.mr_device_present),
      conditions: splitLines(data.conditions).map((description) => ({ description })),
      biomarkers: splitLines(data.biomarkers).map((description) => ({ description })),
      medications: splitLines(data.medications).map((description) => ({ description, active: true })),
      labs: data.lab_name
        ? [
            {
              description: data.lab_name,
              value_numeric: safeNumber(data.lab_value),
              unit: data.lab_unit || undefined,
              coded_concepts: data.lab_code
                ? [
                    {
                      system: "loinc",
                      code: data.lab_code,
                      display: data.lab_display || data.lab_name
                    }
                  ]
                : []
            }
          ]
        : []
    });
  } catch (error) {
    redirectToPatientsWithError(actionErrorMessage(error, "Patient creation failed."), submitted);
  }

  revalidatePath("/patients");
  redirect(`/patients/${patient.id}`);
}

export async function ingestTrialAction(formData: FormData) {
  const rawNctId = optionalFormString(formData, "nct_id") ?? "";
  const parsed = ingestTrialSchema.safeParse({ nct_id: rawNctId });
  if (!parsed.success) {
    redirectToPipelineWithError(actionErrorMessage(parsed.error, "Use a valid NCT ID."), {
      nct_id: rawNctId
    });
  }
  const data = parsed.data;

  let result;
  try {
    result = await ctmApi.ingestTrial({ nct_id: data.nct_id.toUpperCase() });
  } catch (error) {
    redirectToPipelineWithError(actionErrorMessage(error, "Trial ingest failed."), {
      nct_id: rawNctId
    });
  }
  const ingestResult = result;

  revalidatePath("/");
  revalidatePath("/pipeline");
  revalidatePath("/review");
  revalidatePath("/trials");
  redirect(`/trials/${ingestResult.trial_id}`);
}

export async function searchIngestAction(formData: FormData) {
  const submitted = {
    condition: optionalFormString(formData, "condition") ?? "",
    status: optionalFormString(formData, "status") ?? "",
    phase: optionalFormString(formData, "phase") ?? "",
    limit: optionalFormString(formData, "limit") ?? "10"
  };
  const parsed = searchIngestSchema.safeParse(submitted);
  if (!parsed.success) {
    redirectToPipelineWithError(actionErrorMessage(parsed.error, "Search ingest failed validation."), submitted);
  }
  const data = parsed.data;

  let result;
  try {
    result = await ctmApi.searchAndIngest({
      condition: data.condition || undefined,
      status: data.status || undefined,
      phase: data.phase || undefined,
      limit: data.limit
    });
  } catch (error) {
    redirectToPipelineWithError(actionErrorMessage(error, "Search ingest failed."), submitted);
  }
  const searchResult = result;

  revalidatePath("/");
  revalidatePath("/pipeline");
  revalidatePath("/review");
  revalidatePath("/trials");

  const query = new URLSearchParams({
    batch: "1",
    attempted: String(searchResult.attempted),
    returned: String(searchResult.returned),
    ingested: String(searchResult.ingested),
    skipped: String(searchResult.skipped),
    failed: String(searchResult.failed)
  });
  if (searchResult.total_count !== undefined && searchResult.total_count !== null) {
    query.set("total_count", String(searchResult.total_count));
  }
  if (searchResult.next_page_token) {
    query.set("has_more", "1");
  }
  if (data.condition) {
    query.set("condition", data.condition);
  }
  if (data.status) {
    query.set("status", data.status);
  }
  if (data.phase) {
    query.set("phase", data.phase);
  }
  query.set("limit", String(data.limit));

  redirect(`/pipeline?${query.toString()}`);
}

export async function matchPatientAction(formData: FormData) {
  const patientId = z.string().uuid().parse(formData.get("patient_id"));
  const run = await ctmApi.matchPatient(patientId);
  revalidatePath(`/patients/${patientId}`);
  revalidatePath("/patients");
  const topResult = run.results[0];
  redirect(topResult ? `/matches/${topResult.id}` : `/patients/${patientId}`);
}

export async function simulateMatchAction(formData: FormData) {
  const submitted = normalizedFormEntries(formData);
  const parsed = simulateMatchSchema.safeParse(submitted);
  if (!parsed.success) {
    const patientId = submitted.patient_id ?? "";
    if (z.string().uuid().safeParse(patientId).success) {
      redirectToPatientWithError(patientId, actionErrorMessage(parsed.error, "Simulation failed validation."), submitted);
    }
    redirectToPatientsWithError(actionErrorMessage(parsed.error, "Simulation failed validation."), submitted);
  }

  const data = parsed.data;
  const payload = {
    ...(data.ecog_status !== undefined ? { ecog_status: safeNumber(data.ecog_status) } : {}),
    ...(data.biomarkers_replace === "true"
      ? { biomarkers: splitLines(data.biomarkers).map((description) => ({ description })) }
      : {}),
    ...(data.medications_replace === "true"
      ? { medications: splitLines(data.medications).map((description) => ({ description, active: true })) }
      : {}),
    ...(data.therapies_replace === "true"
      ? { therapies: splitLines(data.therapies).map((description) => ({ description })) }
      : {}),
    ...(data.labs_replace === "true"
      ? {
          labs: data.lab_name
            ? [
                {
                  description: data.lab_name,
                  value_numeric: safeNumber(data.lab_value),
                  unit: data.lab_unit || undefined
                }
              ]
            : []
        }
      : {})
  };
  let token;
  try {
    token = await saveSimulationScenario(data.patient_id, payload);
  } catch (error) {
    redirectToPatientWithError(data.patient_id, actionErrorMessage(error, "Simulation scenario could not be saved."), submitted);
  }

  redirect(`/patients/${data.patient_id}/simulate?scenario=${token}`);
}

export async function reviewCriterionAction(formData: FormData) {
  const criterionId = z.string().uuid().parse(formData.get("criterion_id"));
  const action = z.enum(["accept", "reject", "correct"]).parse(formData.get("action"));
  const reviewedBy = z.string().min(1).parse(formData.get("reviewed_by"));
  const reviewNotes = z.string().optional().parse(optionalFormString(formData, "review_notes"));
  const correctedJson = z.string().optional().parse(optionalFormString(formData, "corrected_data"));

  const payload: Record<string, unknown> = {
    action,
    reviewed_by: reviewedBy,
    review_notes: reviewNotes || undefined
  };
  if (action === "correct" && correctedJson) {
    payload.corrected_data = JSON.parse(correctedJson);
  }

  await ctmApi.reviewCriterion(criterionId, payload);
  revalidatePath("/review");
  redirect("/review");
}

export async function reextractTrialAction(formData: FormData) {
  const trialId = z.string().uuid().parse(formData.get("trial_id"));
  await ctmApi.reextractTrial(trialId);
  revalidatePath(`/trials/${trialId}`);
  revalidatePath("/pipeline");
  redirect(`/trials/${trialId}`);
}
