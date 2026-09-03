import { describe, expect, it, vi } from "vitest";

import {
  isPublicSupabaseKey,
  loadRuntimeConfig,
  parseRuntimeConfig,
} from "./config";

const valid = {
  apiBaseUrl: "/api/v1",
  supabaseUrl: "https://project.supabase.co",
  supabaseAnonKey: "public-anon-key",
  buildVersion: "0.13.0",
};

describe("runtime configuration", () => {
  it("accepts and freezes an exact HTTPS configuration", () => {
    const parsed = parseRuntimeConfig(valid, false);
    expect(parsed.supabaseUrl).toBe("https://project.supabase.co");
    expect(Object.isFrozen(parsed)).toBe(true);
  });

  it("allows loopback HTTP only when explicitly local", () => {
    expect(
      parseRuntimeConfig(
        { ...valid, supabaseUrl: "http://127.0.0.1:54321" },
        true,
      ).supabaseUrl,
    ).toBe("http://127.0.0.1:54321");
  });

  it("rejects loopback HTTP in production", () => {
    expect(() =>
      parseRuntimeConfig(
        { ...valid, supabaseUrl: "http://localhost:54321" },
        false,
      ),
    ).toThrow("HTTPS");
  });

  it("rejects non-loopback cleartext", () => {
    expect(() =>
      parseRuntimeConfig({ ...valid, supabaseUrl: "http://example.com" }, true),
    ).toThrow("HTTPS");
  });

  it.each([
    "https://user:pass@project.supabase.co",
    "https://project.supabase.co?redirect=evil",
    "https://project.supabase.co/#fragment",
  ])("rejects unsafe auth URL %s", (supabaseUrl) => {
    expect(() => parseRuntimeConfig({ ...valid, supabaseUrl }, false)).toThrow(
      "invalid",
    );
  });

  it("rejects a client-editable backend destination", () => {
    expect(() =>
      parseRuntimeConfig(
        { ...valid, apiBaseUrl: "https://evil.example" },
        false,
      ),
    ).toThrow("does not match");
  });

  it("rejects a build-version mismatch", () => {
    expect(() =>
      parseRuntimeConfig({ ...valid, buildVersion: "0.11.1" }, false),
    ).toThrow("does not match");
  });

  it("rejects unexpected authority-bearing fields", () => {
    expect(() =>
      parseRuntimeConfig({ ...valid, user_id: "forged" }, false),
    ).toThrow("unsupported field");
  });

  it("rejects named service-role material", () => {
    expect(isPublicSupabaseKey("service_role_secret_value")).toBe(false);
  });

  it("rejects a JWT carrying the service_role claim", () => {
    const encoded = btoa(JSON.stringify({ role: "service_role" })).replaceAll(
      "=",
      "",
    );
    expect(isPublicSupabaseKey(`eyJ.${encoded}.signature`)).toBe(false);
  });

  it("loads configuration without credentials, redirects, or cache", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(json(valid));
    await expect(loadRuntimeConfig(fetcher)).resolves.toMatchObject(valid);
    expect(fetcher).toHaveBeenCalledWith(
      "/config.json",
      expect.objectContaining({
        cache: "no-store",
        credentials: "omit",
        redirect: "error",
      }),
    );
  });

  it("fails closed when configuration is unavailable", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(json({}, 503));
    await expect(loadRuntimeConfig(fetcher)).rejects.toThrow("unavailable");
  });
});

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
