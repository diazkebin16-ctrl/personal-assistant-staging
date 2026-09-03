import type { Identity } from "../api/contracts";
import type {
  AuthGateway,
  AuthSnapshot,
  MfaState,
  TotpEnrollment,
} from "../auth/authGateway";

export type SessionStatus =
  | "SIGNED_OUT"
  | "SIGNING_IN"
  | "VALIDATING"
  | "AUTHENTICATED"
  | "EXPIRED"
  | "ERROR";

export type SessionState = Readonly<{
  status: SessionStatus;
  identity: Identity | null;
  message: string | null;
}>;

export type SessionChannel = Readonly<{
  postLogout(): void;
  subscribe(listener: () => void): () => void;
  close(): void;
}>;

function browserSessionChannel(): SessionChannel {
  if (!("BroadcastChannel" in globalThis)) {
    return Object.freeze({
      postLogout: () => undefined,
      subscribe: () => () => undefined,
      close: () => undefined,
    });
  }
  const channel = new BroadcastChannel("personal-assistant.session.v1");
  return Object.freeze({
    postLogout: () => channel.postMessage({ type: "LOGOUT", version: 1 }),
    subscribe(listener) {
      const handler = (event: MessageEvent<unknown>) => {
        if (
          typeof event.data === "object" &&
          event.data !== null &&
          "type" in event.data &&
          event.data.type === "LOGOUT"
        ) {
          listener();
        }
      };
      channel.addEventListener("message", handler);
      return () => channel.removeEventListener("message", handler);
    },
    close: () => channel.close(),
  });
}

export class SessionController {
  readonly #auth: AuthGateway;
  readonly #channel: SessionChannel;
  readonly #onClear: () => void;
  readonly #listeners = new Set<(state: SessionState) => void>();
  #state: SessionState = Object.freeze({
    status: "SIGNED_OUT",
    identity: null,
    message: null,
  });
  #snapshot: AuthSnapshot | null = null;
  #unsubscribeAuth: () => void;
  #unsubscribeChannel: () => void;

  constructor(
    auth: AuthGateway,
    options: { channel?: SessionChannel; onClear?: () => void } = {},
  ) {
    this.#auth = auth;
    this.#channel = options.channel ?? browserSessionChannel();
    this.#onClear = options.onClear ?? (() => undefined);
    this.#unsubscribeAuth = auth.subscribe((event, snapshot) => {
      if (event === "TOKEN_REFRESHED" && snapshot && this.#snapshot)
        this.#snapshot = snapshot;
      if (event === "SIGNED_OUT") this.#clear("SIGNED_OUT", null);
    });
    this.#unsubscribeChannel = this.#channel.subscribe(() => {
      void this.#remoteLogout();
    });
  }

  get state(): SessionState {
    return this.#state;
  }

  subscribe(listener: (state: SessionState) => void): () => void {
    this.#listeners.add(listener);
    listener(this.#state);
    return () => this.#listeners.delete(listener);
  }

  async getToken(): Promise<string | null> {
    const current = this.#snapshot ?? (await this.#auth.getSnapshot());
    if (!current) return null;
    this.#snapshot = current;
    return current.accessToken;
  }

  getMfaState(): Promise<MfaState> {
    return this.#auth.getMfaState();
  }

  enrollTotp(): Promise<TotpEnrollment> {
    return this.#auth.enrollTotp();
  }

  async verifyTotp(factorId: string, code: string): Promise<void> {
    this.#snapshot = await this.#auth.verifyTotp(factorId, code);
  }

  async signIn(email: string, password: string): Promise<void> {
    this.#set({ status: "SIGNING_IN", identity: null, message: null });
    try {
      this.#snapshot = await this.#auth.signIn(email.trim(), password);
      this.#set({ status: "VALIDATING", identity: null, message: null });
    } catch {
      this.#snapshot = null;
      this.#set({
        status: "ERROR",
        identity: null,
        message: "Sign in was not accepted.",
      });
      throw new Error("Sign in was not accepted.");
    }
  }

  acceptIdentity(identity: Identity): void {
    if (
      !this.#snapshot ||
      !identity.authenticated ||
      identity.auth_user_id !== this.#snapshot.subject
    ) {
      this.expire();
      throw new Error(
        "Authenticated identity did not match the server session.",
      );
    }
    this.#set({ status: "AUTHENTICATED", identity, message: null });
  }

  expire(): void {
    this.#clear("EXPIRED", "Your session has expired. Sign in again.");
  }

  async logout(): Promise<void> {
    let failure = false;
    try {
      await this.#auth.signOut();
    } catch {
      failure = true;
    } finally {
      this.#channel.postLogout();
      this.#clear("SIGNED_OUT", null);
    }
    if (failure)
      throw new Error("Remote sign out failed; local session was cleared.");
  }

  dispose(): void {
    this.#unsubscribeAuth();
    this.#unsubscribeChannel();
    this.#channel.close();
    this.#listeners.clear();
    this.#snapshot = null;
  }

  async #remoteLogout(): Promise<void> {
    try {
      await this.#auth.signOut();
    } catch {
      // Local isolation is mandatory even when the provider is unavailable.
    } finally {
      this.#clear("SIGNED_OUT", null);
    }
  }

  #clear(status: "SIGNED_OUT" | "EXPIRED", message: string | null): void {
    this.#snapshot = null;
    this.#onClear();
    this.#set({ status, identity: null, message });
  }

  #set(state: SessionState): void {
    this.#state = Object.freeze(state);
    for (const listener of this.#listeners) listener(this.#state);
  }
}
