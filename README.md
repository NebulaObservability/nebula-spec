# Nebula Specification

Nebula Observability 协议、语义、隐私规则和跨语言一致性测试的唯一事实来源。
通过 `generated/` 中的版本化制品向 SDK、Agent、Collector、Backend 和
Dashboard 分发 registry 与 conformance fixtures；实现仓库不得复制这些内容。

## 范围

- APM 和 RUM 协议定义。
- OpenTelemetry Semantic Conventions 映射。
- 属性、事件、指标和枚举注册表。
- 隐私分类及默认策略。
- 兼容性矩阵、Golden Fixtures 和 Release Manifest。
- TypeScript、Java、Go、Rust 等语言的生成代码。

本仓库不实现 Agent、SDK、Collector、Backend 或 Dashboard 业务逻辑。

## 目录

```text
specs/          协议和语义源文件
schemas/        可独立校验的 JSON Schema
compatibility/  协议及 OTel 版本兼容矩阵
fixtures/       跨语言一致性测试数据
generated/      Codegen 生成物
releases/       平台 Release Manifest
tools/          Lint、Diff 和生成工具
```

Phase 1 已提供：

- RUTP v1 Batch、Record、Context、Config 和 Replay Proto。
- APM v1 OTLP/Resource 约束及 RUTP 到 OTLP 的版本化映射。
- 语义、枚举和隐私注册表。
- RUM Batch、ACK、配置、隐私和 Release Manifest JSON Schema。
- RUTP Receiver 的认证主体 tenant/project 绑定和受限 JSON 调试边界。
- Control Plane v1 的不可变配置修订、回滚与不含 scope 的 SDK delivery 封套。
- TypeScript、Java、Go、Rust 语义常量生成，以及可消费的 Go RUTP v1 Protobuf module。
- Golden Fixtures、协议 Lint 和兼容性快照检查。

## 可分发制品

每次 `spec-v*` tag 发布以下 GitHub Release assets：

- `@nebula-observability/semantic-registry` npm tarball
- `@nebula-observability/rutp-protobuf` browser-compatible npm tarball
- `nebula-semantic-registry` Rust crate
- `@nebula-observability/rum-conformance` npm tarball
- `@nebula-observability/apm-metrics-contract` npm tarball and standalone zip
- RUM conformance fixture zip 与 `SHA256SUMS`
- 含 RUTP v1 Protobuf 和 Go 语义 registry 的 `nebula-rutp-go-module` zip

制品版本来自 `VERSION`，消费者必须在依赖声明或 Release Manifest 中固定版本。
Go 消费者使用与其 `VERSION` 对应的 `generated/go/v<VERSION>` module tag，
而非复制 `*.pb.go` 文件。

## 版本

当前仓库版本见 [`VERSION`](VERSION)。版本和兼容规则见 [`VERSIONING.md`](VERSIONING.md)。

## 开发命令

```powershell
python -m pip install -r tools/requirements.txt
python tools/spec_tool.py lint
python tools/spec_tool.py verify-receiver-contract
python tools/spec_tool.py verify-control-plane-contract
python tools/spec_tool.py verify-apm-metrics-contract
python tools/spec_tool.py generate --check
python tools/spec_tool.py verify-artifacts
python tools/spec_tool.py breaking --against compatibility/baselines/semantic-registry-0.5.0-draft.0.json
python tools/spec_tool.py breaking-apm-metrics --against compatibility/baselines/apm-metrics-1.1.0-draft.0.json
npx --yes @bufbuild/buf@1.72.0 lint
npx --yes @bufbuild/buf@1.72.0 generate --template buf.gen.yaml
```

需要更新生成物时运行：

```powershell
python tools/spec_tool.py generate
```

兼容性快照只能在准备新协议基线时更新，不能用更新快照来隐藏 Breaking Change。

## APM Metrics MVP 发布入口

`specs/apm/v1/metrics.yaml` 固定标准 OTLP Metrics profile，`schemas/apm-metrics.schema.json` 与
`schemas/otlp-metrics-export.schema.json` 提供结构校验，`fixtures/metrics/apm-metrics-mvp.json`
提供跨仓库 Golden Fixture。Release `2026.07.6-draft.0` 将 Spec `0.6.0-draft.0`、APM
extension 和 Metrics contract `1.1.0-draft.0` 绑定到 OTel Schema `1.43.0`。消费者必须按
Release Manifest 固定版本，不得复制或私有扩展标准指标。

连续 export conformance 另外冻结累计 reset、同 start time 回退和跨 scale bucket 比较；
OTLP JSON Exemplar ID 使用小写 hex，且禁止 `filteredAttributes` 携带额外维度。
源 Schema URL 可为空/省略或为不高于 `1.43.0` 的 OpenTelemetry 官方 semver URL，
并统一归一化到目标 Schema `1.43.0`。
