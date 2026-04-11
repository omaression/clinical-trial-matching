import "server-only";

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

export function getFrontendConfig() {
  return {
    apiBaseUrl: requireEnv("CTM_FRONTEND_API_BASE_URL").replace(/\/$/, ""),
    apiKey: process.env.CTM_FRONTEND_API_KEY ?? ""
  };
}
