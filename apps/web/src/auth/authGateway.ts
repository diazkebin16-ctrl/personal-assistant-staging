import { createClient } from "@supabase/supabase-js";

import type { RuntimeConfig } from "../config";

export type AuthSnapshot = Readonly<{
  accessToken: string;
  expiresAt: number | null;
  subject: string;
}>;

export type AuthEvent =
  "SIGNED_IN" | "SIGNED_OUT" | "TOKEN_REFRESHED" | "USER_UPDATED";

export type AuthGateway = Readonly<{
  signIn(email: string, password: string): Promise<AuthSnapshot>;
  signOut(): Promise<void>;
  getSnapshot(): Promise<AuthSnapshot | null>;
  subscribe(
    listener: (event: AuthEvent, snapshot: AuthSnapshot | null) => void,
  ): () => void;
}>;

function snapshotFromSession(session: {
  access_token: string;
  expires_at?: number;
  user: { id: string };
}): AuthSnapshot {
  return Object.freeze({
    accessToken: session.access_token,
    expiresAt: session.expires_at ?? null,
    subject: session.user.id,
  });
}

export function createAuthGateway(config: RuntimeConfig): AuthGateway {
  const client = createClient(config.supabaseUrl, config.supabaseAnonKey, {
    auth: {
      autoRefreshToken: true,
      detectSessionInUrl: false,
      flowType: "pkce",
      persistSession: false,
    },
    global: {
      headers: {
        "X-Client-Info": `personal-assistant-web/${config.buildVersion}`,
      },
    },
  });

  return Object.freeze({
    async signIn(email, password) {
      const { data, error } = await client.auth.signInWithPassword({
        email,
        password,
      });
      if (error) throw new Error("Sign in was not accepted.");
      return snapshotFromSession(data.session);
    },
    async signOut() {
      const { error } = await client.auth.signOut({ scope: "local" });
      if (error) throw new Error("Sign out could not be completed cleanly.");
    },
    async getSnapshot() {
      const { data, error } = await client.auth.getSession();
      if (error || !data.session) return null;
      return snapshotFromSession(data.session);
    },
    subscribe(listener) {
      const { data } = client.auth.onAuthStateChange((event, session) => {
        if (
          event === "SIGNED_IN" ||
          event === "SIGNED_OUT" ||
          event === "TOKEN_REFRESHED" ||
          event === "USER_UPDATED"
        ) {
          listener(event, session ? snapshotFromSession(session) : null);
        }
      });
      return () => data.subscription.unsubscribe();
    },
  });
}
