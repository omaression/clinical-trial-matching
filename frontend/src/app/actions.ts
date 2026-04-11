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

export async function createPatientAction(formData: FormData) {
  const parsed = createPatientSchema.parse(Object.fromEntries(formData.entries()));

  const patient = await ctmApi.createPatient({
    external_id: parsed.external_id || undefined,
    sex: parsed.sex,
    birth_date: parsed.birth_date || undefined,
    ecog_status: safeNumber(parsed.ecog_status),
    is_healthy_volunteer:
      parsed.is_healthy_volunteer === "true" ? true : parsed.is_healthy_volunteer === "false" ? false : undefined,
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
  const parsed = ingestTrialSchema.parse(Object.fromEntries(formData.entries()));
  const result = await ctmApi.ingestTrial({ nct_id: parsed.nct_id.toUpperCase() });

  revalidatePath("/");
  revalidatePath("/pipeline");
  revalidatePath("/review");
  revalidatePath("/trials");
  redirect(`/trials/${result.trial_id}`);
}

export async function searchIngestAction(formData: FormData) {
  const parsed = searchIngestSchema.parse(Object.fromEntries(formData.entries()));
  const result = await ctmApi.searchAndIngest({
    condition: parsed.condition || undefined,
    status: parsed.status || undefined,
    phase: parsed.phase || undefined,
    limit: parsed.limit
  });

  revalidatePath("/");
  revalidatePath("/pipeline");
  revalidatePath("/review");
  revalidatePath("/trials");

  const query = new URLSearchParams({
    batch: "1",
    attempted: String(result.attempted),
    returned: String(result.returned),
    ingested: String(result.ingested),
    skipped: String(result.skipped),
    failed: String(result.failed)
  });
  if (result.total_count !== undefined && result.total_count !== null) {
    query.set("total_count", String(result.total_count));
  }
  if (result.next_page_token) {
    query.set("has_more", "1");
  }
  if (parsed.condition) {
    query.set("condition", parsed.condition);
  }
  if (parsed.status) {
    query.set("status", parsed.status);
  }
  if (parsed.phase) {
    query.set("phase", parsed.phase);
  }

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
  const reviewNotes = z.string().optional().parse(formData.get("review_notes"));
  const correctedJson = z.string().optional().parse(formData.get("corrected_data"));

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
