export function validatedOrigin(
  value: string | undefined,
  name: string,
  options?: { allowLocal?: boolean },
): string;
export function isPublicSupabaseKey(value: string | undefined): boolean;
export function buildSecurityHeaders(options: {
  supabaseOrigin: string;
  enableHsts?: boolean;
}): Readonly<Record<string, string>>;
export function isTrustedMutationOrigin(
  requestOrigin: string | undefined,
  publicOrigin: string,
): boolean;
export function publicRuntimeConfig(options: {
  supabaseUrl: string | undefined;
  supabaseAnonKey: string | undefined;
}): Readonly<{
  apiBaseUrl: "/api/v1";
  supabaseUrl: string;
  supabaseAnonKey: string;
  buildVersion: "0.13.0";
}>;
