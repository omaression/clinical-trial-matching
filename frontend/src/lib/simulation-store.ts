import "server-only";

import { createCipheriv, createDecipheriv, createHash, randomBytes, randomUUID } from "crypto";
import { cookies } from "next/headers";

import type { MatchSimulationRequest } from "@/lib/api/types";

const TTL_SECONDS = 30 * 60;
const TTL_MS = TTL_SECONDS * 1000;
const COOKIE_PREFIX = "ctm_match_sim_";
const MAX_COOKIE_VALUE_BYTES = 3500;
const TOKEN_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const DEVELOPMENT_SECRET = "ctm-match-simulation-development-only-secret";

type StoredSimulationScenario = {
  token: string;
  patientId: string;
  payload: MatchSimulationRequest;
  expiresAt: number;
};

function cookieName(patientId: string): string {
  return `${COOKIE_PREFIX}${patientId}`;
}

function encryptionKey(): Buffer {
  const configuredSecret = process.env.MATCH_SIMULATION_COOKIE_SECRET ?? process.env.NEXTAUTH_SECRET;
  if (!configuredSecret && process.env.NODE_ENV === "production") {
    throw new Error("MATCH_SIMULATION_COOKIE_SECRET or NEXTAUTH_SECRET must be configured in production.");
  }

  return createHash("sha256")
    .update(configuredSecret ?? DEVELOPMENT_SECRET)
    .digest();
}

function sealScenario(stored: StoredSimulationScenario): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", encryptionKey(), iv);
  const ciphertext = Buffer.concat([cipher.update(JSON.stringify(stored), "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  return Buffer.concat([iv, tag, ciphertext]).toString("base64url");
}

function unsealScenario(value: string): StoredSimulationScenario | null {
  try {
    const sealed = Buffer.from(value, "base64url");
    const iv = sealed.subarray(0, 12);
    const tag = sealed.subarray(12, 28);
    const ciphertext = sealed.subarray(28);
    const decipher = createDecipheriv("aes-256-gcm", encryptionKey(), iv);
    decipher.setAuthTag(tag);
    const raw = Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString("utf8");
    return JSON.parse(raw) as StoredSimulationScenario;
  } catch {
    return null;
  }
}

export async function saveSimulationScenario(patientId: string, payload: MatchSimulationRequest): Promise<string> {
  const token = randomUUID();
  const stored: StoredSimulationScenario = {
    token,
    patientId,
    payload,
    expiresAt: Date.now() + TTL_MS
  };
  const sealed = sealScenario(stored);
  if (Buffer.byteLength(sealed, "utf8") > MAX_COOKIE_VALUE_BYTES) {
    throw new Error("Simulation scenario is too large. Shorten the replacement lists and try again.");
  }
  const cookieStore = await cookies();
  cookieStore.set(cookieName(patientId), sealed, {
    httpOnly: true,
    maxAge: TTL_SECONDS,
    path: `/patients/${patientId}/simulate`,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production"
  });
  return token;
}

export async function loadSimulationScenario(token: string, patientId: string): Promise<MatchSimulationRequest | null> {
  if (!TOKEN_PATTERN.test(token)) {
    return null;
  }

  const cookieStore = await cookies();
  const stored = unsealScenario(cookieStore.get(cookieName(patientId))?.value ?? "");
  if (
    !stored ||
    stored.token !== token ||
    stored.patientId !== patientId ||
    typeof stored.expiresAt !== "number" ||
    stored.expiresAt < Date.now()
  ) {
    return null;
  }
  return stored.payload ?? {};
}
