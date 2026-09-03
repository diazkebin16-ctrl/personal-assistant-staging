import { describe, expect, it, vi } from "vitest";

import { BackendClient } from "../api/client";
import {
  assistantResponse,
  conversation,
  jsonResponse,
} from "../../tests/helpers";
import { ConversationController } from "./controller";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function setup(fetcher: typeof fetch) {
  const client = new BackendClient({
    baseUrl: "/api/v1",
    tokenProvider: () => Promise.resolve("token"),
    fetcher,
  });
  return { client, controller: new ConversationController(client) };
}

describe("conversation concurrency controller", () => {
  it("loads server messages when a conversation opens", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse([]));
    const { controller } = setup(fetcher);
    await controller.select(conversation);
    expect(controller.state.selectedId).toBe(conversation.id);
    expect(fetcher.mock.calls[0]?.[0]).toContain("/messages?limit=200");
  });

  it("deduplicates double submit into one logical request", async () => {
    const send = deferred<Response>();
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockImplementationOnce(() => send.promise);
    const { controller } = setup(fetcher);
    await controller.select(conversation);
    const first = controller.send("hello");
    const second = controller.send("hello");
    expect(first).toBe(second);
    send.resolve(jsonResponse(assistantResponse()));
    await first;
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("does not render a late response into another conversation", async () => {
    const send = deferred<Response>();
    const other = {
      ...conversation,
      id: "77777777-7777-4777-8777-777777777777",
      title: "Other",
    };
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockImplementationOnce(() => send.promise)
      .mockResolvedValueOnce(jsonResponse([]));
    const { controller } = setup(fetcher);
    await controller.select(conversation);
    const pending = controller.send("hello");
    await controller.select(other);
    send.resolve(jsonResponse(assistantResponse()));
    await pending;
    expect(controller.state.selectedId).toBe(other.id);
    expect(controller.state.messages).toEqual([]);
  });

  it("preserves logical idempotency across explicit retry", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValueOnce(jsonResponse(assistantResponse()));
    const { controller } = setup(fetcher);
    await controller.select(conversation);
    await expect(controller.send("retry me")).rejects.toBeDefined();
    const firstRawBody = fetcher.mock.calls[1]?.[1]?.body;
    expect(typeof firstRawBody).toBe("string");
    const firstBody = JSON.parse(
      typeof firstRawBody === "string" ? firstRawBody : "",
    ) as { idempotency_key: string };
    await controller.retry();
    const retryRawBody = fetcher.mock.calls[2]?.[1]?.body;
    expect(typeof retryRawBody).toBe("string");
    const retryBody = JSON.parse(
      typeof retryRawBody === "string" ? retryRawBody : "",
    ) as { idempotency_key: string };
    expect(retryBody.idempotency_key).toBe(firstBody.idempotency_key);
  });

  it("creates a new idempotency identity after completion", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse(assistantResponse()))
      .mockResolvedValueOnce(jsonResponse(assistantResponse()));
    const { controller } = setup(fetcher);
    await controller.select(conversation);
    await controller.send("first");
    await controller.send("second");
    const firstRawBody = fetcher.mock.calls[1]?.[1]?.body;
    const secondRawBody = fetcher.mock.calls[2]?.[1]?.body;
    expect(typeof firstRawBody).toBe("string");
    expect(typeof secondRawBody).toBe("string");
    const first = JSON.parse(
      typeof firstRawBody === "string" ? firstRawBody : "",
    ) as { idempotency_key: string };
    const second = JSON.parse(
      typeof secondRawBody === "string" ? secondRawBody : "",
    ) as { idempotency_key: string };
    expect(second.idempotency_key).not.toBe(first.idempotency_key);
  });

  it("does not queue or send while offline", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse([]));
    const { controller } = setup(fetcher);
    await controller.select(conversation);
    await expect(controller.send("offline", false)).rejects.toMatchObject({
      category: "NETWORK_OFFLINE",
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(controller.state.pending).toBeNull();
  });

  it("clear removes all account-bound state", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse([]));
    const { controller } = setup(fetcher);
    await controller.select(conversation);
    controller.clear();
    expect(controller.state).toEqual({
      selectedId: null,
      conversation: null,
      messages: [],
      pending: null,
      error: null,
    });
  });
});
