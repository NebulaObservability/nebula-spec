# @nebula-observability/rutp-protobuf

Browser-compatible RUTP v1 Protobuf schemas and binary codec generated from
`nebula-spec` with `protoc-gen-es`. The package version is `0.7.0-draft.0`
and the RUTP wire version is `1.0.0-draft.1`.

Import `SpecVersion` and `ProtocolVersion` from the package root. Use
`ProtocolVersion` when constructing RUTP batches and signed configurations so
the wire value stays aligned with the released codec.

Use `create(RumBatchSchema, init)` from `@bufbuild/protobuf` to create a batch,
then call `encodeRumBatch` before sending it as `application/x-protobuf`.
Decode receiver acknowledgements with `decodeBatchAck`.

Do not copy generated message definitions into an SDK or service repository.
Pin and verify the matching immutable `nebula-spec` release asset instead.
