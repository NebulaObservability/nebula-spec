# @nebula-observability/rutp-protobuf

Browser-compatible RUTP v1 Protobuf schemas and binary codec generated from
`nebula-spec` with `protoc-gen-es`. The package version is `0.4.0-draft.0`
and the RUTP wire version is `1.0.0-draft.1`.

Use `create(RumBatchSchema, init)` from `@bufbuild/protobuf` to create a batch,
then call `encodeRumBatch` before sending it as `application/x-protobuf`.
Decode receiver acknowledgements with `decodeBatchAck`.

Do not copy generated message definitions into an SDK or service repository.
Pin and verify the matching immutable `nebula-spec` release asset instead.
