import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  buildSecurityHeaders,
  isPublicSupabaseKey,
  isTrustedMutationOrigin,
  publicRuntimeConfig,
  validatedOrigin,
} from "../../server/security.mjs";

describe("production web boundary", () => {
  it("accepts an HTTPS origin", () => {
    expect(validatedOrigin("https://assistant.example", "ORIGIN")).toBe(
      "https://assistant.example",
    );
  });

  it.each([
    "http://assistant.example",
    "https://user:password@assistant.example",
    "https://assistant.example/path",
    "https://assistant.example?query=yes",
    "https://assistant.example#fragment",
  ])("rejects unsafe production origin %s", (origin) => {
    expect(() => validatedOrigin(origin, "ORIGIN")).toThrow();
  });

  it("permits HTTP only for explicit local development", () => {
    expect(
      validatedOrigin("http://127.0.0.1:8000", "ORIGIN", {
        allowLocal: true,
      }),
    ).toBe("http://127.0.0.1:8000");
    expect(() =>
      validatedOrigin("http://example.test", "ORIGIN", { allowLocal: true }),
    ).toThrow();
  });

  it("rejects named service-role secrets", () => {
    expect(isPublicSupabaseKey("service_role_secret")).toBe(false);
  });

  it("rejects JWTs carrying the service_role claim", () => {
    const payload = Buffer.from(
      JSON.stringify({ role: "service_role" }),
    ).toString("base64url");
    expect(isPublicSupabaseKey(`eyJ.${payload}.signature`)).toBe(false);
  });

  it("emits a restrictive production CSP", () => {
    const headers = buildSecurityHeaders({
      supabaseOrigin: "https://project.supabase.co",
    });
    const csp = headers["Content-Security-Policy"];
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("connect-src 'self' https://project.supabase.co");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).not.toContain("'unsafe-inline'");
    expect(csp).not.toContain("'unsafe-eval'");
  });

  it("sets clickjacking, MIME, privacy and capability headers", () => {
    const headers = buildSecurityHeaders({
      supabaseOrigin: "https://project.supabase.co",
    });
    expect(headers["X-Frame-Options"]).toBe("DENY");
    expect(headers["X-Content-Type-Options"]).toBe("nosniff");
    expect(headers["Referrer-Policy"]).toBe("no-referrer");
    expect(headers["Permissions-Policy"]).toContain("microphone=()");
    expect(headers["Permissions-Policy"]).toContain("payment=()");
  });

  it("enables HSTS only when TLS termination is asserted", () => {
    const without = buildSecurityHeaders({
      supabaseOrigin: "https://project.supabase.co",
    });
    const withHsts = buildSecurityHeaders({
      supabaseOrigin: "https://project.supabase.co",
      enableHsts: true,
    });
    expect(without).not.toHaveProperty("Strict-Transport-Security");
    expect(withHsts["Strict-Transport-Security"]).toContain("max-age=31536000");
  });

  it("requires exact same-origin mutation requests", () => {
    expect(
      isTrustedMutationOrigin(
        "https://assistant.example",
        "https://assistant.example",
      ),
    ).toBe(true);
    expect(
      isTrustedMutationOrigin(
        "https://evil.example",
        "https://assistant.example",
      ),
    ).toBe(false);
    expect(
      isTrustedMutationOrigin(undefined, "https://assistant.example"),
    ).toBe(false);
  });

  it("exposes only public runtime fields", () => {
    const config = publicRuntimeConfig({
      supabaseUrl: "https://project.supabase.co",
      supabaseAnonKey: "sb_publishable_public",
    });
    expect(config).toEqual({
      apiBaseUrl: "/api/v1",
      supabaseUrl: "https://project.supabase.co",
      supabaseAnonKey: "sb_publishable_public",
      buildVersion: "0.13.0",
    });
    expect(config).not.toHaveProperty("backendOrigin");
    expect(config).not.toHaveProperty("serviceRoleKey");
  });

  it("contains no persistent token store or unsafe HTML rendering", () => {
    const sourceRoot = resolve(import.meta.dirname, "../../src");
    const sources = [
      "main.tsx",
      "App.tsx",
      "auth/authGateway.ts",
      "session/sessionController.ts",
      "components/ChatView.tsx",
    ]
      .map((name) => readFileSync(resolve(sourceRoot, name), "utf8"))
      .join("\n");
    expect(sources).not.toMatch(/localStorage|sessionStorage|indexedDB/);
    expect(sources).not.toContain("dangerouslySetInnerHTML");
    expect(sources).not.toContain("document.cookie");
  });
});
