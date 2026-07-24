# Generated Artifacts

此目录只接受 `python tools/spec_tool.py generate` 的生成结果，禁止手工编辑。
它包含：

- `typescript/`：可直接发布的 ESM package
  `@nebula-observability/semantic-registry`。
- `rust/nebula-semantic-registry/`：可直接打包的 Cargo crate。
- `conformance/`：带 SHA-256 `fixture-manifest.json` 的 npm fixture bundle。
- `java/` 和 `go/`：供对应实现仓库消费的源码级 registry。

所有制品的版本都来自根目录 `VERSION`。发布 `spec-v*` tag 时，
`release-artifacts` workflow 会生成 npm tarball、Rust crate、Fixture zip 和
`SHA256SUMS`，并作为 GitHub Release assets 上传。实现仓库必须消费版本化
制品，不能复制 registry 或 fixture。

CI 使用 `generate --check` 和 `verify-artifacts` 检查源规范、生成物、版本和
Fixture 完整性是否一致。
