import "server-only";

import { getFrontendConfig } from "@/lib/config";
import type {
  ApiError,
  CriteriaListResponse,
  HealthResponse,
  IngestRequest,
  IngestResponse,
  MatchResultDetail,
  MatchResultListResponse,
  MatchRunResponse,
  PatientCreatePayload,
  PatientDetail,
  PatientListResponse,
  PipelineCoverageResponse,
  PipelineRunListResponse,
  PipelineStatusResponse,
  ReviewQueueResponse,
  SearchIngestRequest,
  SearchIngestResponse,
  TrialDetail,
  TrialListResponse
} from "@/lib/api/types";

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH";
  auth?: boolean;
  body?: unknown;
  headers?: HeadersInit;
  accept?: string;
  cache?: RequestCache;
};

async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const frontendConfig = getFrontendConfig();
  const url = `${frontendConfig.apiBaseUrl}${path}`;
  const headers = new Headers(options.headers);
  headers.set("Accept", options.accept ?? "application/json");
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (options.auth) {
    if (!frontendConfig.apiKey) {
      throw new Error("CTM_FRONTEND_API_KEY is required for protected frontend operations.");
    }
    headers.set("X-API-Key", frontendConfig.apiKey);
  }

  const response = await fetch(url, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    cache: options.cache ?? "no-store"
  });

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as ApiError | null;
    throw new Error(payload?.detail ?? `API request failed with status ${response.status}`);
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/fhir+json") || contentType.includes("application/json")) {
    return (await response.json()) as T;
  }

  return (await response.text()) as T;
}

export const ctmApi = {
  getHealth: () => apiRequest<HealthResponse>("/health"),
  listTrials: (query = "") => apiRequest<TrialListResponse>(`/trials${query}`),
  getTrial: (trialId: string) => apiRequest<TrialDetail>(`/trials/${trialId}`),
  ingestTrial: (payload: IngestRequest) =>
    apiRequest<IngestResponse>("/trials/ingest", { method: "POST", auth: true, body: payload }),
  searchAndIngest: (payload: SearchIngestRequest) =>
    apiRequest<SearchIngestResponse>("/trials/search-ingest", { method: "POST", auth: true, body: payload }),
  getTrialCriteria: (trialId: string, query = "") =>
    apiRequest<CriteriaListResponse>(`/trials/${trialId}/criteria${query}`),
  getTrialFhir: (trialId: string) =>
    apiRequest<Record<string, unknown>>(`/trials/${trialId}/fhir`, {
      accept: "application/fhir+json"
    }),
  getReviewQueue: (query = "") => apiRequest<ReviewQueueResponse>(`/review${query}`, { auth: true }),
  getPipelineStatus: () => apiRequest<PipelineStatusResponse>("/pipeline/status", { auth: true }),
  getPipelineCoverage: () => apiRequest<PipelineCoverageResponse>("/pipeline/coverage", { auth: true }),
  listPipelineRuns: (query = "") =>
    apiRequest<PipelineRunListResponse>(`/pipeline/runs${query}`, { auth: true }),
  listPatients: (query = "") => apiRequest<PatientListResponse>(`/patients${query}`, { auth: true }),
  getPatient: (patientId: string) => apiRequest<PatientDetail>(`/patients/${patientId}`, { auth: true }),
  createPatient: (payload: PatientCreatePayload) =>
    apiRequest<PatientDetail>("/patients", { method: "POST", auth: true, body: payload }),
  updatePatient: (patientId: string, payload: Partial<PatientCreatePayload>) =>
    apiRequest<PatientDetail>(`/patients/${patientId}`, { method: "PATCH", auth: true, body: payload }),
  matchPatient: (patientId: string) =>
    apiRequest<MatchRunResponse>(`/patients/${patientId}/match`, { method: "POST", auth: true }),
  listPatientMatches: (patientId: string, query = "") =>
    apiRequest<MatchResultListResponse>(`/patients/${patientId}/matches${query}`, { auth: true }),
  getMatch: (matchId: string) => apiRequest<MatchResultDetail>(`/matches/${matchId}`, { auth: true }),
  reviewCriterion: (criterionId: string, payload: unknown) =>
    apiRequest(`/criteria/${criterionId}/review`, { method: "PATCH", auth: true, body: payload }),
  reextractTrial: (trialId: string) =>
    apiRequest(`/trials/${trialId}/re-extract`, { method: "POST", auth: true })
};
