import { createClient } from "@supabase/supabase-js";

import type { RuntimeConfig } from "../config";

export type AuthSnapshot = Readonly<{
  accessToken: string;
  expiresAt: number | null;
  subject: string;
}>;

export type AuthEvent =
  "SIGNED_IN" | "SIGNED_OUT" | "TOKEN_REFRESHED" | "USER_UPDATED";

export type MfaState = Readonly<{
  currentLevel: "aal1" | "aal2" | null;
  nextLevel: "aal1" | "aal2" | null;
  verifiedTotpFactorIds: readonly string[];
}>;

export type TotpEnrollment = Readonly<{
  factorId: string;
  qrCode: string;
  secret: string;
}>;

export type AuthGateway = Readonly<{
  signIn(email: string, password: string): Promise<AuthSnapshot>;
  signOut(): Promise<void>;
  getSnapshot(): Promise<AuthSnapshot | null>;
  getMfaState(): Promise<MfaState>;
  enrollTotp(): Promise<TotpEnrollment>;
  verifyTotp(factorId: string, code: string): Promise<AuthSnapshot>;
  subscribe(
    listener: (event: AuthEvent, snapshot: AuthSnapshot | null) => void,
  ): () => void;
}>;

function normalizeAal(value: string | null): "aal1" | "aal2" | null {
  if (value === "aal1" || value === "aal2") return value;
  return null;
}

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
    async signIn(email: string, password: string) {
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
    async getMfaState() {
      const [assurance, factors] = await Promise.all([
        client.auth.mfa.getAuthenticatorAssuranceLevel(),
        client.auth.mfa.listFactors(),
      ]);
      if (assurance.error || factors.error) {
        throw new Error("MFA state is unavailable.");
      }
      return Object.freeze({
        currentLevel: normalizeAal(assurance.data.currentLevel),
        nextLevel: normalizeAal(assurance.data.nextLevel),
        verifiedTotpFactorIds: Object.freeze(
          factors.data.totp
            .filter((factor) => factor.status === "verified")
            .map((factor) => factor.id),
        ),
      });
    },
    async enrollTotp() {
      const { data, error } = await client.auth.mfa.enroll({
        factorType: "totp",
        friendlyName: "Personal Assistant",
      });
      if (error) throw new Error("MFA enrollment could not be started.");
      return Object.freeze({
        factorId: data.id,
        qrCode: data.totp.qr_code,
        secret: data.totp.secret,
      });
    },
    async verifyTotp(factorId: string, code: string) {
      const normalized = code.trim();
      if (!factorId || !/^[0-9]{6,8}$/.test(normalized)) {
        throw new Error("Enter a valid authenticator code.");
      }
      const challenge = await client.auth.mfa.challenge({ factorId });
      if (challenge.error) throw new Error("MFA challenge could not be created.");
      const verified = await client.auth.mfa.verify({
        factorId,
        challengeId: challenge.data.id,
        code: normalized,
      });
      if (verified.error) throw new Error("Authenticator code was not accepted.");
      const { data, error } = await client.auth.getSession();
      if (error || !data.session) {
        throw new Error("The strengthened session is unavailable.");
      }
      return snapshotFromSession(data.session);
    },
    subscribe(
      listener: (event: AuthEvent, snapshot: AuthSnapshot | null) => void,
    ) {
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
