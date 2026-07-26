# APM v1

`manifest.yaml` 定义 OTLP Trace、Metric、Log 的约束、Resource 必填字段和 APM 扩展版本。主数据继续使用标准 OTLP，不包装私有 Envelope。

Profile 保持适配层实验能力，不能让后端存储模型直接绑定实验版本。租户和项目归属由传输鉴权确定，不信任遥测属性中的租户提示。

## Metrics profile

`metrics.yaml` 固定 APM Metrics `1.1.0-draft.0` profile：标准 OTLP、OTel Schema
`1.43.0`、累计 Sum/Histogram、首选 ExponentialHistogram，以及受约束的指标维度和
Exemplar。它与 APM extension 版本独立演进，并由 `manifest.yaml` 显式关联。
