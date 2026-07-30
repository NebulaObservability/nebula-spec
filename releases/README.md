# Release Manifests

每个 YAML 文件描述一次平台发行版的兼容组件组合。`CURRENT` 指向用于生成制品和 conformance bundle 的当前草案；已发布的历史 Manifest 必须保留，不能就地改写。

## APM Metrics

Metrics 发布在 `protocols.apm_metrics` 中声明独立 contract 版本，并与
`protocols.apm_extension`、`otel_schema` 和 `components.spec` 一起固定。RUTP 与 Control
Plane 版本不会因 APM Metrics profile 发布而隐式变化。

## APM Agent

Go Agent 契约分别通过 `protocols.apm_agent`、`protocols.apm_agent_config` 和
`protocols.apm_agent_diagnostics` 固定，并与当前 APM extension、Metrics 和 Spec 版本一起
发布。Spec Release 只声明协议和可消费制品；在 Agent 仓库的对应 Go module tag 实际发布前，
`components.apm_agent_go` 必须保持 `null`，不得提前宣称实现已交付。
