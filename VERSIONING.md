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

`VERSION` 是 generated TypeScript package、generated Rust crate 和 RUM
Conformance bundle 的唯一版本源。发布 tag 必须严格使用
`spec-v<VERSION>` 格式，例如 `VERSION=0.2.0-draft.0` 对应
`spec-v0.2.0-draft.0`。

发布 workflow 会生成 npm tarball、Cargo crate、Fixture zip 和 `SHA256SUMS`。
消费者必须固定所依赖的制品版本，并在执行 Fixture 前验证
`fixture-manifest.json` 中的 SHA-256。预发布版本只可用于明确记录的兼容组合，
不能隐式升级。
