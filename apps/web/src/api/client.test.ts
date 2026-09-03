import { describe, expect, it, vi } from "vitest";

import {
  assistantResponse,
  conversation,
  jsonResponse,
} from "../../tests/helpers";
import { BackendClient } from "./client";
import { ApiError } from "./errors";

function clientWith(
  fetcher: typeof fetch,
  options: { token?: string | null; onAuth?: () => void } = {},
) {
  return new BackendClient({
    baseUrl: "/api/v1",
    tokenProvider: () =>
      Promise.resolve(
        "token" in options ? (options.token ?? null) : "memory-token",
      ),
    fetcher,
    ...(options.onAuth ? { onAuthenticationRequired: options.onAuth } : {}),
  });
}

describe("typed backend client", () => {
  it("binds the host fetch receiver before native browser transport", async () => {
    let receiverIsGlobal = false;
    const hostFetch = function (this: unknown): Promise<Response> {
      receiverIsGlobal = this === globalThis;
      return Promise.resolve(jsonResponse([]));
    } as typeof fetch;
    vi.stubGlobal("fetch", hostFetch);
    try {
      await new BackendClient({
        baseUrl: "/api/v1",
        tokenProvider: () => Promise.resolve("memory-token"),
      }).listConversations();
      expect(receiverIsGlobal).toBe(true);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("sends bearer auth without browser credentials", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse([]));
    await clientWith(fetcher).listConversations();
    const init = fetcher.mock.calls[0]?.[1];
    expect(new Headers(init?.headers).get("Authorization")).toBe(
      "Bearer memory-token",
    );
    expect(init?.credentials).toBe("omit");
  });

  it("constructs an exact message body without browser authority fields", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse(assistantResponse()));
    const client = clientWith(fetcher);
    const logical = client.createLogicalMessage(
      conversation,
      " Hello ",
      "66666666-6666-4666-8666-666666666666",
    );
    await client.sendLogicalMessage(logical);
    const rawBody = fetcher.mock.calls[0]?.[1]?.body;
    expect(typeof rawBody).toBe("string");
    const body = JSON.parse(
      typeof rawBody === "string" ? rawBody : "",
    ) as Record<string, unknown>;
    expect(body).toEqual({
      content: "Hello",
      idempotency_key: "66666666-6666-4666-8666-666666666666",
      expected_version: 1,
      use_memory_context: true,
      memory_items_per_category: 3,
      requested_output_tokens: 1024,
    });
    expect(body).not.toHaveProperty("user_id");
    expect(body).not.toHaveProperty("model");
    expect(body).not.toHaveProperty("provider");
    expect(body).not.toHaveProperty("sensitivity");
    expect(body).not.toHaveProperty("safe_mode");
  });

  it("creates a new identity for each new logical message", () => {
    const client = clientWith(vi.fn<typeof fetch>());
    expect(
      client.createLogicalMessage(conversation, "one").idempotencyKey,
    ).not.toBe(client.createLogicalMessage(conversation, "two").idempotencyKey);
  });

  it("rejects blank messages before transport", () => {
    const client = clientWith(vi.fn<typeof fetch>());
    expect(() => client.createLogicalMessage(conversation, "   ")).toThrow(
      ApiError,
    );
  });

  it("retries a failed read only once", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError("network"))
      .mockResolvedValueOnce(jsonResponse([]));
    await expect(clientWith(fetcher).listConversations()).resolves.toEqual([]);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("does not automatically retry a mutation", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        jsonResponse({ error: { code: "DATABASE_UNAVAILABLE" } }, 503),
      );
    await expect(
      clientWith(fetcher).createConversation(),
    ).rejects.toMatchObject({
      category: "SERVER_UNAVAILABLE",
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("does not retry permanent 403 responses", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        jsonResponse({ error: { code: "RISK_POLICY_DENIED" } }, 403),
      );
    await expect(clientWith(fetcher).listPermissions()).rejects.toMatchObject({
      category: "FORBIDDEN",
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("expires the session once on 401 without retry", async () => {
    const onAuth = vi.fn();
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        jsonResponse({ error: { code: "EXPIRED_TOKEN" } }, 401),
      );
    await expect(
      clientWith(fetcher, { onAuth }).currentIdentity(),
    ).rejects.toMatchObject({
      category: "AUTH_REQUIRED",
    });
    expect(onAuth).toHaveBeenCalledTimes(1);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("blocks before transport when no session token exists", async () => {
    const onAuth = vi.fn();
    const fetcher = vi.fn<typeof fetch>();
    await expect(
      clientWith(fetcher, { token: null, onAuth }).listConversations(),
    ).rejects.toMatchObject({
      category: "AUTH_REQUIRED",
    });
    expect(fetcher).not.toHaveBeenCalled();
    expect(onAuth).toHaveBeenCalledTimes(1);
  });

  it("does not send sensitivity or provenance authority when saving Memory", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse({ id: "memory" }));
    await clientWith(fetcher).createMemory({
      memoryClass: "PERSISTENT_PREFERENCE",
      content: "Use concise answers",
    });
    const rawBody = fetcher.mock.calls[0]?.[1]?.body;
    expect(typeof rawBody).toBe("string");
    const body = JSON.parse(
      typeof rawBody === "string" ? rawBody : "",
    ) as Record<string, unknown>;
    expect(body).toEqual({
      memory_class: "PERSISTENT_PREFERENCE",
      content: "Use concise answers",
      source_type: "USER_EXPLICIT",
    });
    expect(body).not.toHaveProperty("user_id");
    expect(body).not.toHaveProperty("confidence");
    expect(body).not.toHaveProperty("sensitivity");
  });

  it("grants memory permission only through the canonical server endpoint", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse({ id: "permission" }));

    await clientWith(fetcher).grantMemoryPermission("memory.read", ["read"]);

    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/permissions/grant");

    const rawBody = fetcher.mock.calls[0]?.[1]?.body;
    expect(typeof rawBody).toBe("string");

    const body = JSON.parse(
      typeof rawBody === "string" ? rawBody : "",
    ) as Record<string, unknown>;

    expect(body).toEqual({
      capability_key: "memory.read",
      scope: {
        resource_type: "memory",
        operations: ["read"],
      },
      confirmation_policy: "NEVER",
      auto_execute: false,
      reason: "User explicitly enabled memory access from the web client.",
    });

    expect(body).not.toHaveProperty("user_id");
    expect(body).not.toHaveProperty("authentication_level");
    expect(body).not.toHaveProperty("grant_source");
    expect(body).not.toHaveProperty("permission_id");
  });

  it("grants memory deletion separately with confirmation on every use", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse({ id: "permission-delete" }));

    await clientWith(fetcher).grantMemoryDeletePermission();

    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/permissions/grant");

    const rawBody = fetcher.mock.calls[0]?.[1]?.body;
    expect(typeof rawBody).toBe("string");

    const body = JSON.parse(
      typeof rawBody === "string" ? rawBody : "",
    ) as Record<string, unknown>;

    expect(body).toEqual({
      capability_key: "memory.delete",
      scope: {
        resource_type: "memory",
        operations: ["delete"],
      },
      confirmation_policy: "EVERY_TIME",
      auto_execute: false,
      reason: "User explicitly enabled privacy deletion from the web client.",
    });

    expect(body).not.toHaveProperty("authentication_level");
    expect(body).not.toHaveProperty("confirmation_id");
  });

  it("uses the canonical confirmation routes without local evidence", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse({ status: "APPROVED" }));
    await clientWith(fetcher).approveConfirmation("server-id");
    expect(fetcher.mock.calls[0]?.[0]).toBe(
      "/api/v1/confirmations/server-id/approve",
    );
    expect(fetcher.mock.calls[0]?.[1]?.body).toBe("{}");
  });

  it("treats a 204 Memory deletion as success", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse(null, 204));
    const memory = { id: "memory", version: 4 } as never;
    await expect(
      clientWith(fetcher).deleteMemory(memory),
    ).resolves.toBeUndefined();
  });

  it("never includes content or auth tokens in observations", async () => {
    const observer = vi.fn();
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse(assistantResponse()));
    const client = new BackendClient({
      baseUrl: "/api/v1",
      tokenProvider: () => Promise.resolve("highly-sensitive-token"),
      fetcher,
      observer,
    });
    await client.sendLogicalMessage(
      client.createLogicalMessage(conversation, "private conversation content"),
    );
    const serialized = JSON.stringify(observer.mock.calls);
    expect(serialized).not.toContain("private conversation content");
    expect(serialized).not.toContain("highly-sensitive-token");
    expect(observer).toHaveBeenCalledWith(
      expect.objectContaining({ conversationId: conversation.id }),
    );
  });
});
