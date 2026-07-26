# APM v1

`manifest.yaml` 定义 OTLP Trace、Metric、Log 的约束、Resource 必填字段和 APM 扩展版本。主数据继续使用标准 OTLP，不包装私有 Envelope。

Profile 保持适配层实验能力，不能让后端存储模型直接绑定实验版本。租户和项目归属由传输鉴权确定，不信任遥测属性中的租户提示。

## Metrics profile

`metrics.yaml` 固定 APM Metrics `1.1.0-draft.0` profile：标准 OTLP、OTel Schema
`1.43.0`、累计 Sum/Histogram、首选 ExponentialHistogram，以及受约束的指标维度和
Exemplar。它与 APM extension 版本独立演进，并由 `manifest.yaml` 显式关联。

累计状态只在 `startTimeUnixNano` 严格前进时 reset；相同 start time 下的 Histogram
count/sum/bucket 与 monotonic Sum value 不得回退。ExponentialHistogram scale 可变化，
但必须投影到两次 export 的较低 scale 后比较。Scope version 可省略；Exemplar
`filteredAttributes` 禁用，Trace/Span ID 使用 OTLP JSON 小写 hex。

`1.43.0` 是归一化目标与可接受源 Schema 上限，不是生产者声明值的 exact gate。
Receiver 接受空/省略的 Schema URL，或不高于该上限的 OpenTelemetry 官方 semver URL；
非官方 URL 与未来版本必须拒绝。
