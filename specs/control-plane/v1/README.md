# Control Plane Configuration v1

This contract defines versioned RUM configuration revisions and their safe
delivery to an SDK. It deliberately does not define credentials, a management
API, or a cryptographic signature algorithm. The existing RUM configuration
document carries `key_id` and `signature`; deployments choose a verifier and
must document the exact canonicalization and key-distribution scheme before
accepting a signed document.

## Two representations

`schemas/control-plane-config-revision.schema.json` is a server-side immutable
revision record. It contains `scope`, lifecycle, and audit metadata so a
control plane can keep history, activate a revision, and create a higher
revision that rolls back to earlier content. Its `scope` is derived from an
authenticated server principal. It is not a client request format and must not
be returned to an SDK.

`schemas/control-plane-config-delivery.schema.json` is the only SDK-facing
representation:

```json
{
  "contract_version": "1.0.0-draft.1",
  "revision": 12,
  "etag": "cfg-rum-web-demo-r12",
  "status": "active",
  "document": { "...": "the existing signed RUM configuration" }
}
```

The delivery envelope intentionally has no `tenant_id`, `project_id`,
`principal_id`, audit fields, or lifecycle history. The endpoint selects a
configuration from server-side authenticated scope. Client headers, query
parameters, RUM batch fields, and Resource attributes must not select a scope.

## Revision lifecycle

Revisions are immutable and monotonically increasing within a server scope and
logical `config_id`. A newly published or rollback revision has `status:
active`; the prior active revision becomes `superseded`. A rollback never
reactivates an old revision in place: it creates a new, higher `revision` with
`lifecycle.operation: rollback` and `rollback_of_revision` set to the source
revision. The control plane emits only the current active revision.

`etag` is an opaque server-generated representation identifier. A client may
send it in `If-None-Match`; an unchanged active revision returns HTTP 304 with
no body. A newly active revision must have a different ETag. Consumers do not
parse ETags or use them for authorization.

## Document and sampling semantics

`document` is the existing `schemas/rum-config.schema.json` payload. Its
`config_version`, issue/expiry timestamps, protocol version, sampling,
privacy, upload, instrumentation, kill-switch, and signature fields retain
their existing meanings.

Sampling uses `session_rate`, `trace_rate`, and `replay_rate` in the inclusive
range `[0, 1]`; an implementation must make each decision consistently from a
stable relevant identifier. `always_keep_events` takes precedence over the
probability only after consent, privacy filtering, and kill switches have been
applied. It never authorizes collection of data that those safeguards deny.
Telemetry records continue to report the effective decision through
`rum.sampling.rate`, `rum.sampling.reason`, and `rum.sampling.priority`, and
the active document identity through `rum.sdk.config.version`.

## Safety rules

An SDK validates the delivery envelope, document compatibility, expiry, and
its deployment-provided signature verifier before atomically applying it. A
failed validation, expired document, unsupported protocol, or unavailable
endpoint leaves the last valid configuration in effect; if none exists, the
SDK uses local defaults. Remote configuration cannot weaken local consent or
the default-deny privacy policy. It may add only extra deny behavior at the
deployment layer.

Management and query authorization are separate from ingest authorization. A
configuration endpoint must not use a browser-provided tenant or project value
as a routing or authorization input.
