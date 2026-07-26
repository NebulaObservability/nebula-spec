# Versioning

协议版本与 Agent、SDK、Collector、Backend 和 Dashboard 版本相互独立。

## 语义化版本

- Patch：不改变编码或运行时行为的修正。
- Minor：向后兼容地增加可选字段、枚举值或能力。
- Major：删除、重命名、改变语义或编码不兼容。

带 `draft` 预发布标识的版本不承诺稳定性。发布 `1.0.0` 后，所有不兼容变更必须提升 Major。

## 演进规则

1. Protobuf 字段号不得复用，删除字段必须标记为 `reserved`。
2. 消费者必须忽略未知字段。
3. 新增字段默认可选；必填语义需要能力协商或新的 Major 版本。
4. 枚举必须保留明确的 `UNSPECIFIED = 0`。
5. 实验性 OTel 语义通过版本化映射隔离。
6. 每个协议变更必须带兼容性说明和 Golden Fixture。
7. `generated/` 只能由仓库 Codegen 更新。

## Release Manifest

每个平台发行版在 `releases/` 中声明协议、OTel Schema 和各组件的兼容版本；组件不共享一个版本号。

## 可分发制品

`VERSION` 是 generated TypeScript package、generated Rust crate、generated Go module
和 RUM Conformance bundle 的唯一版本源。发布 tag 必须严格使用
`spec-v<VERSION>` 格式，例如 `VERSION=0.2.0-draft.0` 对应
`spec-v0.2.0-draft.0`。

发布制品还包含生成的 `@nebula-observability/rutp-protobuf` package。Browser
SDK 必须固定并校验此制品，不得在实现仓库维护私有 Protobuf codec。

Go module 还必须在同一提交创建 `generated/go/v<VERSION>` tag，例如
`generated/go/v0.2.0-draft.0`，供 Collector 和 Backend 以标准 Go module 版本解析。
发布 workflow 会生成 npm tarball、Cargo crate、Go module zip、Fixture zip 和 `SHA256SUMS`。
消费者必须固定所依赖的制品版本，并在执行 Fixture 前验证
`fixture-manifest.json` 中的 SHA-256。预发布版本只可用于明确记录的兼容组合，
不能隐式升级。

RUTP Receiver 的认证主体绑定、项目声明校验和 JSON 调试规则同样随 `VERSION`
发布。仅新增可选 JSON 字段、Fixture 或兼容接收语义时提升 Minor；只有改变
Protobuf 编码、删除字段或改变既有字段语义时才提升 RUTP Major。Receiver 不能以
客户端 `project_id` 选择 tenant/project，这一安全边界不得作为兼容性例外放宽。

Control Plane Config 的服务端修订记录与 SDK delivery 封套也随 `VERSION` 发布，
并在 Release Manifest 中声明独立的 `control_plane_config` 协议版本。新增可选的
管理元数据或 SDK capability 可以提升 Minor；改变 delivery 的认证 scope、active
revision、ETag 或默认拒绝隐私边界属于不兼容的运行时语义变更。服务端 scope 和
审计字段不得出现在 SDK delivery 中，也不得由浏览器或遥测正文选择。

## APM Metrics 契约

APM Metrics profile 使用独立的 `metrics_contract_version`，并在 Release Manifest 的
`protocols.apm_metrics` 中声明。新增向后兼容的指标或可选维度提升 Minor；删除指标、改变
单位、instrument、temporality、monotonicity、必填维度或 exemplar 语义属于不兼容变更。
OTel Schema 版本独立记录，消费者必须同时校验 Metrics contract 与 OTel Schema。
