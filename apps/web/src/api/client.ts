import type {
  ApiErrorEnvelope,
  AssistantResponse,
  Confirmation,
  Conversation,
  ConversationMessage,
  Identity,
  MemoryRecord,
  Permission,
  UUID,
} from "./contracts";
import { ApiError, classifyHttpError, classifyTransportError } from "./errors";
import type { WebObserver } from "../observability/observer";
import { safeObservation, silentObserver } from "../observability/observer";

export type TokenProvider = () => Promise<string | null>;

export type LogicalMessage = Readonly<{
  conversationId: UUID;
  content: string;
  expectedVersion: number;
  idempotencyKey: UUID;
}>;

export type ExplicitMemoryInput = Readonly<{
  memoryClass:
    | "OPERATIONAL"
    | "PERSISTENT_PREFERENCE"
    | "HISTORICAL_DECISION"
    | "DISCARDABLE";
  content: string;
  subject?: string;
}>;

type RequestOptions = Readonly<{
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal | undefined;
  conversationId?: UUID;
}>;

const READ_RETRY_LIMIT = 1;

export class BackendClient {
  readonly #baseUrl: "/api/v1";
  readonly #tokenProvider: TokenProvider;
  readonly #fetcher: typeof fetch;
  readonly #observer: WebObserver;
  readonly #onAuthenticationRequired: () => void;
  readonly #controllers = new Set<AbortController>();

  constructor(options: {
    baseUrl: "/api/v1";
    tokenProvider: TokenProvider;
    fetcher?: typeof fetch;
    observer?: WebObserver;
    onAuthenticationRequired?: () => void;
  }) {
    this.#baseUrl = options.baseUrl;
    this.#tokenProvider = options.tokenProvider;
    this.#fetcher = options.fetcher ?? globalThis.fetch.bind(globalThis);
    this.#observer = options.observer ?? silentObserver;
    this.#onAuthenticationRequired =
      options.onAuthenticationRequired ?? (() => undefined);
  }

  abortAll(): void {
    for (const controller of this.#controllers) controller.abort();
    this.#controllers.clear();
  }

  createLogicalMessage(
    conversation: Conversation,
    content: string,
    idempotencyKey: UUID = crypto.randomUUID(),
  ): LogicalMessage {
    const normalized = content.trim();
    if (!normalized || normalized.length > 50_000) {
      throw new ApiError(
        "VALIDATION_ERROR",
        "Enter a message between 1 and 50,000 characters.",
      );
    }
    return Object.freeze({
      conversationId: conversation.id,
      content: normalized,
      expectedVersion: conversation.version,
      idempotencyKey,
    });
  }

  currentIdentity(signal?: AbortSignal): Promise<Identity> {
    return this.#request("/me", { signal });
  }

  listConversations(signal?: AbortSignal): Promise<readonly Conversation[]> {
    return this.#request("/conversations?limit=100&offset=0", { signal });
  }

  createConversation(
    title?: string,
    signal?: AbortSignal,
  ): Promise<Conversation> {
    const normalized = title?.trim();
    return this.#request("/conversations", {
      method: "POST",
      body: normalized ? { title: normalized.slice(0, 200) } : {},
      signal,
    });
  }

  getConversation(
    conversationId: UUID,
    signal?: AbortSignal,
  ): Promise<Conversation> {
    return this.#request(
      `/conversations/${encodeURIComponent(conversationId)}`,
      { signal },
    );
  }

  listMessages(
    conversationId: UUID,
    signal?: AbortSignal,
  ): Promise<readonly ConversationMessage[]> {
    return this.#request(
      `/conversations/${encodeURIComponent(conversationId)}/messages?limit=200&offset=0`,
      { signal, conversationId },
    );
  }

  sendLogicalMessage(
    message: LogicalMessage,
    signal?: AbortSignal,
  ): Promise<AssistantResponse> {
    return this.#request(
      `/conversations/${encodeURIComponent(message.conversationId)}/messages`,
      {
        method: "POST",
        body: {
          content: message.content,
          idempotency_key: message.idempotencyKey,
          expected_version: message.expectedVersion,
          use_memory_context: true,
          memory_items_per_category: 3,
          requested_output_tokens: 1024,
        },
        signal,
        conversationId: message.conversationId,
      },
    );
  }

  listMemories(signal?: AbortSignal): Promise<readonly MemoryRecord[]> {
    return this.#request("/memories?status=ACTIVE&limit=100&offset=0", {
      signal,
    });
  }

  createMemory(
    input: ExplicitMemoryInput,
    signal?: AbortSignal,
  ): Promise<MemoryRecord> {
    const content = input.content.trim();
    if (!content || content.length > 16_000) {
      throw new ApiError(
        "VALIDATION_ERROR",
        "Memory content must be between 1 and 16,000 characters.",
      );
    }
    return this.#request("/memories", {
      method: "POST",
      body: {
        memory_class: input.memoryClass,
        content,
        ...(input.subject?.trim()
          ? { subject: input.subject.trim().slice(0, 200) }
          : {}),
        source_type: "USER_EXPLICIT",
      },
      signal,
    });
  }

  archiveMemory(
    memory: MemoryRecord,
    confirmationId?: UUID,
    signal?: AbortSignal,
  ): Promise<MemoryRecord> {
    return this.#request(`/memories/${encodeURIComponent(memory.id)}/archive`, {
      method: "POST",
      body: {
        expected_version: memory.version,
        ...(confirmationId ? { confirmation_id: confirmationId } : {}),
      },
      signal,
    });
  }

  async deleteMemory(
    memory: MemoryRecord,
    confirmationId?: UUID,
    signal?: AbortSignal,
  ): Promise<void> {
    const query = new URLSearchParams({
      expected_version: String(memory.version),
    });
    if (confirmationId) query.set("confirmation_id", confirmationId);
    await this.#request<undefined>(
      `/memories/${encodeURIComponent(memory.id)}?${query.toString()}`,
      {
        method: "DELETE",
        signal,
      },
    );
  }

  listPermissions(signal?: AbortSignal): Promise<readonly Permission[]> {
    return this.#request("/permissions", { signal });
  }

  grantMemoryPermission(
    capabilityKey: "memory.read" | "memory.write",
    operations: readonly string[],
    signal?: AbortSignal,
  ): Promise<Permission> {
    if (operations.length === 0) {
      return Promise.reject(
        new ApiError("VALIDATION_ERROR", "Permission operations are required."),
      );
    }
    return this.#request("/permissions/grant", {
      method: "POST",
      body: {
        capability_key: capabilityKey,
        scope: {
          resource_type: "memory",
          operations,
        },
        confirmation_policy: "NEVER",
        auto_execute: false,
        reason: "User explicitly enabled memory access from the web client.",
      },
      signal,
    });
  }

  grantMemoryDeletePermission(
    signal?: AbortSignal,
  ): Promise<Permission> {
    return this.#request("/permissions/grant", {
      method: "POST",
      body: {
        capability_key: "memory.delete",
        scope: {
          resource_type: "memory",
          operations: ["delete"],
        },
        confirmation_policy: "EVERY_TIME",
        auto_execute: false,
        reason: "User explicitly enabled privacy deletion from the web client.",
      },
      signal,
    });
  }

  approveConfirmation(
    confirmationId: UUID,
    signal?: AbortSignal,
  ): Promise<Confirmation> {
    return this.#request(
      `/confirmations/${encodeURIComponent(confirmationId)}/approve`,
      {
        method: "POST",
        body: {},
        signal,
      },
    );
  }

  rejectConfirmation(
    confirmationId: UUID,
    signal?: AbortSignal,
  ): Promise<Confirmation> {
    return this.#request(
      `/confirmations/${encodeURIComponent(confirmationId)}/reject`,
      {
        method: "POST",
        body: {},
        signal,
      },
    );
  }

  async #request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    if (!path.startsWith("/") || path.startsWith("//") || path.includes("\\")) {
      throw new ApiError("VALIDATION_ERROR", "The API route is invalid.");
    }
    const method = options.method ?? "GET";
    const maxAttempts = method === "GET" ? READ_RETRY_LIMIT + 1 : 1;
    let attempt = 0;
    while (attempt < maxAttempts) {
      try {
        return await this.#attempt<T>(path, options, attempt);
      } catch (error) {
        const classified = classifyTransportError(error);
        const retryableRead =
          method === "GET" &&
          attempt + 1 < maxAttempts &&
          (classified.category === "SERVER_UNAVAILABLE" ||
            classified.category === "TIMEOUT");
        if (!retryableRead) throw classified;
        attempt += 1;
      }
    }
    throw new ApiError("INTERNAL_ERROR", "The request could not be completed.");
  }

  async #attempt<T>(
    path: string,
    options: RequestOptions,
    retryCount: number,
  ): Promise<T> {
    const token = await this.#tokenProvider();
    if (!token) {
      this.#onAuthenticationRequired();
      throw new ApiError(
        "AUTH_REQUIRED",
        "Your session has expired. Sign in again.",
      );
    }
    const controller = new AbortController();
    this.#controllers.add(controller);
    const forwardAbort = () => controller.abort();
    options.signal?.addEventListener("abort", forwardAbort, { once: true });
    const timeout = globalThis.setTimeout(() => controller.abort(), 15_000);
    const requestId = crypto.randomUUID();
    const started = performance.now();
    let statusCategory = "transport_error";
    try {
      const response = await this.#fetcher(`${this.#baseUrl}${path}`, {
        method: options.method ?? "GET",
        credentials: "omit",
        redirect: "error",
        cache: "no-store",
        headers: {
          Accept: "application/json",
          Authorization: `Bearer ${token}`,
          "X-Request-ID": requestId,
          ...(options.body === undefined
            ? {}
            : { "Content-Type": "application/json" }),
        },
        ...(options.body === undefined
          ? {}
          : { body: JSON.stringify(options.body) }),
        signal: controller.signal,
      });
      statusCategory = response.ok
        ? "success"
        : `http_${response.status.toString()}`;
      if (!response.ok) {
        let body: ApiErrorEnvelope = {};
        try {
          body = (await response.json()) as ApiErrorEnvelope;
        } catch {
          body = {};
        }
        const error = classifyHttpError(response.status, body);
        if (error.category === "AUTH_REQUIRED")
          this.#onAuthenticationRequired();
        throw error;
      }
      if (response.status === 204) return undefined as T;
      return (await response.json()) as T;
    } finally {
      globalThis.clearTimeout(timeout);
      options.signal?.removeEventListener("abort", forwardAbort);
      this.#controllers.delete(controller);
      this.#observer(
        safeObservation({
          requestId,
          route: path.split("?")[0] ?? path,
          latencyMs: Math.max(0, performance.now() - started),
          statusCategory,
          retryCount,
          buildVersion: "0.13.0",
          ...(options.conversationId
            ? { conversationId: options.conversationId }
            : {}),
        }),
      );
    }
  }
}
