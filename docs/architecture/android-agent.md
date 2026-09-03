# Android Agent architecture

Phase 8 adds one mobile client of the existing assistant. It is not a second assistant and does
not hold policy or execution authority.

## Module boundary

`mobile/shared` is Kotlin Multiplatform and contains only portable contracts, serialization,
typed HTTP clients, safe error categories, truth-preserving outcome mapping, capability semantics,
and retry/idempotency policy. It has Android and JVM targets.

`mobile/androidApp` contains Android-only APIs: Compose, lifecycle, ConnectivityManager, Android
Keystore, Room, WorkManager, OS permission state, and application wiring. No Android class leaks
into `shared`. The current project intentionally has two modules; further fragmentation would add
build overhead without a distinct authority or release boundary.

## Identity and authentication

The installation identifier is 192 bits from `SecureRandom`, Base64URL encoded, app-scoped, and
stored under Keystore-backed authenticated encryption. It never reads IMEI, MAC, phone number,
advertising ID, hardware serial, or Android ID. An EC P-256 key pair is also created in Android
Keystore; only its public SubjectPublicKeyInfo representation is registered, preparing a future
proof-of-possession design without claiming attestation.

Supabase-compatible password/refresh grants obtain the ordinary user session. Access and refresh
tokens plus server Device ID are encrypted separately from installation state. The backend derives
the user exclusively from the verified bearer token. Device registration accepts no `user_id` and
the returned server Device UUID becomes the `X-Device-ID` for later requests. JWT AAL information
is preserved inside the token and interpreted only by the backend. Logout cancels authenticated
work, clears Room and session material, but retains installation identity for stable re-linking.

## Conversation and network flow

The typed client provides only Identity, Conversation, Message, and certified Confirmation calls.
There is no raw completion, model/provider override, Task mutation, Memory mutation, envelope,
tool, or execution API. Requests use bearer auth, optional owned Device header, JSON validation,
finite timeouts, and safe error categories. Bodies and authorization headers are never logged.

The Compose UI lists and opens conversations, displays history, sends text, and renders server
outcomes without promoting pending states to success. A server `ACTION_WAITING_CONFIRMATION` is a
confirmation state; `ACTION_WAITING_PERMISSION` is a permission state; and
`ACTION_READY_FOR_FUTURE_EXECUTION` explicitly says no Executor performed the action.

## Connectivity, durable delivery, and process death

ConnectivityManager reports `ONLINE` only when Android reports both Internet and validation.
Missing networks are `OFFLINE`; unvalidated links are `DEGRADED`, indeterminate links are `UNKNOWN`,
and validated links are `RECOVERING` until an event-driven backend probe establishes `ONLINE`.
This is UX and scheduling evidence, never authority.

Room stores server conversation metadata, encrypted message content, and encrypted pending message
payloads. It is a delivery/cache database, not Task Engine or Memory. Each new user send creates
one operation UUID and one idempotency key. Process death, app restart, WorkManager scheduling, and
network retries reuse that identity. A new send creates a new identity. Unique Room constraints
and server Phase 7 idempotency prevent logical duplication.

WorkManager creates unique network-constrained one-time work with exponential backoff. The local
and WorkManager limits are both five attempts. There is no loop, polling, periodic work, or
foreground service. Failed mutations never become success. Cache content cannot grant permission,
change risk, confirm an action, disable Safe Mode, or authorize execution.

Manual retry never invokes network delivery. It resolves the existing durable operation and
re-enqueues the same operation ID under the same unique WorkManager name with `KEEP`. The worker is
the only caller of the repository's internal delivery boundary; the operation's idempotency key,
payload, expected conversation version, and attempt history are preserved. Repeated UI taps map to
one logical work identity and cannot create another pending operation. Scheduling awaits the
WorkManager enqueue operation so the UI reports queued only after durable registration succeeds.

## Capability and permission model

Capabilities are modeled with four independent facts:

1. Device supports capability.
2. Android OS permission is granted.
3. Assistant permission is granted server-side.
4. The specific action is authorized server-side.

All four are required for a future capability to be usable. Phase 8 declares only genuine platform
support and requests no microphone, camera, location, contacts, calendar, SMS, phone,
notifications, or accessibility permission. Future OS permission prompts must be just-in-time.

## Environments and release

Build-controlled `local`, `staging`, and `production` flavors are separate from `debug` and
`release`. Only `localDebug` can use emulator-loopback HTTP. Local release is disabled. Staging and
production configuration requires HTTPS at Gradle configuration time; release trusts system CAs
only, does not trust user-installed CAs, and does not disable certificate validation. Ordinary app
users cannot change endpoints.

## Deferred work

Realtime Voice, speech, text-to-speech, microphone streaming, Wake Word, full Phase 11 offline
conflict resolution, attestation, push sync, external executors, proactive behavior, and all
financial execution remain outside Phase 8.

## Dependency rationale

- Kotlin, coroutines, serialization, and Ktor provide portable typed contracts and asynchronous
  HTTPS without an agent framework.
- Compose, lifecycle, Room, WorkManager, and Android Core are maintained Jetpack primitives for UI,
  structured local persistence, lifecycle, and OS-scheduled durable work; standard Android APIs do
  not provide equivalent typed database/migration or durable scheduling facilities.
- OkHttp is Ktor's mature Android transport. KSP is build-time code generation for Room and is not
  shipped as application runtime code.
- Guava is not an app dependency; Room/KSP brings it onto the build classpath. Resolution pins it to
  `33.7.1-jre` because the older transitive `31.1-jre` has known OSV advisories. It is absent from
  the release APK.
- AGP's optional Unified Test Platform configurations transitively resolve Netty, Protobuf, and
  Commons IO. Central resolution keeps those build/test-only libraries on patched stable releases;
  none is an Android application runtime dependency.

Dependency locks pin transitives and the Gradle wrapper validates the distribution SHA-256. No DI,
analytics, agent, browser, voice, logging, or tracking SDK was introduced.
