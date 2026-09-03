const LOOPBACK = new Set(["127.0.0.1", "localhost", "::1"]);

export function validatedOrigin(value, name, { allowLocal = false } = {}) {
  if (!value) throw new Error(`${name} is required.`);
  const url = new URL(value);
  const local =
    allowLocal && url.protocol === "http:" && LOOPBACK.has(url.hostname);
  if (url.protocol !== "https:" && !local)
    throw new Error(`${name} must use HTTPS.`);
  if (
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    url.pathname !== "/"
  ) {
    throw new Error(
      `${name} must be an origin without credentials, path, query, or fragment.`,
    );
  }
  return url.origin;
}

export function isPublicSupabaseKey(value) {
  if (!value || /service[_-]?role/i.test(value)) return false;
  if (!value.startsWith("eyJ")) return true;
  try {
    const payload = value.split(".")[1];
    if (!payload) return false;
    const parsed = JSON.parse(
      Buffer.from(payload, "base64url").toString("utf8"),
    );
    return parsed.role !== "service_role";
  } catch {
    return false;
  }
}

export function buildSecurityHeaders({ supabaseOrigin, enableHsts = false }) {
  const trustedSupabase = validatedOrigin(supabaseOrigin, "WEB_SUPABASE_URL");
  const headers = {
    "Content-Security-Policy": [
      "default-src 'self'",
      "base-uri 'none'",
      `connect-src 'self' ${trustedSupabase}`,
      "font-src 'self'",
      "form-action 'self'",
      "frame-ancestors 'none'",
      "img-src 'self' data:",
      "manifest-src 'self'",
      "object-src 'none'",
      "script-src 'self'",
      "style-src 'self'",
      "worker-src 'none'",
      "upgrade-insecure-requests",
    ].join("; "),
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Origin-Agent-Cluster": "?1",
    "Permissions-Policy":
      "camera=(), geolocation=(), microphone=(), payment=(), usb=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
  };
  if (enableHsts) {
    headers["Strict-Transport-Security"] =
      "max-age=31536000; includeSubDomains";
  }
  return Object.freeze(headers);
}

export function isTrustedMutationOrigin(requestOrigin, publicOrigin) {
  if (!requestOrigin) return false;
  try {
    return (
      new URL(requestOrigin).origin ===
      validatedOrigin(publicOrigin, "WEB_PUBLIC_ORIGIN")
    );
  } catch {
    return false;
  }
}

export function publicRuntimeConfig({ supabaseUrl, supabaseAnonKey }) {
  const origin = validatedOrigin(supabaseUrl, "WEB_SUPABASE_URL");
  if (!isPublicSupabaseKey(supabaseAnonKey)) {
    throw new Error(
      "WEB_SUPABASE_ANON_KEY must be a public anon or publishable key.",
    );
  }
  return Object.freeze({
    apiBaseUrl: "/api/v1",
    supabaseUrl: origin,
    supabaseAnonKey,
    buildVersion: "0.13.0",
  });
}
