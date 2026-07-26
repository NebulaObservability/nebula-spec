# Release Manifests

每个 YAML 文件描述一次平台发行版的兼容组件组合。`CURRENT` 指向用于生成制品和 conformance bundle 的当前草案；已发布的历史 Manifest 必须保留，不能就地改写。

## APM Metrics

Metrics 发布在 `protocols.apm_metrics` 中声明独立 contract 版本，并与
`protocols.apm_extension`、`otel_schema` 和 `components.spec` 一起固定。RUTP 与 Control
Plane 版本不会因 APM Metrics profile 发布而隐式变化。
