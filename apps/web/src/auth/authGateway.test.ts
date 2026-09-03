import { afterEach, describe, expect, it, vi } from "vitest";

import type { RuntimeConfig } from "../config";
import { createAuthGateway } from "./authGateway";

const config: RuntimeConfig = Object.freeze({
  apiBaseUrl: "/api/v1",
  supabaseUrl: "https://project.supabase.co",
  supabaseAnonKey: "public-test-key",
  buildVersion: "0.13.0",
});

function fakeJwt() {
  return [
    btoa(JSON.stringify({ alg: "HS256", typ: "JWT" })),
    btoa(
      JSON.stringify({
        sub: "11111111-1111-4111-8111-111111111111",
        exp: 2_000_000_000,
        role: "authenticated",
      }),
    ),
    "signature",
  ].join(".");
}

afterEach(() => vi.unstubAllGlobals());

describe("Supabase authentication gateway", () => {
  it("maps a password session to a memory-only snapshot", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: fakeJwt(),
          token_type: "bearer",
          expires_in: 3600,
          expires_at: 2_000_000_000,
          refresh_token: "controlled-refresh-token",
          user: {
            id: "11111111-1111-4111-8111-111111111111",
            aud: "authenticated",
            role: "authenticated",
            email: "avery@example.com",
            app_metadata: {},
            user_metadata: {},
            created_at: "2026-09-02T12:00:00Z",
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetcher);
    const gateway = createAuthGateway(config);
    const events: string[] = [];
    const unsubscribe = gateway.subscribe((event) => events.push(event));
    await expect(
      gateway.signIn("avery@example.com", "correct-password"),
    ).resolves.toMatchObject({
      subject: "11111111-1111-4111-8111-111111111111",
      expiresAt: 2_000_000_000,
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(events).toContain("SIGNED_IN");
    unsubscribe();
  });

  it("keeps persistence disabled and has no session before sign in", async () => {
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    const gateway = createAuthGateway(config);
    await expect(gateway.getSnapshot()).resolves.toBeNull();
    expect(fetcher).not.toHaveBeenCalled();
  });
});
