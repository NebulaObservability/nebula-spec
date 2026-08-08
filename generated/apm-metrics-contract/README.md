# @nebula-observability/apm-metrics-contract

Generated, immutable APM Metrics contract for Spec `0.8.0-draft.0` and
platform release `2026.08.1-mvp.0`. The bundle contains the exact 21-metric
OTLP profile, its schemas, ExponentialHistogram and explicit Histogram fixtures,
continuous cumulative export sequences, the official Go runtime `v0.69.0`
profile, negative conformance cases, and the frozen compatibility snapshot. OTLP exemplar trace/span IDs use lowercase hex;
filtered attributes are forbidden. Source Schema URLs may be empty or official
OpenTelemetry semver URLs up to the `1.43.0` normalization target.

Verify every file against `asset-manifest.json` before consuming it. Runtime
repositories must pin the matching release asset and must not copy or extend the
profile locally.
