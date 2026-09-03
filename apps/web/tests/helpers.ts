import type {
  AssistantResponse,
  Conversation,
  ConversationMessage,
  Identity,
} from "../src/api/contracts";
import type {
  AuthEvent,
  AuthGateway,
  AuthSnapshot,
  MfaState,
  TotpEnrollment,
} from "../src/auth/authGateway";
import type { SessionChannel } from "../src/session/sessionController";

export const USER_ID = "11111111-1111-4111-8111-111111111111";
export const OTHER_USER_ID = "22222222-2222-4222-8222-222222222222";
export const CONVERSATION_ID = "33333333-3333-4333-8333-333333333333";

export const identity: Identity = Object.freeze({
  user_id: USER_ID,
  auth_user_id: USER_ID,
  display_name: "Avery",
  device_id: null,
  authenticated: true,
  authentication_level: "aal1",
});

export const conversation: Conversation = Object.freeze({
  id: CONVERSATION_ID,
  device_id: null,
  title: "Project notes",
  version: 1,
  created_at: "2026-09-02T12:00:00Z",
  updated_at: "2026-09-02T12:00:00Z",
  last_message_at: null,
});

export function message(
  role: "USER" | "ASSISTANT",
  overrides: Partial<ConversationMessage> = {},
): ConversationMessage {
  return Object.freeze({
    id:
      role === "USER"
        ? "44444444-4444-4444-8444-444444444444"
        : "55555555-5555-4555-8555-555555555555",
    conversation_id: CONVERSATION_ID,
    role,
    status: "COMPLETED",
    outcome: role === "ASSISTANT" ? "ANSWERED" : null,
    sequence: role === "USER" ? 1 : 2,
    content: role === "USER" ? "Hello" : "Hello, Avery.",
    sensitivity: "PRIVATE",
    orchestration_id: null,
    confirmation_request_id: null,
    memory_id: null,
    reason_code: null,
    citations: [],
    created_at: "2026-09-02T12:00:01Z",
    ...overrides,
  });
}

export function assistantResponse(
  overrides: Partial<ConversationMessage> = {},
): AssistantResponse {
  return Object.freeze({
    conversation: Object.freeze({
      ...conversation,
      version: 2,
      last_message_at: "2026-09-02T12:00:01Z",
    }),
    user_message: message("USER"),
    assistant_message: message("ASSISTANT", overrides),
  });
}

export function jsonResponse(value: unknown, status = 200): Response {
  return new Response(status === 204 ? null : JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export class FakeAuthGateway implements AuthGateway {
  snapshot: AuthSnapshot | null = Object.freeze({
    accessToken: "memory-only-token",
    expiresAt: 2_000_000_000,
    subject: USER_ID,
  });
  signInCalls = 0;
  signOutCalls = 0;
  failSignIn = false;
  failSignOut = false;
  #listener:
    ((event: AuthEvent, snapshot: AuthSnapshot | null) => void) | null = null;

  signIn(): Promise<AuthSnapshot> {
    this.signInCalls += 1;
    if (this.failSignIn || !this.snapshot)
      return Promise.reject(new Error("denied"));
    return Promise.resolve(this.snapshot);
  }

  signOut(): Promise<void> {
    this.signOutCalls += 1;
    return this.failSignOut
      ? Promise.reject(new Error("unavailable"))
      : Promise.resolve();
  }

  getSnapshot(): Promise<AuthSnapshot | null> {
    return Promise.resolve(this.snapshot);
  }

  getMfaState(): Promise<MfaState> {
    return Promise.resolve(
      Object.freeze({
        currentLevel: "aal1",
        nextLevel: "aal1",
        verifiedTotpFactorIds: Object.freeze([]),
      }),
    );
  }

  enrollTotp(): Promise<TotpEnrollment> {
    return Promise.resolve(
      Object.freeze({
        factorId: "factor-test",
        qrCode: "data:image/svg+xml,test",
        secret: "TESTSECRET",
      }),
    );
  }

  verifyTotp(): Promise<AuthSnapshot> {
    if (!this.snapshot) return Promise.reject(new Error("denied"));
    return Promise.resolve(this.snapshot);
  }

  subscribe(
    listener: (event: AuthEvent, snapshot: AuthSnapshot | null) => void,
  ): () => void {
    this.#listener = listener;
    return () => {
      this.#listener = null;
    };
  }

  emit(event: AuthEvent, snapshot: AuthSnapshot | null): void {
    this.#listener?.(event, snapshot);
  }
}

export class FakeSessionChannel implements SessionChannel {
  logoutPosts = 0;
  closed = false;
  #listener: (() => void) | null = null;

  postLogout(): void {
    this.logoutPosts += 1;
  }

  subscribe(listener: () => void): () => void {
    this.#listener = listener;
    return () => {
      this.#listener = null;
    };
  }

  remoteLogout(): void {
    this.#listener?.();
  }

  close(): void {
    this.closed = true;
  }
}
