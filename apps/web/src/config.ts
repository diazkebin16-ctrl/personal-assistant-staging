export type RuntimeConfig = Readonly<{
  apiBaseUrl: "/api/v1";
  supabaseUrl: string;
  supabaseAnonKey: string;
  buildVersion: "0.13.0";
}>;

const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1"]);

function objectValue(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("Public web configuration is invalid.");
  }
  return value as Record<string, unknown>;
}

export function isPublicSupabaseKey(value: string): boolean {
  if (!value || /service[_-]?role/i.test(value)) return false;
  if (!value.startsWith("eyJ")) return true;
  try {
    const payload = value.split(".")[1];
    if (!payload) return false;
    const normalized = payload.replaceAll("-", "+").replaceAll("_", "/");
    const parsed = JSON.parse(atob(normalized)) as { role?: unknown };
    return parsed.role !== "service_role";
  } catch {
    return false;
  }
}

export function parseRuntimeConfig(
  value: unknown,
  allowLocal = import.meta.env.DEV,
): RuntimeConfig {
  const input = objectValue(value);
  const allowed = new Set([
    "apiBaseUrl",
    "supabaseUrl",
    "supabaseAnonKey",
    "buildVersion",
  ]);
  if (Object.keys(input).some((key) => !allowed.has(key))) {
    throw new Error("Public web configuration contains an unsupported field.");
  }
  if (input.apiBaseUrl !== "/api/v1" || input.buildVersion !== "0.13.0") {
    throw new Error("Public web configuration does not match this build.");
  }
  if (
    typeof input.supabaseUrl !== "string" ||
    typeof input.supabaseAnonKey !== "string"
  ) {
    throw new Error("Public authentication configuration is invalid.");
  }
  const url = new URL(input.supabaseUrl);
  const localAllowed =
    allowLocal && url.protocol === "http:" && LOOPBACK_HOSTS.has(url.hostname);
  if (url.protocol !== "https:" && !localAllowed) {
    throw new Error("Authentication configuration must use HTTPS.");
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new Error("Authentication origin is invalid.");
  }
  if (!isPublicSupabaseKey(input.supabaseAnonKey)) {
    throw new Error("Only a public Supabase key is accepted.");
  }
  return Object.freeze({
    apiBaseUrl: "/api/v1",
    supabaseUrl: url.origin,
    supabaseAnonKey: input.supabaseAnonKey,
    buildVersion: "0.13.0",
  });
}

export async function loadRuntimeConfig(
  fetcher: typeof fetch = fetch,
): Promise<RuntimeConfig> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), 5_000);
  try {
    const response = await fetcher("/config.json", {
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      signal: controller.signal,
    });
    if (!response.ok)
      throw new Error("Public web configuration is unavailable.");
    return parseRuntimeConfig(await response.json());
  } finally {
    globalThis.clearTimeout(timeout);
  }
}
