# Web Research security model

## Threats and controls

| Threat | Control |
| --- | --- |
| SSRF and metadata access | Global-address allow policy; private, loopback, link-local, carrier-grade, documentation, multicast, reserved, unspecified, internal/local hostname, userinfo, unsafe scheme, and unsafe port rejection. |
| DNS rebinding | Every request/redirect is resolved before connection; all answers must be global; same-host address-set changes are rejected; transport connects to the validated IP. |
| Redirect escape | Relative redirects are normalized and every target repeats complete URL/DNS validation; redirect count is bounded. |
| Decompression/body abuse | `Accept-Encoding: identity`; encoded responses are rejected; content length, bytes, total bytes, media type, extraction size, and elapsed time are bounded. |
| Prompt injection | Active/hidden HTML is excluded; remaining content is tagged untrusted; synthesis has no tools/actions and cannot alter trusted policy. |
| Hallucinated citations | Model supplies evidence IDs only; server owns URLs/titles/timestamps, rejects unknown IDs and unsupported claims, and renders citation IDs into the final answer. |
| Privacy leakage | Sensitivity gate runs before outbound work; critical/sensitive content fails closed; ordinary queries are minimized/redacted; Memory and conversation history are excluded. |
| Provider abuse | Provider-neutral protocol, bounded attempts, safe typed failures, no raw errors, no runtime client/provider override, fake adapters forbidden in production. |
| Authority confusion | Existing PermissionsEngine, risk, confirmation, Safe Mode and audit chain; no Task, Executor, financial path, or model-granted authority. |
| Client XSS/navigation | React text rendering only; citations are isolated, revalidated links; no raw HTML/Markdown or scriptable schemes. |

Research rejection events store only mode, policy version, classified reason, identity references,
and the canonical capability/action. Logs and metrics do not contain questions, page text, URLs,
credentials, headers, or model output.

The default distribution cannot perform live Web Research: it has no configured search provider,
contains no search credential, and has research disabled. Enabling it is an operator action that
requires an approved adapter and separate staging validation.

