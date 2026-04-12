"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";

import { ctmApi } from "@/lib/api/client";

const createPatientSchema = z.object({
  external_id: z.string().trim().optional(),
  sex: z.enum(["male", "female", "other", "unknown"]).optional(),
  birth_date: z.string().trim().optional(),
  ecog_status: z.string().trim().optional(),
  is_healthy_volunteer: z.string().trim().optional(),
  can_consent: z.string().trim().optional(),
  protocol_compliant: z.string().trim().optional(),
  claustrophobic: z.string().trim().optional(),
  motion_intolerant: z.string().trim().optional(),
  pregnant: z.string().trim().optional(),
  mr_device_present: z.string().trim().optional(),
  conditions: z.string().trim().optional(),
  biomarkers: z.string().trim().optional(),
  medications: z.string().trim().optional(),
  lab_name: z.string().trim().optional(),
  lab_code: z.string().trim().optional(),
  lab_display: z.string().trim().optional(),
  lab_value: z.string().trim().optional(),
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

function optionalFormString(formData: FormData, key: string): string | undefined {
  const value = formData.get(key);
  return typeof value === "string" ? value : undefined;
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

export async function createPatientAction(formData: FormData) {
  const parsed = createPatientSchema.parse(Object.fromEntries(formData.entries()));

  const patient = await ctmApi.createPatient({
    external_id: parsed.external_id || undefined,
    sex: parsed.sex,
    birth_date: parsed.birth_date || undefined,
    ecog_status: safeNumber(parsed.ecog_status),
    is_healthy_volunteer: safeBoolean(parsed.is_healthy_volunteer),
    can_consent: safeBoolean(parsed.can_consent),
    protocol_compliant: safeBoolean(parsed.protocol_compliant),
    claustrophobic: safeBoolean(parsed.claustrophobic),
    motion_intolerant: safeBoolean(parsed.motion_intolerant),
    pregnant: safeBoolean(parsed.pregnant),
    mr_device_present: safeBoolean(parsed.mr_device_present),
    conditions: splitLines(parsed.conditions).map((description) => ({ description })),
    biomarkers: splitLines(parsed.biomarkers).map((description) => ({ description })),
    medications: splitLines(parsed.medications).map((description) => ({ description, active: true })),
    labs: parsed.lab_name
      ? [
          {
            description: parsed.lab_name,
            value_numeric: safeNumber(parsed.lab_value),
            unit: parsed.lab_unit || undefined,
            coded_concepts: parsed.lab_code
              ? [
                  {
                    system: "loinc",
                    code: parsed.lab_code,
                    display: parsed.lab_display || parsed.lab_name
                  }
                ]
              : []
          }
        ]
      : []
  });

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
