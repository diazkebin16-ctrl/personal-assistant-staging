# Android Agent security boundary

## Authority

Cloud Identity, Memory, Permissions, Risk, Confirmation, Safe Mode, Task Engine, AI Router,
Orchestrator, conversation state, and FinancialExecutionGuard remain authoritative. Android owns
only installation identity, encrypted session/cache data, UI, connectivity evidence, durable
delivery metadata, and device-support declarations.

The client cannot create `AuthorizedActionEnvelope`, mutate Task or Memory tables, force a model or
provider, grant either OS or Assistant permission, fabricate or replay confirmation evidence, or
execute an external action. Model output, user text, intents, clipboard, files, notifications, and
cached responses are untrusted data. There are no deep links or exported receivers/services.

Financial execution is absent. `buy`, `sell`, `transfer`, `withdraw`, `deposit`, `place_order`,
leverage changes, risk increases, and generic financial execution have no client implementation,
even when the user writes a confirmation phrase.

## Secret and content storage

Android Keystore holds non-exportable AES-256-GCM keys and the non-exportable device private key.
Access token, refresh token, server Device ID, installation ID, message content, and pending
message payload are encrypted with randomized IVs and authenticated encryption. Non-sensitive
database metadata remains plaintext. Backups and device transfer are disabled. The app contains no
service-role key, provider API key, backend secret, private keystore, or production credential.

Supabase anon configuration is a public client identifier supplied at build time; it is not a
service-role secret. Passwords are sent directly over the Supabase HTTPS auth endpoint and are
never persisted or logged.

## Network and logging

Production cleartext is denied in both manifest and Network Security Configuration. TLS
verification is never replaced or disabled. Debug HTTP is restricted to local emulator targets.
The Ktor logging plugin is not installed. Network telemetry exposes only operation name,
request ID, status, latency, and high-level category; it receives no token, authorization header,
message, Memory, provider response, or raw payload.

Retries are allowed for reads or for mutations carrying their original stable idempotency
identity. Backoff and attempts are bounded. Authentication, revocation, validation, and malformed
response failures do not blind-retry. Unknown Safe Mode or permission state fails closed for
privileged actions; cached state has no authority.

WorkManager is the single durable network-delivery path. UI retries only re-enqueue the stored
operation using the same unique work name and `ExistingWorkPolicy.KEEP`; they do not call the API,
change the idempotency key, or write delivery results. This prevents a late UI result from
overwriting worker state while retaining backend idempotency as defense in depth.

## Runtime limitations

Static and JVM validation cannot certify Keystore behavior, ConnectivityManager callbacks,
WorkManager rescheduling after reboot/process death, Room encryption behavior on a real filesystem,
Compose accessibility, or packaged release behavior on a device. These require an Android emulator
or physical device. Live Supabase ownership/RLS/revocation and backend TLS require staging.
