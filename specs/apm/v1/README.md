# APM v1

`manifest.yaml` 定义 OTLP Trace、Metric、Log 的约束、Resource 必填字段和 APM 扩展版本。主数据继续使用标准 OTLP，不包装私有 Envelope。

Profile 保持适配层实验能力，不能让后端存储模型直接绑定实验版本。租户和项目归属由传输鉴权确定，不信任遥测属性中的租户提示。

## Metrics profile

`metrics.yaml` 固定 APM Metrics `1.2.0-draft.0` profile：标准 OTLP、OTel Schema
`1.43.0`、累计 Sum/Histogram、首选 ExponentialHistogram，以及受约束的指标维度和
Exemplar。它与 APM extension 版本独立演进，并由 `manifest.yaml` 显式关联。

累计状态只在 `startTimeUnixNano` 严格前进时 reset；相同 start time 下的 Histogram
count/sum/bucket 与 monotonic Sum value 不得回退。ExponentialHistogram scale 可变化，
但必须投影到两次 export 的较低 scale 后比较。Scope version 可省略；Exemplar
`filteredAttributes` 禁用，Trace/Span ID 使用 OTLP JSON 小写 hex。

`1.43.0` 是归一化目标与可接受源 Schema 上限，不是生产者声明值的 exact gate。
Receiver 接受空/省略的 Schema URL，或不高于该上限的 OpenTelemetry 官方 semver URL；
非官方 URL 与未来版本必须拒绝。

## Go Agent profile

`go-agent.yaml` 固定 Go APM Agent `1.0.0-draft.0`，并绑定配置与诊断契约、
OpenTelemetry Go SDK `1.44.0` 及 runtime instrumentation `0.69.0`。Agent 使用
`telemetry.distro.name=nebula-go-agent` 和不可变的发行版本；第三方标准发行版只要同时提供
合法的 `telemetry.distro.name`/`telemetry.distro.version` 仍可兼容。

运行时 profile 包含 9 个标准 `go.*` 指标，全部使用官方 runtime scope/version，禁止旧
`runtime.go.*` 指标。`go.memory.limit` 仅在进程存在有效 `GOMEMLIMIT` 时出现，其余指标按
契约必需。`go.memory.used` 的 `go.memory.type` 只能是 `stack` 或 `other`。
